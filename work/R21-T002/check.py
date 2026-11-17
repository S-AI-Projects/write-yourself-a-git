#!/usr/bin/env python3
"""Run native tests and record the cmd_ls_tree argument boundaries checks."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
WYAG = ROOT / "wyag"
report = {"commands": [], "checks": [], "passed": False}
inputs = {
    "staging": {
        "notes.txt": {"initial": "alpha\n", "updated": "alpha updated\n", "expected": "staged"},
        "file with space.txt": {
            "initial": "space initial\n",
            "updated": "space modified\n",
            "expected": "unstaged",
        },
    },
    "argument_boundaries": {
        "minimum_args": "wyag ls-tree HEAD (succeeds with exit 0)",
        "optional_argument": "wyag ls-tree -r HEAD (succeeds with recursive tree entries)",
        "invalid_combination": "wyag ls-tree (fails with status 2, usage message, no state change)",
        "nonexistent_tree": "wyag ls-tree nonexistent_sha (fails non-zero, diagnostic message)",
    },
    "normalization": [
        "Baseline commit dates and author/committer identity are fixed.",
        "Timestamps and author metadata are normalized across Git and wyag.",
    ],
}


def execute(label, args, cwd=ROOT, env=None):
    argv = [str(arg) for arg in args]
    completed = subprocess.run(
        argv, cwd=str(cwd), env=env, text=True, capture_output=True
    )
    report["commands"].append(
        {
            "label": label,
            "args": argv,
            "cwd": str(cwd),
            "exit_status": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    )
    return completed


def expect(condition, message):
    report["checks"].append({"assertion": message, "passed": bool(condition)})
    if not condition:
        raise AssertionError(message)


def git(repo, *args, env, label):
    result = execute(label, ["git", "-C", repo, *args], env=env)
    expect(result.returncode == 0, f"{label} exits successfully")
    return result.stdout


def empty_repo_state(repo):
    index = repo / ".git" / "index"
    head = repo / ".git" / "HEAD"
    refs_dir = repo / ".git" / "refs"
    refs = {}
    if refs_dir.exists():
        for ref in sorted(path for path in refs_dir.rglob("*") if path.is_file()):
            refs[str(ref.relative_to(repo / ".git"))] = ref.read_text()
    return {
        "index_exists": index.exists(),
        "index_sha256": (
            hashlib.sha256(index.read_bytes()).hexdigest() if index.exists() else None
        ),
        "head": head.read_text() if head.exists() else None,
        "refs": refs,
    }


def run_checks():
    versions = {}
    for name, args in (
        ("python", ["python3", "--version"]),
        ("git", ["git", "--version"]),
        ("make", ["make", "--version"]),
        ("emacs", ["emacs", "--version"]),
    ):
        result = execute(f"version: {name}", args)
        expect(result.returncode == 0, f"{name} version command succeeds")
        versions[name] = result.stdout.splitlines()[0]
    report["tool_versions"] = versions

    native = execute("native shell test suite", ["bash", "wyag-tests.sh"])
    expect(native.returncode == 0, "native wyag-tests.sh suite passes")
    expect(
        "ls-tree exercises argument boundaries" in native.stdout,
        "native suite executes the focused ls-tree test",
    )

    git_env = os.environ.copy()
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_CONFIG_GLOBAL"] = os.devnull
    commit_env = git_env.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "cmd_ls_tree test",
            "GIT_AUTHOR_EMAIL": "cmd-ls-tree@example.invalid",
            "GIT_AUTHOR_DATE": "2001-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "cmd_ls_tree test",
            "GIT_COMMITTER_EMAIL": "cmd-ls-tree@example.invalid",
            "GIT_COMMITTER_DATE": "2001-01-01T00:00:00+00:00",
        }
    )

    with tempfile.TemporaryDirectory(prefix="wyag-lstree-boundary-") as temp:
        temp_root = Path(temp)
        wyag_repo = temp_root / "wyag"
        git_repo = temp_root / "git"

        result = execute("initialize wyag repository", [WYAG, "init", wyag_repo])
        expect(result.returncode == 0, "wyag repository initializes")
        result = execute(
            "initialize reference Git repository",
            ["git", "-c", "init.defaultBranch=master", "init", "--quiet", git_repo],
            env=git_env,
        )
        expect(result.returncode == 0, "reference Git repository initializes")

        for repo in (wyag_repo, git_repo):
            (repo / "notes.txt").write_text(inputs["staging"]["notes.txt"]["initial"])
            (repo / "file with space.txt").write_text(
                inputs["staging"]["file with space.txt"]["initial"]
            )
            sub_dir = repo / "sub"
            sub_dir.mkdir()
            (sub_dir / "nested.txt").write_text("nested content\n")
            git(repo, "add", "notes.txt", "file with space.txt", "sub/nested.txt", env=git_env, label="stage initial files")
            git(repo, "commit", "-m", "initial commit", env=commit_env, label="commit initial state")

            # One staged change
            (repo / "notes.txt").write_text(inputs["staging"]["notes.txt"]["updated"])
            git(repo, "add", "notes.txt", env=git_env, label="stage notes update")

            # One unstaged change
            (repo / "file with space.txt").write_text(inputs["staging"]["file with space.txt"]["updated"])

        # Test minimum accepted argument list: wyag ls-tree HEAD
        min_args = execute("wyag ls-tree HEAD", [WYAG, "ls-tree", "HEAD"], cwd=wyag_repo)
        expect(min_args.returncode == 0, "wyag ls-tree HEAD exits with status 0")
        expect("notes.txt" in min_args.stdout, "ls-tree output includes notes.txt")
        expect("file with space.txt" in min_args.stdout, "ls-tree output includes file with space.txt")
        expect("sub" in min_args.stdout, "ls-tree non-recursive shows sub tree entry")
        expect("nested.txt" not in min_args.stdout, "non-recursive ls-tree does not show nested leaf directly")

        # Test optional argument: wyag ls-tree -r HEAD
        opt_args = execute("wyag ls-tree -r HEAD", [WYAG, "ls-tree", "-r", "HEAD"], cwd=wyag_repo)
        expect(opt_args.returncode == 0, "wyag ls-tree -r HEAD exits with status 0")
        expect("sub/nested.txt" in opt_args.stdout, "recursive ls-tree includes sub/nested.txt")

        # Test documented invalid combination: missing required tree argument
        repo_state_before = empty_repo_state(wyag_repo)
        no_args = execute("wyag ls-tree without arguments", [WYAG, "ls-tree"], cwd=wyag_repo)
        repo_state_after = empty_repo_state(wyag_repo)
        expect(no_args.returncode == 2, "wyag ls-tree without arguments exits with status 2")
        expect("the following arguments are required: tree" in no_args.stderr or "required" in no_args.stderr,
               "error message identifies missing tree argument")
        expect(repo_state_before == repo_state_after, "invalid invocation preserves repository state")

        # Test nonexistent object identifier
        nonexistent = execute("wyag ls-tree nonexistent", [WYAG, "ls-tree", "0000000000000000000000000000000000000000"], cwd=wyag_repo)
        expect(nonexistent.returncode != 0, "wyag ls-tree with nonexistent object exits non-zero")


def write_evidence():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    (EVIDENCE / "tool-versions.json").write_text(
        json.dumps(report.get("tool_versions", {}), indent=2) + "\n"
    )
    (EVIDENCE / "results.json").write_text(json.dumps(report, indent=2) + "\n")


try:
    run_checks()
    report["passed"] = True
finally:
    write_evidence()
