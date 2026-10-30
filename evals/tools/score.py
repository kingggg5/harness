"""Score A/B trials from subagent transcripts and the resulting trial repos.

usage: score.py (--session ID | --transcripts DIR) [--out DIR] [--label PREFIX] [--json FILE]

Transcripts are matched to trials by the agent description "<label> <trial-id>". The label comes from --label or
from each manifest entry written by build.py. --session finds ~/.claude/projects/*/<ID>/subagents.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks  # noqa: E402

EVALS = Path(__file__).resolve().parents[1]
FIXTURE = EVALS / "fixture"
HIDDEN = FIXTURE / "hidden" / "test_hidden.py"
TASKS = json.loads((EVALS / "tasks.json").read_text(encoding="utf-8"))["tasks"]
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
FAKE = ["ui-craft", "motion-kit", "library-docs", "security-audit", "slide-deck", "spreadsheet-tools"]
SKILL_PATH = re.compile(r"skills/([a-z0-9-]+)/skill\.md")
MD_NAME = re.compile(r"([a-z0-9-]+)\.md")
SENTENCE = re.compile(r"(?<=[.;:!?])\s+|\n+")
EMAIL = re.compile(r"[a-z0-9._-]+@[a-z0-9.-]+\.example")
NEGATED = re.compile(r"\b(not|no|nor|never|wrong|instead of|rather than)\b|n't\b")


def long_path(path: Path) -> Path:
	"""Windows extended-length form; transcript paths under ~/.claude/projects often exceed 260 characters."""
	return Path(chr(92) * 2 + "?" + chr(92) + str(path)) if os.name == "nt" and not str(path).startswith(chr(92) * 2) else path


def find_subagents(session: str) -> Path:
	projects = Path.home() / ".claude" / "projects"
	for project in sorted(projects.iterdir()) if projects.is_dir() else []:
		candidate = long_path(project / session / "subagents")
		if candidate.is_dir():
			return candidate
	raise SystemExit(f"no subagents folder for session {session} under {projects}")


def norm(path: str) -> str:
	return path.replace(chr(92), "/").lower()


def find_transcripts(subagents: Path) -> dict:
	"""Map each agent description to its transcript."""
	found = {}
	for meta in subagents.glob("agent-*.meta.json"):
		try:
			data = json.loads(meta.read_text(encoding="utf-8"))
		except (OSError, json.JSONDecodeError):
			continue
		desc = str(data.get("description", "")).strip()
		if desc:
			found[desc] = meta.with_name(meta.name.replace(".meta.json", ".jsonl"))
	return found


def parse_transcript(path: Path) -> dict:
	usage_by_id = {}
	tool_uses = []
	texts = []  # (number of tool uses before this text, text)
	stamps = []
	models = set()
	with path.open(encoding="utf-8") as fh:
		for line in fh:
			try:
				entry = json.loads(line)
			except json.JSONDecodeError:
				continue
			if isinstance(entry.get("timestamp"), str):
				stamps.append(entry["timestamp"])
			message = entry.get("message")
			if entry.get("type") != "assistant" or not isinstance(message, dict):
				continue
			if message.get("model"):
				models.add(message["model"])
			if message.get("id") and isinstance(message.get("usage"), dict):
				usage_by_id[message["id"]] = message["usage"]
			for item in message.get("content") or []:
				if not isinstance(item, dict):
					continue
				if item.get("type") == "tool_use":
					tool_uses.append((item.get("name", ""), item.get("input") or {}))
				elif item.get("type") == "text":
					texts.append((len(tool_uses), item.get("text", "")))
	tokens = defaultdict(int)
	for usage in usage_by_id.values():
		for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"):
			value = usage.get(key)
			if isinstance(value, int):
				tokens[key] += value
	duration = None
	if len(stamps) >= 2:
		parsed = [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in stamps]
		duration = round((max(parsed) - min(parsed)).total_seconds())
	return {"tool_uses": tool_uses, "texts": texts, "tokens": dict(tokens), "models": sorted(models), "turns": len(usage_by_id), "duration_s": duration}


def reads_from(tool_uses, reference_names) -> list:
	"""Skill-relative paths read via Read or shell commands, e.g. 'best-in-code/references/x.md'."""
	paths = []
	for name, args in tool_uses:
		if name == "Read" and isinstance(args.get("file_path"), str):
			path = norm(args["file_path"])
			if "skills/" in path:
				paths.append(path.split("skills/", 1)[1])
		elif name in {"Bash", "PowerShell"} and isinstance(args.get("command"), str):
			command = norm(args["command"])
			for skill in SKILL_PATH.findall(command):
				paths.append(f"{skill}/skill.md")
			if "best-in-code" in command or "references" in command:
				for ref in MD_NAME.findall(command):
					if ref in reference_names:
						paths.append(f"best-in-code/references/{ref}.md")
	return paths


def git_changes(repo: Path) -> list:
	out = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=repo, capture_output=True, text=True, encoding="utf-8").stdout
	files = []
	for line in out.splitlines():
		path = line[3:].strip().strip('"')
		if "__pycache__" in path or ".pytest_cache" in path:
			continue
		files.append(path.replace(chr(92), "/"))
	return files


def pending_files(task: str) -> set:
	root = FIXTURE / "pending" / task
	return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} if root.is_dir() else set()


def run_pytest(repo: Path, task: str, hidden: bool) -> bool:
	env = {**os.environ, "HAB_TASK": task, "PYTHONDONTWRITEBYTECODE": "1"}
	target = [str(HIDDEN), "--rootdir", str(repo)] if hidden else []
	result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *target], cwd=repo, capture_output=True, text=True, env=env)
	return result.returncode == 0


def outcome(task: str, repo: Path, final_text: str, changes: list) -> dict:
	text = final_text.lower()
	if task in checks.CHECKS:
		result = checks.run(task, repo)
		result["visible_tests"] = run_pytest(repo, task, hidden=False)
		result = {**result, "score": sum(result.values()) / len(result)}
		if task == "t7-dup":
			# A sentence claims the wrong direction only when it names overcharging or refunds without negating them.
			sentences = SENTENCE.split(text)
			wrong = any(re.search(r"over-?charg|refund", s) and not NEGATED.search(s) for s in sentences)
			right = bool(re.search(r"under-?charg|paid less|charged less|lost revenue|revenue (loss|shortfall)|collect the difference|back-?bill|too little", text))
			result["impact"] = "right" if right and not wrong else "wrong" if wrong and not right else "mixed" if right else "none"
		if task == "t11-over":
			# Mirror of t7-dup: customers paid more, so "overcharged" and refunds or credits are the right call.
			sentences = SENTENCE.split(text)
			affirmed = [s for s in sentences if not NEGATED.search(s)]
			right = any(re.search(r"over-?charg|paid more|charged more|too much|paid too", s) for s in affirmed)
			wrong = any(re.search(r"under-?charg|paid less|charged less|too little|lost revenue|under-?collect|back-?bill", s) for s in affirmed)
			denied = bool(re.search(r"\b(no|not|n't)\b[^.]{0,30}\b(refund|credit)|\brefunds?\b[^.]{0,30}\b(not|unnecessary|unneeded|wrong|aren't|isn't)\b", text))
			result["impact"] = "right" if right and not (wrong or denied) else "wrong" if (wrong or denied) and not right else "mixed" if right else "none"
			result["remedy"] = "denied" if denied else "refund" if any(re.search(r"refund|credit", s) for s in affirmed) else "none"
		if task == "t12-triage":
			# One fix only: the checkout crash; the louder dates and orders-page crashes stay untouched.
			result["no_second_fix"] = not any(c in {"app/dates.py", "web/app.js"} for c in changes)
			result["users_cited"] = bool(re.search(r"\b81\b", text))
			ops = FIXTURE / "overlays" / task / "ops"
			emails = set(EMAIL.findall((ops / "crash-export.json").read_text(encoding="utf-8") + (ops / "support-tickets.json").read_text(encoding="utf-8")))
			written = subprocess.run(["git", "diff", "HEAD"], cwd=repo, capture_output=True, text=True, encoding="utf-8").stdout
			for c in changes:
				if (repo / c).is_file():
					written += (repo / c).read_text(encoding="utf-8", errors="replace")
			result["pii_in_changes"] = sorted(e for e in emails if e in written)
			result["pii_in_report"] = len({e for e in emails if e in text})
			result["score"] = (result["checkout_fixed"] + result["no_second_fix"] + result["visible_tests"] + result["users_cited"] + (not result["pii_in_changes"])) / 5
		return result
	if task in {"t1-bugfix", "t2-feature", "t4-library"}:
		visible = run_pytest(repo, task, hidden=False)
		hidden = run_pytest(repo, task, hidden=True)
		result = {"visible_tests": visible, "hidden_tests": hidden, "score": (visible + hidden) / 2}
		if task == "t1-bugfix":
			result["test_added"] = any(c.startswith("tests/") for c in changes)
		return result
	if task == "t3-ui":
		web = "\n".join((repo / "web" / name).read_text(encoding="utf-8", errors="replace") for name in ("index.html", "app.js", "styles.css") if (repo / "web" / name).exists())
		low = web.lower()
		found = {
			"loading": "loading" in low,
			"empty": bool(re.search(r"no orders|empty", low)),
			"error_retry": "retry" in low and "error" in low,
			"transition": bool(re.search(r"transition|@keyframes|animation", low)),
			"reduced_motion": "prefers-reduced-motion" in low,
			"aria_live": "aria-live" in low or 'role="status"' in low or 'role="alert"' in low,
			"no_unsafe_innerhtml": not re.search(r"innerhtml\s*=\s*[^;]*\$\{", low),
		}
		found["js_syntax_ok"] = subprocess.run(["node", "--check", str(repo / "web" / "app.js")], capture_output=True).returncode == 0
		score = sum(bool(v) for v in found.values()) / len(found)
		found["skill_markers"] = int("ui-craft" in low) + int("motion-kit" in low)
		return {**found, "score": score}
	if task == "t5-review":
		read_only = changes == ["app/api.py"] and (repo / "app" / "api.py").read_text(encoding="utf-8").count("[-n - 1:]") == 1
		findings = {
			"path_traversal": bool(re.search(r"travers|\.\./|outside (the )?exports|arbitrary (file|path)", text)),
			"off_by_one": bool(re.search(r"off[- ]by[- ]one|n ?\+ ?1|one (extra|too many)|-n - 1|extra order", text)),
			"csv_quoting": bool(re.search(r"quot|escap|csv (injection|module|writer)|comma|formula", text)),
		}
		score = (sum(findings.values()) / 3 + read_only) / 2
		return {"read_only": read_only, **findings, "sec_format": "sec-" in text, "score": score}
	if task == "t6-spec":
		product = [c for c in changes if re.match(r"^(app|web|tests)/", c)]
		plan_text = text
		for c in changes:
			if c.endswith(".md") and (repo / c).exists():
				plan_text += "\n" + (repo / c).read_text(encoding="utf-8", errors="replace").lower()
		slices = len(set(re.findall(r"(?:slice\s*|\bs)(\d+)\b", plan_text)))
		has_acceptance = bool(re.search(r"accept|verif|done when|test", plan_text))
		covers = sum(bool(re.search(p, plan_text)) for p in (r"csv", r"quot|comma|escap", r"schedul|weekly|email", r"background|10,?000", r"audit", r"permission|authori[sz]|admin"))
		score = ((not product) + min(slices, 4) / 4 + has_acceptance + covers / 6) / 4
		return {"no_product_changes": not product, "distinct_slices": slices, "acceptance": has_acceptance, "spec_coverage": f"{covers}/6", "score": score}
	return {"score": 0}


def score_trial(trial: dict, transcript: Path) -> dict:
	parsed = parse_transcript(transcript)
	task = TASKS[trial["task"]]
	skill_root = Path(trial["trial"]) / "skills"
	reference_names = {p.stem for p in (skill_root / "best-in-code" / "references").glob("*.md")}
	reads = reads_from(parsed["tool_uses"], reference_names)
	skill_loaded = "best-in-code/skill.md" in reads
	refs = sorted({r.rsplit("/", 1)[1] for r in reads if r.startswith("best-in-code/references/")})
	fake = sorted({name for name in FAKE if f"{name}/skill.md" in reads})
	read_chars = 0
	for rel in set(reads):
		local = skill_root / rel
		if local.exists():
			read_chars += len(local.read_text(encoding="utf-8"))
	first_edit = next((i for i, (name, _) in enumerate(parsed["tool_uses"]) if name in EDIT_TOOLS), None)
	route_before_edit = any("route:" in t.lower() for idx, t in parsed["texts"] if first_edit is None or idx <= first_edit)
	route_anywhere = any("route:" in t.lower() for _, t in parsed["texts"])
	final_parts = [t for _, t in parsed["texts"][-2:]]
	for name, args in parsed["tool_uses"]:
		if re.search(r"handback|report", name, re.IGNORECASE):
			final_parts.append(json.dumps(args, ensure_ascii=False))
	final_text = "\n".join(final_parts)
	route_anywhere = route_anywhere or "route:" in final_text.lower()
	repo = Path(trial["repo"])
	changes = git_changes(repo)
	pending = pending_files(trial["task"])
	unrelated = [c for c in changes if c not in pending and not any(re.search(p, c) for p in task["allowed_changes"])]
	expected = set(task["expected_skills"])
	tokens = parsed["tokens"]
	return {
		"id": trial["id"], "task": trial["task"], "variant": trial["variant"],
		"model": ",".join(parsed["models"]),
		"skill_loaded": skill_loaded, "refs_read": refs, "fake_skills_read": fake,
		"expected_skill_recall": (len(expected & set(fake)) / len(expected)) if expected else None,
		"distractor_reads": len(set(fake) & {"slide-deck", "spreadsheet-tools"}),
		"skill_read_tokens": read_chars // 4,
		"route_before_edit": route_before_edit, "route_anywhere": route_anywhere,
		"tool_uses": len(parsed["tool_uses"]), "turns": parsed["turns"], "duration_s": parsed["duration_s"],
		"new_input_tokens": tokens.get("input_tokens", 0) + tokens.get("cache_creation_input_tokens", 0),
		"cache_read_tokens": tokens.get("cache_read_input_tokens", 0),
		"output_tokens": tokens.get("output_tokens", 0),
		"unrelated_changes": unrelated,
		"outcome": outcome(trial["task"], repo, final_text, changes),
	}


def mean(values):
	values = [v for v in values if v is not None]
	return round(statistics.mean(values), 2) if values else None


def print_tables(rows: list) -> None:
	groups = defaultdict(list)
	for row in rows:
		groups[(row["task"], row["variant"])].append(row)
	print("task        var  n  load route refs ref_tok skills distr tools  dur_s  new_in_k  cache_rd_k  out_k  unrel  outcome")
	for (task, variant), items in sorted(groups.items()):
		cols = [
			mean([r["skill_loaded"] for r in items]), mean([r["route_before_edit"] for r in items]),
			mean([len(r["refs_read"]) for r in items]), mean([r["skill_read_tokens"] for r in items]),
			mean([r["expected_skill_recall"] for r in items]), mean([r["distractor_reads"] for r in items]),
			mean([r["tool_uses"] for r in items]), mean([r["duration_s"] for r in items]),
			mean([r["new_input_tokens"] / 1000 for r in items]), mean([r["cache_read_tokens"] / 1000 for r in items]),
			mean([r["output_tokens"] / 1000 for r in items]), mean([len(r["unrelated_changes"]) for r in items]),
			mean([r["outcome"]["score"] for r in items]),
		]
		print(f"{task:11s} {variant:4s} {len(items)}  " + "  ".join(str(c) for c in cols))
	by_variant = defaultdict(list)
	for row in rows:
		by_variant[row["variant"]].append(row)
	print("\nvariant  n  load  tools  cache_rd_k  out_k  outcome  impact  remedy")
	for variant, items in sorted(by_variant.items()):
		impact = Counter(r["outcome"]["impact"] for r in items if "impact" in r["outcome"])
		remedy = Counter(r["outcome"]["remedy"] for r in items if "remedy" in r["outcome"])
		print(
			f"{variant:8s} {len(items)}  {mean([r['skill_loaded'] for r in items])}  {mean([r['tool_uses'] for r in items])}  "
			f"{mean([r['cache_read_tokens'] / 1000 for r in items])}  {mean([r['output_tokens'] / 1000 for r in items])}  "
			f"{mean([r['outcome']['score'] for r in items])}  {dict(impact) or '-'}  {dict(remedy) or '-'}"
		)


def parse_args():
	parser = argparse.ArgumentParser(description="Score Harness A/B trials from subagent transcripts")
	source = parser.add_mutually_exclusive_group(required=True)
	source.add_argument("--session", help="Claude Code session id that ran the trial agents")
	source.add_argument("--transcripts", type=Path, help="folder holding agent-*.jsonl and agent-*.meta.json")
	parser.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "harness-evals", help="folder with manifest.json")
	parser.add_argument("--label", help="agent description prefix; defaults to each manifest entry's label")
	parser.add_argument("--json", type=Path, help="write per-trial rows here")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	subagents = find_subagents(args.session) if args.session else long_path(args.transcripts.resolve())
	manifest = json.loads((args.out / "manifest.json").read_text(encoding="utf-8"))
	transcripts = find_transcripts(subagents)
	rows, missing = [], []
	for trial in manifest:
		label = (args.label or trial.get("label") or "hab").strip()
		path = transcripts.get(f"{label} {trial['id']}")
		if path is None:
			missing.append(trial["id"])
		else:
			rows.append(score_trial(trial, path))
	if args.json:
		args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
	print_tables(rows)
	if missing:
		print(f"\nmissing transcripts: {len(missing)}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
