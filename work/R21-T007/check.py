#!/usr/bin/env python3
"""Run native tests and record the cmd_status executable documentation checks."""

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
    "executable_documentation": {
        "scenario": "Repository on master with one staged modification and one unstaged worktree change",
        "output_verification": "Status reports active branch, changes to be committed, and changes not staged for commit",
        "state_invariance": "Running status leaves index, worktree, and references strictly unchanged",
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


def capture_repo_state(repo):
    index = repo / ".git" / "index"
    head = repo / ".git" / "HEAD"
    return {
        "index_bytes": hashlib.sha256(index.read_bytes()).hexdigest() if index.exists() else None,
        "head_text": head.read_text() if head.exists() else None,
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
        "status publishes a tested usage example" in native.stdout,
        "native suite executes the focused status test",
    )

    git_env = os.environ.copy()
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_CONFIG_GLOBAL"] = os.devnull
    commit_env = git_env.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "cmd_status test",
            "GIT_AUTHOR_EMAIL": "cmd-status@example.invalid",
            "GIT_AUTHOR_DATE": "2001-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "cmd_status test",
            "GIT_COMMITTER_EMAIL": "cmd-status@example.invalid",
            "GIT_COMMITTER_DATE": "2001-01-01T00:00:00+00:00",
        }
    )

    with tempfile.TemporaryDirectory(prefix="wyag-status-doc-") as temp:
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
            git(repo, "add", "notes.txt", "file with space.txt", env=git_env, label="stage initial files")
            git(repo, "commit", "-m", "initial commit", env=commit_env, label="commit initial state")

            # One staged change
            (repo / "notes.txt").write_text(inputs["staging"]["notes.txt"]["updated"])
            git(repo, "add", "notes.txt", env=git_env, label="stage notes update")

            # One unstaged change
            (repo / "file with space.txt").write_text(inputs["staging"]["file with space.txt"]["updated"])

        state_before = capture_repo_state(wyag_repo)

        # Execute wyag status and verify output matches documented usage example
        status_result = execute("wyag status usage example", [WYAG, "status"], cwd=wyag_repo)
        expect(status_result.returncode == 0, "wyag status exits successfully with status 0")
        expect("On branch master" in status_result.stdout, "status reports 'On branch master'")
        expect("Changes to be committed:" in status_result.stdout, "status reports 'Changes to be committed:'")
        expect("notes.txt" in status_result.stdout, "staged file notes.txt is reported under staged changes")
        expect("Changes not staged for commit:" in status_result.stdout, "status reports 'Changes not staged for commit:'")
        expect("file with space.txt" in status_result.stdout, "unstaged file with space.txt is reported under unstaged changes")

        state_after = capture_repo_state(wyag_repo)
        expect(state_before == state_after, "status is idempotent and does not modify index or HEAD")


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
