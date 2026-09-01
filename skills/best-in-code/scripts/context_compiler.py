#!/usr/bin/env python3
"""Build bounded, provenance-rich context manifests and validate tool contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, Iterable, Sequence


sys.dont_write_bytecode = True


COMPILER_VERSION = "1.0.0"
CONTEXT_SCHEMA_VERSION = 1
TOOL_REGISTRY_SCHEMA_VERSION = 1
DEFAULT_MAX_CONTENT_BYTES = 64 * 1024
DEFAULT_MAX_FILES = 32
DEFAULT_MAX_TOKENS = 16_000
DEFAULT_MAX_SOURCE_BYTES = 16 * 1024
DEFAULT_SCAN_BYTES = 4 * 1024 * 1024
MAX_TASK_BYTES = 16 * 1024
MAX_REGISTRY_BYTES = 1024 * 1024
MAX_DISCOVERY_ENTRIES = 4096
MAX_DISCOVERY_DEPTH = 16
GIT_TIMEOUT_SECONDS = 5.0

INSTRUCTION_PATHS = (
	"AGENTS.md",
	"CLAUDE.md",
	"GEMINI.md",
	"AI-HARNESS.md",
	".github/copilot-instructions.md",
)
IGNORED_DIRECTORIES = {
	".git",
	".hg",
	".svn",
	".idea",
	".vscode",
	"__pycache__",
	"coverage",
	"dist",
	"build",
	"node_modules",
	"target",
	"vendor",
}
TEXT_SUFFIXES = {
	".c", ".cc", ".cpp", ".cs", ".css", ".go", ".h", ".hpp", ".html",
	".java", ".js", ".json", ".jsx", ".kt", ".md", ".mjs", ".php",
	".py", ".rb", ".rs", ".sh", ".sql", ".svelte", ".toml", ".ts",
	".tsx", ".txt", ".vue", ".xml", ".yaml", ".yml",
}
TASK_STOP_WORDS = {
	"about", "after", "again", "also", "and", "build", "change", "code", "create",
	"file", "for", "from", "have", "into", "make", "more", "project", "should",
	"that", "the", "their", "this", "use", "using", "with", "your",
}

INJECTION_RULES = (
	(
		"instruction_override",
		"high",
		re.compile(r"\b(?:ignore|disregard|override|forget)\s+(?:all\s+)?(?:previous|prior|above|system|developer)\s+(?:instructions?|messages?|rules?)\b", re.IGNORECASE),
	),
	(
		"role_impersonation",
		"high",
		re.compile(r"(?:^|\n)\s*(?:system|developer)\s*(?:message)?\s*:\s*", re.IGNORECASE),
	),
	(
		"secret_exfiltration",
		"high",
		re.compile(r"\b(?:reveal|print|send|upload|exfiltrate)\b.{0,80}\b(?:secret|credential|token|password|system prompt|private key)\b", re.IGNORECASE | re.DOTALL),
	),
	(
		"tool_execution_directive",
		"medium",
		re.compile(r"(?:<\/?tool_call>|\bfunction_call\s*\(|\bexecute\s+(?:this|the following)\s+(?:command|tool)\b)", re.IGNORECASE),
	),
)

ALLOWED_SIDE_EFFECTS = {"none", "read", "write", "external", "destructive"}
ALLOWED_APPROVALS = {"none", "policy", "human"}
ALLOWED_TELEMETRY_EVENTS = {
	"attempted", "authorized", "denied", "started", "completed", "failed", "timed_out",
}
ALLOWED_SCHEMA_TYPES = {"array", "boolean", "integer", "null", "number", "object", "string"}
ALLOWED_SCHEMA_KEYS = {
	"type", "description", "properties", "required", "additionalProperties", "items",
	"enum", "const", "default", "minimum", "maximum", "minLength", "maxLength",
	"minItems", "maxItems", "pattern", "format",
}


class ContextCompilerError(ValueError):
	"""Raised when the compiler cannot preserve a required safety invariant."""


@dataclass(frozen=True)
class Limits:
	max_content_bytes: int = DEFAULT_MAX_CONTENT_BYTES
	max_files: int = DEFAULT_MAX_FILES
	max_tokens: int = DEFAULT_MAX_TOKENS
	max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES
	scan_bytes: int = DEFAULT_SCAN_BYTES

	def validate(self) -> None:
		_ranges = (
			("max_content_bytes", self.max_content_bytes, 1024, 4 * 1024 * 1024),
			("max_files", self.max_files, 1, 256),
			("max_tokens", self.max_tokens, 256, 1_000_000),
			("max_source_bytes", self.max_source_bytes, 256, 1024 * 1024),
			("scan_bytes", self.scan_bytes, 1024, 64 * 1024 * 1024),
		)
		for name, value, minimum, maximum in _ranges:
			if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
				raise ContextCompilerError(f"{name} must be an integer from {minimum} to {maximum}")
		if self.max_source_bytes > self.max_content_bytes:
			raise ContextCompilerError("max_source_bytes cannot exceed max_content_bytes")


@dataclass(frozen=True)
class FileCandidate:
	path: Path
	kind: str
	reason: str
	authority: str
	trust: str
	content_role: str
	priority: int


def configure_utf8_stdio() -> None:
	for stream in (sys.stdout, sys.stderr):
		reconfigure = getattr(stream, "reconfigure", None)
		if reconfigure:
			reconfigure(encoding="utf-8", errors="backslashreplace")


def canonical_json(value: Any, *, pretty: bool = False) -> str:
	if pretty:
		return json.dumps(value, ensure_ascii=False, indent="\t", sort_keys=True) + "\n"
	return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_bytes(raw: bytes) -> str:
	return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def sha256_text(text: str) -> str:
	return sha256_bytes(text.encode("utf-8"))


def estimate_tokens(text: str) -> int:
	"""Return a deterministic, conservative tokenizer-independent estimate."""
	byte_count = len(text.encode("utf-8"))
	return 0 if byte_count == 0 else (byte_count + 3) // 4


def detect_prompt_injection(text: str) -> dict[str, Any]:
	flags: list[dict[str, str]] = []
	for rule_id, severity, pattern in INJECTION_RULES:
		if pattern.search(text):
			flags.append({"id": rule_id, "severity": severity})
	return {
		"detected": bool(flags),
		"flags": flags,
		"high_confidence": any(flag["severity"] == "high" for flag in flags),
	}


def _is_link_or_junction(path: Path) -> bool:
	try:
		return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())
	except OSError:
		return True


def _normalize_relative_path(raw_path: str) -> PurePath:
	if not isinstance(raw_path, str) or not raw_path.strip() or "\x00" in raw_path:
		raise ContextCompilerError("source path must be a non-empty relative path")
	path = Path(raw_path)
	if path.is_absolute() or path.drive or any(part in {"", ".", ".."} for part in path.parts):
		raise ContextCompilerError(f"source path must stay inside the project: {raw_path}")
	return PurePath(*path.parts)


def resolve_project_file(root: Path, raw_path: str) -> Path:
	relative = _normalize_relative_path(raw_path)
	current = root
	for part in relative.parts:
		current = current / part
		if not current.exists():
			raise ContextCompilerError(f"source file does not exist: {relative.as_posix()}")
		if _is_link_or_junction(current):
			raise ContextCompilerError(f"source path cannot contain a symlink or junction: {relative.as_posix()}")
	try:
		resolved = current.resolve(strict=True)
		resolved.relative_to(root)
	except (OSError, ValueError) as exc:
		raise ContextCompilerError(f"source path escapes the project: {relative.as_posix()}") from exc
	if not resolved.is_file():
		raise ContextCompilerError(f"source path must name one regular file: {relative.as_posix()}")
	return resolved


def relative_locator(root: Path, path: Path) -> str:
	return path.relative_to(root).as_posix()


def read_regular_file(path: Path, max_bytes: int) -> tuple[bytes | None, int, str | None]:
	"""Read at most max_bytes from one stable, non-linked regular file."""
	try:
		if _is_link_or_junction(path):
			return None, 0, "symlink_or_junction"
		initial = path.lstat()
		if not stat.S_ISREG(initial.st_mode):
			return None, 0, "not_regular_file"
		if initial.st_size > max_bytes:
			return None, initial.st_size, "source_exceeds_per_file_cap"
		flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0) | getattr(os, "O_NOFOLLOW", 0)
		descriptor = os.open(path, flags)
		try:
			metadata = os.fstat(descriptor)
			if not stat.S_ISREG(metadata.st_mode) or (initial.st_dev, initial.st_ino) != (metadata.st_dev, metadata.st_ino):
				return None, metadata.st_size, "file_changed_while_opening"
			raw = os.read(descriptor, max_bytes + 1)
			final = os.fstat(descriptor)
			if (metadata.st_dev, metadata.st_ino, metadata.st_size) != (final.st_dev, final.st_ino, final.st_size):
				return None, final.st_size, "file_changed_while_reading"
		finally:
			os.close(descriptor)
	except OSError:
		return None, 0, "unreadable_file"
	if len(raw) > max_bytes:
		return None, len(raw), "source_exceeds_per_file_cap"
	return raw, len(raw), None


def decode_utf8(raw: bytes) -> tuple[str | None, str | None]:
	try:
		return raw.decode("utf-8"), None
	except UnicodeDecodeError:
		return None, "not_utf8_text"


def _bounded_git(root: Path, arguments: Sequence[str], max_bytes: int) -> tuple[str, bool, int | None]:
	command = ["git", "-c", "color.ui=false", "-c", "core.quotepath=false", *arguments]
	try:
		process = subprocess.Popen(
			command,
			cwd=root,
			stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
		)
	except OSError:
		return "", False, None
	result: dict[str, bytes] = {"raw": b""}

	def read_output() -> None:
		assert process.stdout is not None
		result["raw"] = process.stdout.read(max_bytes + 1)

	reader = threading.Thread(target=read_output, daemon=True)
	reader.start()
	reader.join(GIT_TIMEOUT_SECONDS)
	if reader.is_alive():
		process.kill()
		reader.join(1.0)
		process.wait(timeout=1.0)
		return "", True, None
	raw = result["raw"]
	truncated = len(raw) > max_bytes
	if truncated and process.poll() is None:
		process.kill()
	try:
		return_code = process.wait(timeout=1.0)
	except subprocess.TimeoutExpired:
		process.kill()
		process.wait(timeout=1.0)
		return_code = None
	raw = raw[:max_bytes]
	return raw.decode("utf-8", errors="replace"), truncated, return_code


def git_commit(root: Path) -> str:
	output, truncated, return_code = _bounded_git(root, ("rev-parse", "--verify", "HEAD"), 256)
	value = output.strip()
	if truncated or return_code != 0 or not re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
		return "NO_GIT_COMMIT"
	return value.lower()


def _task_terms(task: str) -> tuple[str, ...]:
	terms = {
		match.group(0).lower()
		for match in re.finditer(r"[A-Za-z0-9_.-]{3,}", task)
		if match.group(0).lower() not in TASK_STOP_WORDS
	}
	return tuple(sorted(terms))


def discover_text_files(root: Path) -> tuple[list[Path], dict[str, Any]]:
	files: list[Path] = []
	entries_seen = 0
	skipped_links = 0
	stack: list[tuple[Path, int]] = [(root, 0)]
	while stack and entries_seen < MAX_DISCOVERY_ENTRIES:
		directory, depth = stack.pop()
		if depth > MAX_DISCOVERY_DEPTH:
			continue
		try:
			entries = sorted(os.scandir(directory), key=lambda entry: entry.name.lower(), reverse=True)
		except OSError:
			continue
		for entry in entries:
			entries_seen += 1
			if entries_seen > MAX_DISCOVERY_ENTRIES:
				break
			path = Path(entry.path)
			try:
				if entry.is_symlink() or _is_link_or_junction(path):
					skipped_links += 1
					continue
				if entry.is_dir(follow_symlinks=False):
					if entry.name not in IGNORED_DIRECTORIES and not (relative_locator(root, path) == ".harness/.cache"):
						stack.append((path, depth + 1))
				elif entry.is_file(follow_symlinks=False) and path.suffix.lower() in TEXT_SUFFIXES:
					files.append(path)
			except OSError:
				continue
	files.sort(key=lambda item: relative_locator(root, item))
	return files, {
		"entry_cap": MAX_DISCOVERY_ENTRIES,
		"entries_seen": min(entries_seen, MAX_DISCOVERY_ENTRIES),
		"truncated": entries_seen >= MAX_DISCOVERY_ENTRIES,
		"links_skipped": skipped_links,
	}


def _path_relevance(path: Path, root: Path, terms: Sequence[str]) -> int:
	locator = relative_locator(root, path).lower()
	return sum(4 if term in Path(locator).stem else 1 for term in terms if term in locator)


def select_symbol_files(
	root: Path,
	paths: Sequence[Path],
	symbols: Sequence[str],
	limits: Limits,
) -> tuple[list[tuple[Path, tuple[str, ...]]], dict[str, Any]]:
	if not symbols:
		return [], {"byte_cap": limits.scan_bytes, "bytes_scanned": 0, "truncated": False}
	valid_symbols: tuple[str, ...] = tuple(dict.fromkeys(symbol for symbol in symbols if symbol))
	if len(valid_symbols) != len(symbols) or any(len(symbol.encode("utf-8")) > 256 for symbol in valid_symbols):
		raise ContextCompilerError("symbols must be unique non-empty UTF-8 strings of at most 256 bytes")
	remaining = limits.scan_bytes
	matches: list[tuple[Path, tuple[str, ...]]] = []
	truncated = False
	for path in paths:
		if remaining <= 0:
			truncated = True
			break
		per_file_cap = min(limits.max_source_bytes, remaining)
		raw, byte_count, error = read_regular_file(path, per_file_cap)
		remaining -= min(byte_count, per_file_cap)
		if error or raw is None:
			continue
		text, decode_error = decode_utf8(raw)
		if decode_error or text is None:
			continue
		found = tuple(symbol for symbol in valid_symbols if symbol in text)
		if found:
			matches.append((path, found))
	return matches, {
		"byte_cap": limits.scan_bytes,
		"bytes_scanned": limits.scan_bytes - remaining,
		"truncated": truncated,
	}


class ManifestBuilder:
	def __init__(self, root: Path, task: str, commit: str, limits: Limits) -> None:
		self.root = root
		self.task = task
		self.commit = commit
		self.limits = limits
		self.sources: list[dict[str, Any]] = []
		self.quarantine: list[dict[str, Any]] = []
		self.excluded: list[dict[str, Any]] = []
		self.diagnostics: list[dict[str, str]] = []
		self.bytes_used = len(task.encode("utf-8"))
		self.tokens_used = estimate_tokens(task)
		self.files_considered = 0

	def _metadata(
		self,
		*,
		kind: str,
		locator: str,
		reason: str,
		authority: str,
		trust: str,
		content_role: str,
		content: str,
		source_digest: str,
		truncated: bool,
	) -> dict[str, Any]:
		injection = detect_prompt_injection(content)
		content_bytes = len(content.encode("utf-8"))
		return {
			"id": sha256_text(f"{kind}\0{locator}")[:23],
			"kind": kind,
			"locator": locator,
			"selection_reason": reason,
			"authority": authority,
			"trust": trust,
			"content_role": content_role,
			"policy_effect": "may_define_project_policy" if trust == "trusted_control" else "data_only",
			"provenance": {
				"git_commit": self.commit,
				"source_sha256": source_digest,
			},
			"content_sha256": sha256_text(content),
			"byte_count": content_bytes,
			"token_estimate": estimate_tokens(content),
			"truncated": truncated,
			"prompt_injection": injection,
		}

	def add_content(
		self,
		*,
		kind: str,
		locator: str,
		reason: str,
		authority: str,
		trust: str,
		content_role: str,
		content: str,
		source_digest: str | None = None,
		truncated: bool = False,
		file_backed: bool = False,
	) -> None:
		if file_backed:
			if self.files_considered >= self.limits.max_files:
				self.excluded.append({"kind": kind, "locator": locator, "reason": "file_cap_reached"})
				return
			self.files_considered += 1
		metadata = self._metadata(
			kind=kind,
			locator=locator,
			reason=reason,
			authority=authority,
			trust=trust,
			content_role=content_role,
			content=content,
			source_digest=source_digest or sha256_text(content),
			truncated=truncated,
		)
		if metadata["prompt_injection"]["high_confidence"] and trust != "trusted_control":
			metadata["quarantined"] = True
			metadata["selected"] = False
			metadata["quarantine_reason"] = "high_confidence_prompt_injection"
			self.quarantine.append(metadata)
			return
		if self.bytes_used + metadata["byte_count"] > self.limits.max_content_bytes:
			self.excluded.append({"kind": kind, "locator": locator, "reason": "content_byte_cap_reached"})
			return
		if self.tokens_used + metadata["token_estimate"] > self.limits.max_tokens:
			self.excluded.append({"kind": kind, "locator": locator, "reason": "token_cap_reached"})
			return
		metadata["quarantined"] = False
		metadata["selected"] = True
		metadata["content"] = content
		self.bytes_used += metadata["byte_count"]
		self.tokens_used += metadata["token_estimate"]
		self.sources.append(metadata)

	def add_file(self, candidate: FileCandidate) -> None:
		locator = relative_locator(self.root, candidate.path)
		if self.files_considered >= self.limits.max_files:
			self.excluded.append({"kind": candidate.kind, "locator": locator, "reason": "file_cap_reached"})
			return
		raw, size, error = read_regular_file(candidate.path, self.limits.max_source_bytes)
		if error or raw is None:
			self.files_considered += 1
			self.excluded.append({
				"kind": candidate.kind,
				"locator": locator,
				"reason": error or "unreadable_file",
				"observed_bytes": size,
			})
			return
		text, decode_error = decode_utf8(raw)
		if decode_error or text is None:
			self.files_considered += 1
			self.excluded.append({"kind": candidate.kind, "locator": locator, "reason": decode_error})
			return
		if candidate.kind == "harness_memory":
			try:
				parsed = json.loads(text, object_pairs_hook=_unique_object)
			except (json.JSONDecodeError, ValueError, RecursionError) as exc:
				self.files_considered += 1
				self.excluded.append({"kind": candidate.kind, "locator": locator, "reason": "invalid_canonical_memory"})
				self.diagnostics.append({"code": "invalid_memory", "message": str(exc)})
				return
			if not isinstance(parsed, dict) or parsed.get("schema_version") != 1 or not isinstance(parsed.get("records"), list):
				self.files_considered += 1
				self.excluded.append({"kind": candidate.kind, "locator": locator, "reason": "invalid_canonical_memory_shape"})
				return
			text = canonical_json(parsed)
		self.add_content(
			kind=candidate.kind,
			locator=locator,
			reason=candidate.reason,
			authority=candidate.authority,
			trust=candidate.trust,
			content_role=candidate.content_role,
			content=text,
			source_digest=sha256_bytes(raw),
			file_backed=True,
		)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
	result: dict[str, Any] = {}
	for key, value in pairs:
		if key in result:
			raise ValueError(f"duplicate JSON key: {key}")
		result[key] = value
	return result


def _candidate_key(candidate: FileCandidate, root: Path) -> tuple[int, str, str]:
	return candidate.priority, relative_locator(root, candidate.path), candidate.kind


def compile_context(
	project: str | Path,
	task: str,
	*,
	includes: Sequence[str] = (),
	symbols: Sequence[str] = (),
	verification: Sequence[str] = (),
	limits: Limits | None = None,
) -> dict[str, Any]:
	limits = limits or Limits()
	limits.validate()
	if not isinstance(task, str) or not task.strip():
		raise ContextCompilerError("task must be a non-empty string")
	task_bytes = len(task.encode("utf-8"))
	if task_bytes > MAX_TASK_BYTES:
		raise ContextCompilerError(f"task exceeds {MAX_TASK_BYTES} UTF-8 bytes")
	if task_bytes > limits.max_content_bytes or estimate_tokens(task) > limits.max_tokens:
		raise ContextCompilerError("task alone exceeds the configured context budget")
	try:
		root = Path(project).expanduser().resolve(strict=True)
	except OSError as exc:
		raise ContextCompilerError(f"project does not exist: {project}") from exc
	if not root.is_dir():
		raise ContextCompilerError("project must be a directory")

	commit = git_commit(root)
	builder = ManifestBuilder(root, task, commit, limits)
	candidates: list[FileCandidate] = []
	seen: set[tuple[str, str]] = set()

	def add_candidate(candidate: FileCandidate) -> None:
		key = (relative_locator(root, candidate.path), candidate.kind)
		if key not in seen:
			seen.add(key)
			candidates.append(candidate)

	for locator in INSTRUCTION_PATHS:
		try:
			path = resolve_project_file(root, locator)
		except ContextCompilerError:
			continue
		add_candidate(FileCandidate(path, "project_instruction", "trusted project instruction", "project_owner", "trusted_control", "instruction", 10))

	selected_paths: list[str] = []
	for raw_path in includes:
		path = resolve_project_file(root, raw_path)
		locator = relative_locator(root, path)
		selected_paths.append(locator)
		add_candidate(FileCandidate(path, "repository_file", "explicit task-relevant include", "repository", "untrusted_data", "data", 30))

	for raw_path in verification:
		path = resolve_project_file(root, raw_path)
		add_candidate(FileCandidate(path, "verification_metadata", "explicit verification evidence", "verification_system", "untrusted_evidence", "evidence", 50))

	memory_locator = ".harness/MEMORY.json"
	try:
		memory_path = resolve_project_file(root, memory_locator)
	except ContextCompilerError:
		memory_path = None
	if memory_path is not None:
		add_candidate(FileCandidate(memory_path, "harness_memory", "canonical Harness memory", "harness_memory_store", "untrusted_data", "data", 25))

	discovered, discovery = discover_text_files(root)
	symbol_matches, symbol_scan = select_symbol_files(root, discovered, symbols, limits)
	for path, found in symbol_matches:
		add_candidate(FileCandidate(path, "repository_file", f"symbol match: {', '.join(found)}", "repository", "untrusted_data", "data", 35))

	terms = _task_terms(task)
	relevant = sorted(
		((path, _path_relevance(path, root, terms)) for path in discovered),
		key=lambda item: (-item[1], relative_locator(root, item[0])),
	)
	for path, score in relevant:
		if score <= 0:
			break
		add_candidate(FileCandidate(path, "repository_file", f"task-path relevance score {score}", "repository", "untrusted_data", "data", 60))

	git_paths = sorted(set(selected_paths + [relative_locator(root, candidate.path) for candidate in candidates if candidate.kind == "repository_file"]))[:limits.max_files]
	if commit != "NO_GIT_COMMIT":
		path_arguments: tuple[str, ...] = ("--", *git_paths) if git_paths else ("--",)
		status, status_truncated, status_code = _bounded_git(
			root,
			("status", "--porcelain=v1", "--untracked-files=all", *path_arguments),
			min(limits.max_source_bytes, 16 * 1024),
		)
		if status_code == 0:
			builder.add_content(
				kind="git_status",
				locator="git:status",
				reason="working-tree status for selected paths",
				authority="git",
				trust="untrusted_evidence",
				content_role="evidence",
				content=status,
				truncated=status_truncated,
			)
		unstaged, unstaged_truncated, unstaged_code = _bounded_git(
			root,
			("diff", "--no-ext-diff", "--unified=2", *path_arguments),
			min(limits.max_source_bytes, 16 * 1024),
		)
		staged, staged_truncated, staged_code = _bounded_git(
			root,
			("diff", "--cached", "--no-ext-diff", "--unified=2", *path_arguments),
			min(limits.max_source_bytes, 16 * 1024),
		)
		if unstaged_code == 0 and staged_code == 0:
			diff_content = f"[unstaged]\n{unstaged}\n[staged]\n{staged}"
			builder.add_content(
				kind="git_diff",
				locator="git:diff",
				reason="staged and unstaged diff for selected paths",
				authority="git",
				trust="untrusted_evidence",
				content_role="evidence",
				content=diff_content,
				truncated=unstaged_truncated or staged_truncated,
			)

	for candidate in sorted(candidates, key=lambda item: _candidate_key(item, root)):
		builder.add_file(candidate)

	manifest: dict[str, Any] = {
		"schema_version": CONTEXT_SCHEMA_VERSION,
		"compiler": {
			"name": "harness-context-compiler",
			"version": COMPILER_VERSION,
			"token_estimate": "ceil(utf8_bytes/4); tokenizer-independent upper planning estimate",
		},
		"task": {
			"text": task,
			"authority": "user",
			"trust": "trusted_request",
			"content_sha256": sha256_text(task),
			"byte_count": task_bytes,
			"token_estimate": estimate_tokens(task),
		},
		"cache": {
			"key": "",
			"inputs": {
				"compiler_version": COMPILER_VERSION,
				"git_commit": commit,
				"task_sha256": sha256_text(task),
				"source_set_sha256": "",
			},
		},
		"policy_boundary": {
			"rule": "Only trusted_control sources may define project policy; repository, Git, verification, memory, and retrieved content are data.",
			"untrusted_content_can_authorize_tools": False,
			"authorization_is_rechecked_at_execution": True,
		},
		"limits": {
			"max_content_bytes": limits.max_content_bytes,
			"max_files": limits.max_files,
			"max_tokens": limits.max_tokens,
			"max_source_bytes": limits.max_source_bytes,
			"symbol_scan_bytes": limits.scan_bytes,
		},
		"usage": {
			"content_bytes": builder.bytes_used,
			"estimated_tokens": builder.tokens_used,
			"files_considered": builder.files_considered,
			"sources_selected": len(builder.sources),
			"sources_quarantined": len(builder.quarantine),
			"sources_excluded": len(builder.excluded),
		},
		"selection": {
			"task_terms": list(terms),
			"requested_symbols": list(symbols),
			"discovery": discovery,
			"symbol_scan": symbol_scan,
		},
		"sources": builder.sources,
		"quarantine": builder.quarantine,
		"excluded": builder.excluded,
		"diagnostics": builder.diagnostics,
	}
	source_fingerprints = [
		{
			"kind": item["kind"],
			"locator": item["locator"],
			"content_sha256": item["content_sha256"],
			"trust": item["trust"],
			"selected": item["selected"],
			"quarantined": item["quarantined"],
		}
		for item in [*builder.sources, *builder.quarantine]
	]
	manifest["cache"]["inputs"]["source_set_sha256"] = sha256_text(canonical_json(source_fingerprints))
	manifest["cache"]["key"] = sha256_text(canonical_json({
		"inputs": manifest["cache"]["inputs"],
		"limits": manifest["limits"],
		"selection": manifest["selection"],
	}))
	manifest["integrity"] = {
		"manifest_sha256": sha256_text(canonical_json(manifest)),
		"covers": "canonical JSON excluding this integrity object",
	}
	return manifest


def _expect_exact_keys(value: Any, expected: set[str], path: str, errors: list[str]) -> bool:
	if not isinstance(value, dict):
		errors.append(f"{path} must be an object")
		return False
	missing = sorted(expected - set(value))
	unknown = sorted(set(value) - expected)
	if missing:
		errors.append(f"{path} is missing fields: {', '.join(missing)}")
	if unknown:
		errors.append(f"{path} has unknown fields: {', '.join(unknown)}")
	return not missing and not unknown


def _valid_string_list(value: Any, path: str, errors: list[str], *, minimum: int = 1, maximum: int = 16) -> bool:
	if not isinstance(value, list) or not minimum <= len(value) <= maximum:
		errors.append(f"{path} must contain {minimum}-{maximum} strings")
		return False
	if any(not isinstance(item, str) or not item.strip() or len(item.encode("utf-8")) > 1024 for item in value):
		errors.append(f"{path} contains an invalid string")
		return False
	if len(value) != len(set(value)):
		errors.append(f"{path} must not contain duplicates")
		return False
	return True


def _validate_closed_schema(schema: Any, path: str, errors: list[str]) -> None:
	if not isinstance(schema, dict):
		errors.append(f"{path} must be a JSON Schema object")
		return
	unknown = sorted(set(schema) - ALLOWED_SCHEMA_KEYS)
	if unknown:
		errors.append(f"{path} uses unsupported schema fields: {', '.join(unknown)}")
	schema_type = schema.get("type")
	if schema_type not in ALLOWED_SCHEMA_TYPES:
		errors.append(f"{path}.type must be one supported scalar type")
		return
	if schema_type == "object":
		if schema.get("additionalProperties") is not False:
			errors.append(f"{path}.additionalProperties must be false")
		properties = schema.get("properties")
		required = schema.get("required")
		if not isinstance(properties, dict):
			errors.append(f"{path}.properties must be an object")
			properties = {}
		if not isinstance(required, list) or any(not isinstance(field, str) for field in required):
			errors.append(f"{path}.required must be a string array")
			required = []
		if len(required) != len(set(required)):
			errors.append(f"{path}.required must not contain duplicates")
		unknown_required = sorted(set(required) - set(properties))
		if unknown_required:
			errors.append(f"{path}.required names unknown properties: {', '.join(unknown_required)}")
		for name, child in sorted(properties.items()):
			if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", name):
				errors.append(f"{path}.properties has invalid field name: {name}")
				continue
			_validate_closed_schema(child, f"{path}.properties.{name}", errors)
	elif schema_type == "array":
		if "items" not in schema:
			errors.append(f"{path}.items is required for arrays")
		else:
			_validate_closed_schema(schema["items"], f"{path}.items", errors)
	elif "properties" in schema or "required" in schema or "additionalProperties" in schema or "items" in schema:
		errors.append(f"{path} has container fields incompatible with type {schema_type}")


def validate_tool_registry(registry: Any) -> list[str]:
	errors: list[str] = []
	if not _expect_exact_keys(registry, {"schema_version", "registry_id", "tools"}, "registry", errors):
		return errors
	if registry.get("schema_version") != TOOL_REGISTRY_SCHEMA_VERSION:
		errors.append(f"registry.schema_version must be {TOOL_REGISTRY_SCHEMA_VERSION}")
	if not isinstance(registry.get("registry_id"), str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{2,63}", registry.get("registry_id", "")):
		errors.append("registry.registry_id must be a portable lowercase identifier")
	tools = registry.get("tools")
	if not isinstance(tools, list) or not 1 <= len(tools) <= 256:
		errors.append("registry.tools must contain 1-256 tool objects")
		return errors
	names: set[str] = set()
	tool_fields = {
		"name", "version", "summary", "when_to_use", "when_not_to_use", "prohibitions",
		"input_schema", "result_schema", "side_effect_class", "approval_class", "scopes",
		"timeout_ms", "output_policy", "idempotency", "telemetry",
	}
	for index, tool in enumerate(tools):
		path = f"registry.tools[{index}]"
		if not _expect_exact_keys(tool, tool_fields, path, errors):
			continue
		name = tool.get("name")
		if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{2,63}", name):
			errors.append(f"{path}.name must be a portable lowercase identifier")
		elif name in names:
			errors.append(f"{path}.name is duplicated: {name}")
		else:
			names.add(name)
		if not isinstance(tool.get("version"), str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", tool.get("version", "")):
			errors.append(f"{path}.version must be semantic major.minor.patch")
		if not isinstance(tool.get("summary"), str) or not 20 <= len(tool.get("summary", "").strip()) <= 500:
			errors.append(f"{path}.summary must contain 20-500 characters")
		for field in ("when_to_use", "when_not_to_use", "prohibitions"):
			_valid_string_list(tool.get(field), f"{path}.{field}", errors, minimum=1, maximum=16)
		_validate_closed_schema(tool.get("input_schema"), f"{path}.input_schema", errors)
		_validate_closed_schema(tool.get("result_schema"), f"{path}.result_schema", errors)
		side_effect = tool.get("side_effect_class")
		approval = tool.get("approval_class")
		if side_effect not in ALLOWED_SIDE_EFFECTS:
			errors.append(f"{path}.side_effect_class is invalid")
		if approval not in ALLOWED_APPROVALS:
			errors.append(f"{path}.approval_class is invalid")
		if side_effect in {"write", "external"} and approval not in {"policy", "human"}:
			errors.append(f"{path}.approval_class must be policy or human for {side_effect} effects")
		if side_effect == "destructive" and approval != "human":
			errors.append(f"{path}.approval_class must be human for destructive effects")

		scopes = tool.get("scopes")
		if _expect_exact_keys(scopes, {"filesystem", "network", "capabilities"}, f"{path}.scopes", errors):
			filesystem = scopes["filesystem"]
			network = scopes["network"]
			if _expect_exact_keys(filesystem, {"read", "write"}, f"{path}.scopes.filesystem", errors):
				_valid_string_list(filesystem["read"], f"{path}.scopes.filesystem.read", errors, minimum=0, maximum=64)
				_valid_string_list(filesystem["write"], f"{path}.scopes.filesystem.write", errors, minimum=0, maximum=64)
			if _expect_exact_keys(network, {"allow_hosts"}, f"{path}.scopes.network", errors):
				_valid_string_list(network["allow_hosts"], f"{path}.scopes.network.allow_hosts", errors, minimum=0, maximum=64)
			_valid_string_list(scopes["capabilities"], f"{path}.scopes.capabilities", errors, minimum=1, maximum=64)

		timeout = tool.get("timeout_ms")
		if not isinstance(timeout, int) or isinstance(timeout, bool) or not 100 <= timeout <= 300_000:
			errors.append(f"{path}.timeout_ms must be an integer from 100 to 300000")

		output = tool.get("output_policy")
		output_fields = {"max_bytes", "max_items", "pagination", "cursor_field", "truncation_field", "digest", "digest_field"}
		if _expect_exact_keys(output, output_fields, f"{path}.output_policy", errors):
			if not isinstance(output["max_bytes"], int) or isinstance(output["max_bytes"], bool) or not 256 <= output["max_bytes"] <= 1024 * 1024:
				errors.append(f"{path}.output_policy.max_bytes must be 256-1048576")
			if not isinstance(output["max_items"], int) or isinstance(output["max_items"], bool) or not 1 <= output["max_items"] <= 1000:
				errors.append(f"{path}.output_policy.max_items must be 1-1000")
			if not isinstance(output["pagination"], bool) or not isinstance(output["digest"], bool):
				errors.append(f"{path}.output_policy pagination and digest must be booleans")
			cursor = output["cursor_field"]
			if output["pagination"] and (not isinstance(cursor, str) or not cursor):
				errors.append(f"{path}.output_policy.cursor_field is required with pagination")
			if not output["pagination"] and cursor is not None:
				errors.append(f"{path}.output_policy.cursor_field must be null without pagination")
			if not isinstance(output["truncation_field"], str) or not output["truncation_field"]:
				errors.append(f"{path}.output_policy.truncation_field must name a result field")
			result_properties = tool.get("result_schema", {}).get("properties", {}) if isinstance(tool.get("result_schema"), dict) else {}
			if output["truncation_field"] not in result_properties:
				errors.append(f"{path}.result_schema must expose the truncation field")
			if output["pagination"] and cursor not in result_properties:
				errors.append(f"{path}.result_schema must expose the cursor field")
			digest_field = output["digest_field"]
			if output["digest"]:
				if not isinstance(digest_field, str) or not digest_field:
					errors.append(f"{path}.output_policy.digest_field is required when digest is enabled")
				elif digest_field not in result_properties:
					errors.append(f"{path}.result_schema must expose the digest field")
			elif digest_field is not None:
				errors.append(f"{path}.output_policy.digest_field must be null when digest is disabled")

		idempotency = tool.get("idempotency")
		if _expect_exact_keys(idempotency, {"mode", "key_field", "retry_safe"}, f"{path}.idempotency", errors):
			mode = idempotency["mode"]
			if mode not in {"not_applicable", "optional", "required"}:
				errors.append(f"{path}.idempotency.mode is invalid")
			if not isinstance(idempotency["retry_safe"], bool):
				errors.append(f"{path}.idempotency.retry_safe must be boolean")
			key_field = idempotency["key_field"]
			if mode == "required":
				input_properties = tool.get("input_schema", {}).get("properties", {}) if isinstance(tool.get("input_schema"), dict) else {}
				if not isinstance(key_field, str) or key_field not in input_properties:
					errors.append(f"{path}.idempotency.key_field must name an input property")
			elif key_field is not None:
				errors.append(f"{path}.idempotency.key_field must be null unless mode is required")
			if side_effect in {"write", "external", "destructive"} and mode != "required":
				errors.append(f"{path}.idempotency.mode must be required for side effects")

		telemetry = tool.get("telemetry")
		if _expect_exact_keys(telemetry, {"events", "redact_fields", "record_arguments", "record_result"}, f"{path}.telemetry", errors):
			if _valid_string_list(telemetry["events"], f"{path}.telemetry.events", errors, minimum=2, maximum=7):
				unknown_events = sorted(set(telemetry["events"]) - ALLOWED_TELEMETRY_EVENTS)
				if unknown_events:
					errors.append(f"{path}.telemetry.events has unknown values: {', '.join(unknown_events)}")
				if "attempted" not in telemetry["events"] or not ({"completed", "failed"} & set(telemetry["events"])):
					errors.append(f"{path}.telemetry.events must include attempted and an outcome")
			_valid_string_list(telemetry["redact_fields"], f"{path}.telemetry.redact_fields", errors, minimum=0, maximum=64)
			if telemetry["record_arguments"] not in {"none", "redacted"}:
				errors.append(f"{path}.telemetry.record_arguments must be none or redacted")
			if telemetry["record_result"] not in {"metadata", "redacted"}:
				errors.append(f"{path}.telemetry.record_result must be metadata or redacted")
	return errors


def load_registry(path: Path) -> tuple[Any | None, list[str]]:
	raw, _, error = read_regular_file(path, MAX_REGISTRY_BYTES)
	if error or raw is None:
		return None, [f"registry could not be read: {error}"]
	try:
		return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object), []
	except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
		return None, [f"registry is invalid UTF-8 JSON: {exc}"]


def write_manifest(root: Path, raw_path: str, manifest: dict[str, Any]) -> Path:
	relative = _normalize_relative_path(raw_path)
	target = root.joinpath(*relative.parts)
	try:
		target.parent.resolve(strict=True).relative_to(root)
	except (OSError, ValueError) as exc:
		raise ContextCompilerError("output parent must exist inside the project") from exc
	if _is_link_or_junction(target.parent) or (target.exists() and _is_link_or_junction(target)):
		raise ContextCompilerError("output path cannot contain a symlink or junction")
	content = canonical_json(manifest, pretty=True)
	descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
	try:
		with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
			stream.write(content)
			stream.flush()
			os.fsync(stream.fileno())
		os.replace(temporary_name, target)
	except Exception:
		try:
			os.unlink(temporary_name)
		except OSError:
			pass
		raise
	return target


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Compile bounded Harness context or validate a tool registry")
	subparsers = parser.add_subparsers(dest="command", required=True)
	compile_parser = subparsers.add_parser("compile", help="Build a deterministic context manifest")
	compile_parser.add_argument("--project", required=True, help="Project root")
	compile_parser.add_argument("--task", required=True, help="Current task; at most 16 KiB UTF-8")
	compile_parser.add_argument("--include", action="append", default=[], help="Task-relevant project-relative file; repeatable")
	compile_parser.add_argument("--symbol", action="append", default=[], help="Exact symbol to locate within the bounded scan; repeatable")
	compile_parser.add_argument("--verification", action="append", default=[], help="Project-relative verification metadata file; repeatable")
	compile_parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_CONTENT_BYTES, help="Maximum selected content bytes, including task")
	compile_parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES, help="Maximum file-backed sources considered")
	compile_parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="Maximum tokenizer-independent token estimate")
	compile_parser.add_argument("--max-source-bytes", type=int, default=DEFAULT_MAX_SOURCE_BYTES, help="Maximum bytes read from one file or Git lane")
	compile_parser.add_argument("--scan-bytes", type=int, default=DEFAULT_SCAN_BYTES, help="Maximum bytes scanned for requested symbols")
	compile_parser.add_argument("--output", help="Optional project-relative output path; stdout when omitted")
	registry_parser = subparsers.add_parser("validate-tools", help="Validate a closed, bounded tool registry")
	registry_parser.add_argument("--registry", required=True, help="Tool registry JSON path")
	registry_parser.add_argument("--json", action="store_true", help="Print a machine-readable result")
	return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
	configure_utf8_stdio()
	args = parse_args(argv)
	if args.command == "compile":
		try:
			limits = Limits(args.max_bytes, args.max_files, args.max_tokens, args.max_source_bytes, args.scan_bytes)
			manifest = compile_context(
				args.project,
				args.task,
				includes=args.include,
				symbols=args.symbol,
				verification=args.verification,
				limits=limits,
			)
			if args.output:
				root = Path(args.project).expanduser().resolve(strict=True)
				path = write_manifest(root, args.output, manifest)
				print(json.dumps({"ok": True, "output": relative_locator(root, path), "integrity": manifest["integrity"]["manifest_sha256"]}, ensure_ascii=False))
			else:
				print(canonical_json(manifest, pretty=True), end="")
		except (ContextCompilerError, OSError) as exc:
			print(f"context compilation failed: {exc}", file=sys.stderr)
			return 2
		return 0
	path = Path(args.registry).expanduser()
	try:
		path = path.resolve(strict=True)
	except OSError as exc:
		errors = [f"registry does not exist: {exc}"]
	else:
		registry, errors = load_registry(path)
		if not errors:
			errors = validate_tool_registry(registry)
	result = {"ok": not errors, "errors": errors}
	if args.json:
		print(canonical_json(result, pretty=True), end="")
	elif errors:
		print("Tool registry validation failed:", file=sys.stderr)
		for error in errors:
			print(f"- {error}", file=sys.stderr)
	else:
		print("Tool registry validation passed.")
	return 0 if not errors else 1


if __name__ == "__main__":
	raise SystemExit(main())
