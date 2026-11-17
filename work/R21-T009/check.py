#!/usr/bin/env python3
"""Run native tests and record the cmd_log tooling integration checks."""

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
    "tooling_integration": {
        "repeatable_entry_point": "wyag log traverses commit history and produces valid Graphviz digraph",
        "failure_propagation": "Nonexistent commit references fail non-zero with error diagnostic",
        "isolation": "Command executes independently without network or external services",
        "temporary_state": "All fixtures and outputs are isolated in temporary directory structures",
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
        "log integrates a focused check" in native.stdout,
        "native suite executes the focused log check",
    )

    git_env = os.environ.copy()
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_CONFIG_GLOBAL"] = os.devnull
    commit_env = git_env.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "cmd_log test",
            "GIT_AUTHOR_EMAIL": "cmd-log@example.invalid",
            "GIT_AUTHOR_DATE": "2001-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "cmd_log test",
            "GIT_COMMITTER_EMAIL": "cmd-log@example.invalid",
            "GIT_COMMITTER_DATE": "2001-01-01T00:00:00+00:00",
        }
    )

    with tempfile.TemporaryDirectory(prefix="wyag-log-integ-") as temp:
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
            git(repo, "commit", "-m", "first commit message", env=commit_env, label="commit initial state")

            # One staged change
            (repo / "notes.txt").write_text(inputs["staging"]["notes.txt"]["updated"])
            git(repo, "add", "notes.txt", env=git_env, label="stage notes update")

            # One unstaged change
            (repo / "file with space.txt").write_text(inputs["staging"]["file with space.txt"]["updated"])

        c1_sha = git(wyag_repo, "rev-parse", "HEAD", env=git_env, label="get c1 sha").strip()

        # Add a second commit in wyag_repo
        c2_env = commit_env.copy()
        c2_env["GIT_AUTHOR_DATE"] = "2001-01-01T01:00:00+00:00"
        c2_env["GIT_COMMITTER_DATE"] = "2001-01-01T01:00:00+00:00"
        (wyag_repo / "second.txt").write_text("second content\n")
        git(wyag_repo, "add", "second.txt", env=git_env, label="stage second file")
        git(wyag_repo, "commit", "-m", "second commit message", env=c2_env, label="commit second state")
        c2_sha = git(wyag_repo, "rev-parse", "HEAD", env=git_env, label="get c2 sha").strip()

        # 1. Success check: default log starts at HEAD
        log_res = execute("wyag log HEAD", [WYAG, "log"], cwd=wyag_repo)
        expect(log_res.returncode == 0, "wyag log exits with code 0")
        expect("digraph wyaglog" in log_res.stdout, "log stdout contains digraph wyaglog")
        expect(f"c_{c1_sha}" in log_res.stdout, "digraph includes c1 node")
        expect(f"c_{c2_sha}" in log_res.stdout, "digraph includes c2 node")
        expect("first commit message" in log_res.stdout, "digraph includes first commit message")
        expect("second commit message" in log_res.stdout, "digraph includes second commit message")

        # 2. Success check: explicit commit argument
        explicit_log = execute("wyag log explicit c1", [WYAG, "log", c1_sha], cwd=wyag_repo)
        expect(explicit_log.returncode == 0, "wyag log with explicit commit sha exits code 0")
        expect(f"c_{c1_sha}" in explicit_log.stdout, "explicit log includes c1 node")
        expect(f"c_{c2_sha}" not in explicit_log.stdout, "log starting at c1 does not include c2")

        # 3. Failure propagation: nonexistent commit reference
        fail_log = execute("wyag log nonexistent", [WYAG, "log", "0000000000000000000000000000000000000000"], cwd=wyag_repo)
        expect(fail_log.returncode != 0, "wyag log with invalid commit exits non-zero")
        expect("No such reference" in fail_log.stderr or "Exception" in fail_log.stderr,
               "error diagnostic explains missing reference")


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
