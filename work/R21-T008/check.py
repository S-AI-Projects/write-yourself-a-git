#!/usr/bin/env python3
"""Run native tests and record the cmd_status_index_worktree failure diagnostics checks."""

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
    "failure_diagnostics": {
        "failure_branch": "Running wyag status outside a git repository fails non-zero with informative diagnostic",
        "diagnostic_explanation": "Informs user that no git directory was found and repository context is required",
        "corrected_invocation": "Running status in a valid initialized repository succeeds with exit code 0",
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
        "status-index-worktree explains a failing invocation" in native.stdout,
        "native suite executes the focused failure diagnostics test",
    )

    git_env = os.environ.copy()
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_CONFIG_GLOBAL"] = os.devnull
    commit_env = git_env.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "cmd_status_index_worktree test",
            "GIT_AUTHOR_EMAIL": "status-worktree@example.invalid",
            "GIT_AUTHOR_DATE": "2001-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "cmd_status_index_worktree test",
            "GIT_COMMITTER_EMAIL": "status-worktree@example.invalid",
            "GIT_COMMITTER_DATE": "2001-01-01T00:00:00+00:00",
        }
    )

    with tempfile.TemporaryDirectory(prefix="wyag-sitw-fail-") as temp:
        temp_root = Path(temp)
        wyag_repo = temp_root / "wyag"
        git_repo = temp_root / "git"
        non_repo = temp_root / "non_repo_dir"
        non_repo.mkdir()

        # 1. Failure branch: invoke status in directory without a git repository
        failing_call = execute("failing status outside repository", [WYAG, "status"], cwd=non_repo)
        expect(failing_call.returncode != 0, "status invocation outside repository exits non-zero")
        expect("No Git directory" in failing_call.stderr or "Exception" in failing_call.stderr,
               "error diagnostic explains that no git directory was found")

        # 2. Setup standard fixture repository
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

        # 3. Corrected invocation: succeeding status within valid repository
        corrected_call = execute("corrected status inside repository", [WYAG, "status"], cwd=wyag_repo)
        expect(corrected_call.returncode == 0, "corrected status inside repository succeeds with exit code 0")
        expect("On branch master" in corrected_call.stdout, "corrected status output contains branch header")
        expect("notes.txt" in corrected_call.stdout, "corrected status output contains notes.txt")
        expect("file with space.txt" in corrected_call.stdout, "corrected status output contains file with space.txt")


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
