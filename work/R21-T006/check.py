#!/usr/bin/env python3
"""Run native tests and record the cmd_init implementation readability checks."""

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
    "implementation_readability": {
        "default_path_contract": "wyag init without path argument defaults explicitly to '.'",
        "explicit_path_contract": "wyag init <path> creates new git repository at target path",
        "structural_invariants": ".git containing HEAD, config, description, objects, refs/heads, refs/tags",
        "error_handling": "wyag init on an existing non-directory file raises clear exception",
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
        "init clarifies one source responsibility" in native.stdout,
        "native suite executes the focused init test",
    )

    git_env = os.environ.copy()
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_CONFIG_GLOBAL"] = os.devnull
    commit_env = git_env.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "cmd_init test",
            "GIT_AUTHOR_EMAIL": "cmd-init@example.invalid",
            "GIT_AUTHOR_DATE": "2001-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "cmd_init test",
            "GIT_COMMITTER_EMAIL": "cmd-init@example.invalid",
            "GIT_COMMITTER_DATE": "2001-01-01T00:00:00+00:00",
        }
    )

    with tempfile.TemporaryDirectory(prefix="wyag-init-readability-") as temp:
        temp_root = Path(temp)
        wyag_repo = temp_root / "wyag"
        git_repo = temp_root / "git"

        # Test explicit path initialization
        result = execute("initialize wyag repository at explicit path", [WYAG, "init", wyag_repo])
        expect(result.returncode == 0, "wyag init with explicit path succeeds")

        result = execute(
            "initialize reference Git repository",
            ["git", "-c", "init.defaultBranch=master", "init", "--quiet", git_repo],
            env=git_env,
        )
        expect(result.returncode == 0, "reference Git repository initializes")

        # Standard fixture setup
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

        # Verify structural invariants of wyag_repo
        expect((wyag_repo / ".git").is_dir(), ".git is a directory")
        expect((wyag_repo / ".git" / "HEAD").is_file(), "HEAD is a file")
        expect((wyag_repo / ".git" / "config").is_file(), "config is a file")
        expect((wyag_repo / ".git" / "description").is_file(), "description is a file")
        expect((wyag_repo / ".git" / "objects").is_dir(), "objects is a directory")
        expect((wyag_repo / ".git" / "refs" / "heads").is_dir(), "refs/heads is a directory")
        expect((wyag_repo / ".git" / "refs" / "tags").is_dir(), "refs/tags is a directory")

        head_content = (wyag_repo / ".git" / "HEAD").read_text()
        expect(head_content.strip() == "ref: refs/heads/master", "HEAD points to ref: refs/heads/master")

        config_content = (wyag_repo / ".git" / "config").read_text()
        expect("repositoryformatversion = 0" in config_content, "config specifies format version 0")

        # Test default path dispatch (no arguments => '.')
        default_dir = temp_root / "default_dir"
        default_dir.mkdir()
        def_result = execute("wyag init in default directory", [WYAG, "init"], cwd=default_dir)
        expect(def_result.returncode == 0, "wyag init with no arguments defaults to current directory")
        expect((default_dir / ".git").is_dir(), "default init created .git in current directory")
        expect((default_dir / ".git" / "HEAD").is_file(), "default init created valid HEAD file")

        # Test characterization of invalid invocation: init on regular file fails
        not_a_dir = temp_root / "dummy.file"
        not_a_dir.write_text("not a directory")
        fail_result = execute("wyag init on regular file", [WYAG, "init", not_a_dir])
        expect(fail_result.returncode != 0, "wyag init on regular file fails non-zero")
        expect("is not a directory" in fail_result.stderr, "error message indicates path is not a directory")


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
