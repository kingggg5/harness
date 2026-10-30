"""Build live-model A/B trials for the Harness router.

usage: build.py --variant LABEL=REF [--variant ...] --task ID [--task ...] [--reps N] [--explicit]
                [--context none|agents|hook] [--label PREFIX] [--out DIR]

REF is a git revision of this repository, "worktree" for the files on disk, or "none" for no best-in-code skill.
Each trial gets OUT/trials/<task>-<variant>-r<n>/ with repo/, skills/ and PROMPT.txt, and OUT/manifest.json lists
every trial built into OUT. Run one agent per trial with the description "<label> <trial-id>" and the PROMPT.txt
text, then score the results with score.py.
"""
import argparse
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

EVALS = Path(__file__).resolve().parents[1]
HARNESS = EVALS.parent
FIXTURE = EVALS / "fixture"
PLUGIN_PATHS = ["skills/best-in-code", "adapters", "hooks", ".claude-plugin", ".codex-plugin"]
SKILL_PATHS = ["SKILL.md", "references", "assets/templates"]
MOCK_ORDER = ["ui-craft", "motion-kit", "library-docs", "security-audit", "slide-deck", "spreadsheet-tools"]
GIT_USER = ["-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid"]
DECISION_SOURCE = "human:product-owner"

PROMPT = """You are acting as a coding agent for a user, inside their repository.

Repository: {repo}
Work only inside {trial}. Do not use the network, install packages, or touch other directories. Browser, GUI and MCP tools are unavailable for this task; verify with local commands only.

Skills installed on this host live in {skills_dir}. A skill is loaded by reading its SKILL.md with the Read tool; paths inside a skill are relative to that skill's folder. Use a skill when its description fits the work.
{skills}

User request:
\"\"\"{task}\"\"\"

Handle the request as you normally would for this user, then end with a short final report to them."""


def run(cmd: list, cwd: Path, data: bytes | None = None, text: bool = True):
	result = subprocess.run(cmd, cwd=cwd, input=data, capture_output=True)
	if result.returncode != 0:
		tail = (result.stdout[-400:] + result.stderr[-400:]).decode("utf-8", "replace")
		raise SystemExit(f"{' '.join(str(c) for c in cmd[:4])} failed in {cwd}: {tail}")
	return result.stdout.decode("utf-8") if text else result.stdout


def remove(path: Path) -> None:
	"""Delete a directory, including the read-only objects git leaves on Windows."""
	def retry(func, target, _exc):
		os.chmod(target, stat.S_IWRITE)
		func(target)
	if path.exists():
		if sys.version_info >= (3, 12):
			shutil.rmtree(path, onexc=retry)
		else:
			shutil.rmtree(path, onerror=retry)


def description(skill_md: Path) -> str:
	for line in skill_md.read_text(encoding="utf-8").splitlines():
		if line.startswith("description:"):
			return line.split(":", 1)[1].strip().strip('"')
	raise SystemExit(f"description not found in {skill_md}")


def export_plugin(dest: Path, ref: str) -> Path:
	"""Copy the parts of the plugin a trial needs, at a git revision or from the working tree."""
	remove(dest)
	if ref == "worktree":
		for rel in PLUGIN_PATHS:
			if (HARNESS / rel).is_dir():
				shutil.copytree(HARNESS / rel, dest / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
		return dest
	run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], HARNESS)
	present = [rel for rel in PLUGIN_PATHS if subprocess.run(["git", "cat-file", "-e", f"{ref}:{rel}"], cwd=HARNESS, capture_output=True).returncode == 0]
	archive = run(["git", "archive", "--format=tar", ref, "--", *present], HARNESS, text=False)
	dest.mkdir(parents=True)
	with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
		try:
			tar.extractall(dest, filter="data")
		except TypeError:
			tar.extractall(dest)
	return dest


def copy_files(source: Path, target: Path) -> None:
	for path in sorted(source.rglob("*")):
		if path.is_file():
			dest = target / path.relative_to(source)
			dest.parent.mkdir(parents=True, exist_ok=True)
			shutil.copyfile(path, dest)


def record_decisions(repo: Path, plugin: Path, decisions: list) -> None:
	scripts = plugin / "skills" / "best-in-code" / "scripts"
	run([sys.executable, "-B", str(scripts / "init_project.py"), "--project", str(repo), "--json"], repo)
	for decision in decisions:
		run([sys.executable, "-B", str(scripts / "memory_ops.py"), "remember", "--project", str(repo), "--scope", "project", "--kind", "decision", "--key", decision["key"], "--value", decision["value"], "--source", DECISION_SOURCE], repo)
	run(["git", *GIT_USER, "add", "-A"], repo)
	run(["git", *GIT_USER, "commit", "-q", "-m", "harness init and decisions"], repo)


def project_context(repo: Path, plugin: Path, mode: str) -> str:
	"""Text Claude Code would load before the request: AGENTS.md through CLAUDE.md, and the SessionStart hook notice."""
	extra = ""
	agents = repo / "AGENTS.md"
	if mode in {"agents", "hook"} and agents.is_file():
		extra += "\nProject instructions loaded automatically from the repository's CLAUDE.md (which imports AGENTS.md):\n\"\"\"\n" + agents.read_text(encoding="utf-8").strip() + "\n\"\"\"\n"
	if mode == "hook":
		notice = run(["node", str(plugin / "hooks" / "session-status.js")], repo, data=json.dumps({"cwd": str(repo)}).encode("utf-8")).strip()
		if notice:
			extra += "\nSession start notice from the Harness plugin hook:\n\"\"\"\n" + notice + "\n\"\"\"\n"
	return extra


def build_trial(out: Path, trial_id: str, task_id: str, task: dict, variant: dict, args) -> dict:
	trial = out / "trials" / trial_id
	remove(trial)
	repo = trial / "repo"
	copy_files(FIXTURE / "base", repo)
	if (FIXTURE / "overlays" / task_id).is_dir():
		copy_files(FIXTURE / "overlays" / task_id, repo)
	run(["git", "init", "-q", "-b", "main"], repo)
	run(["git", *GIT_USER, "add", "-A"], repo)
	run(["git", *GIT_USER, "commit", "-q", "-m", "baseline"], repo)
	if task.get("decisions") or task.get("init"):
		record_decisions(repo, variant["setup"], task.get("decisions", []))
	if (FIXTURE / "pending" / task_id).is_dir():
		copy_files(FIXTURE / "pending" / task_id, repo)

	skills = trial / "skills"
	lines = []
	if variant["plugin"] is not None:
		source = variant["plugin"] / "skills" / "best-in-code"
		for rel in SKILL_PATHS:
			if (source / rel).is_dir():
				shutil.copytree(source / rel, skills / "best-in-code" / rel)
			else:
				(skills / "best-in-code").mkdir(parents=True, exist_ok=True)
				shutil.copyfile(source / rel, skills / "best-in-code" / rel)
		lines.append(f"- best-in-code — {variant['description']}")
	mocks = FIXTURE / "mock-skills"
	names = [n for n in MOCK_ORDER if (mocks / n).is_dir()] + sorted(p.name for p in mocks.iterdir() if p.is_dir() and p.name not in MOCK_ORDER)
	for name in names:
		shutil.copytree(mocks / name, skills / name)
		lines.append(f"- {name} — {description(mocks / name / 'SKILL.md')}")

	if args.explicit:
		request = task.get("explicit_request") or "Harness: " + task["request"]
	else:
		request = task["request"]
	skills_dir = f"{trial}{os.sep}skills{os.sep}<name>{os.sep}SKILL.md"
	prompt = PROMPT.format(repo=repo, trial=trial, skills_dir=skills_dir, skills="\n".join(lines), task=request)
	extra = project_context(repo, variant["setup"], args.context)
	if extra:
		prompt = prompt.replace("\nUser request:", extra + "\nUser request:", 1)
	(trial / "PROMPT.txt").write_text(prompt, encoding="utf-8", newline="\n")
	return {
		"id": trial_id, "variant": variant["label"], "task": task_id, "trial": str(trial), "repo": str(repo), "prompt": prompt,
		"label": args.label, "ref": variant["ref"], "explicit": args.explicit, "context": args.context,
	}


def parse_args():
	parser = argparse.ArgumentParser(description="Build live-model A/B trials for the Harness router")
	parser.add_argument("--variant", action="append", required=True, metavar="LABEL=REF", help="git revision, 'worktree' or 'none'; repeatable")
	parser.add_argument("--task", action="append", required=True, help="task id from evals/tasks.json; repeatable")
	parser.add_argument("--reps", type=int, default=3)
	parser.add_argument("--explicit", action="store_true", help="invoke Harness explicitly (explicit_request, or 'Harness: ' + request)")
	parser.add_argument("--context", choices=["none", "agents", "hook"], default="none", help="project text Claude Code would preload")
	parser.add_argument("--label", default="hab", help="agent description prefix used to match transcripts")
	parser.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "harness-evals")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	tasks = json.loads((EVALS / "tasks.json").read_text(encoding="utf-8"))["tasks"]
	unknown = [t for t in args.task if t not in tasks]
	if unknown:
		raise SystemExit(f"unknown task(s): {', '.join(unknown)}; choose from {', '.join(tasks)}")
	out = args.out.resolve()
	worktree = None
	variants = []
	for spec in args.variant:
		label, sep, ref = spec.partition("=")
		if not sep or not label or not ref:
			raise SystemExit(f"--variant needs LABEL=REF, got {spec!r}")
		plugin = None if ref == "none" else export_plugin(out / "variants" / label, ref)
		if plugin is None and worktree is None:
			worktree = export_plugin(out / "variants" / "_worktree", "worktree")
		variants.append({
			"label": label, "ref": ref, "plugin": plugin, "setup": plugin or worktree,
			"description": description(plugin / "skills" / "best-in-code" / "SKILL.md") if plugin else None,
		})
	built = []
	for rep in range(1, args.reps + 1):
		for task_id in args.task:
			for variant in variants:
				built.append(build_trial(out, f"{task_id}-{variant['label']}-r{rep}", task_id, tasks[task_id], variant, args))
	manifest_path = out / "manifest.json"
	manifest = {t["id"]: t for t in json.loads(manifest_path.read_text(encoding="utf-8"))} if manifest_path.exists() else {}
	manifest.update({t["id"]: t for t in built})
	manifest_path.write_text(json.dumps(list(manifest.values()), ensure_ascii=False, indent=1), encoding="utf-8")
	print(f"built {len(built)} trials in {out}")
	for trial in built:
		print(f"  {args.label} {trial['id']}  ->  {Path(trial['trial']) / 'PROMPT.txt'}")
	return 0


if __name__ == "__main__":
	sys.exit(main())
