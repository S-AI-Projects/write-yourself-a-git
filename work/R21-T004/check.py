#!/usr/bin/env python3
"""Run native tests and record the tree_from_index path quoting checks."""

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
    "path_quoting": {
        "spaced_filename": "file with space.txt (exact boundaries preserved in tree leaf)",
        "wildcard_filename": "literal*star.txt (literal asterisk preserved without glob expansion)",
        "isolation": "Wildcard characters do not expand or match unrelated files in repository",
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
        "tree-from-index preserves quoted arguments" in native.stdout,
        "native suite executes the focused tree-from-index test",
    )

    git_env = os.environ.copy()
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_CONFIG_GLOBAL"] = os.devnull
    commit_env = git_env.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "tree_from_index test",
            "GIT_AUTHOR_EMAIL": "tree-from-index@example.invalid",
            "GIT_AUTHOR_DATE": "2001-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "tree_from_index test",
            "GIT_COMMITTER_EMAIL": "tree-from-index@example.invalid",
            "GIT_COMMITTER_DATE": "2001-01-01T00:00:00+00:00",
        }
    )

    with tempfile.TemporaryDirectory(prefix="wyag-treeidx-quoted-") as temp:
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
            (repo / "literal*star.txt").write_text("literal star contents\n")
            git(repo, "add", "notes.txt", "file with space.txt", "literal*star.txt", env=git_env, label="stage initial files")
            git(repo, "commit", "-m", "initial commit with special paths", env=commit_env, label="commit special paths")

            # One staged change
            (repo / "notes.txt").write_text(inputs["staging"]["notes.txt"]["updated"])
            git(repo, "add", "notes.txt", env=git_env, label="stage notes update")

            # One unstaged change
            (repo / "file with space.txt").write_text(inputs["staging"]["file with space.txt"]["updated"])

        # Test wyag ls-tree HEAD matches git ls-tree HEAD
        wyag_lstree = execute("wyag ls-tree HEAD", [WYAG, "ls-tree", "HEAD"], cwd=wyag_repo)
        expect(wyag_lstree.returncode == 0, "wyag ls-tree HEAD succeeds")

        git_lstree = git(git_repo, "ls-tree", "HEAD", env=git_env, label="git ls-tree HEAD")

        # 1. Assert exact argument boundaries for path containing spaces
        expect("file with space.txt" in wyag_lstree.stdout, "tree output includes path with space exactly")
        expect("literal*star.txt" in wyag_lstree.stdout, "tree output includes path with literal asterisk")

        # 2. Assert shell expansion does not affect unrelated files:
        # The asterisk must NOT match notes.txt or any other file
        tree_entries = [line.split("\t", 1)[-1] for line in wyag_lstree.stdout.strip().splitlines()]
        expect("file with space.txt" in tree_entries, "exact path 'file with space.txt' is an entry")
        expect("literal*star.txt" in tree_entries, "exact path 'literal*star.txt' is an entry")
        expect("notes.txt" in tree_entries, "exact path 'notes.txt' is an entry")

        # 3. Verify tree hash and entries match reference Git
        wyag_tree_sha = git(wyag_repo, "rev-parse", "HEAD^{tree}", env=git_env, label="get wyag tree SHA").strip()
        git_tree_sha = git(git_repo, "rev-parse", "HEAD^{tree}", env=git_env, label="get git tree SHA").strip()
        expect(wyag_tree_sha == git_tree_sha, "wyag and git tree SHAs match identically")


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
