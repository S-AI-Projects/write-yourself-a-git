#!/usr/bin/env python3
"""Run native tests and record the tree_to_dict environment isolation checks."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
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
    "environment_isolation": {
        "missing_dependency_branch": "tree_to_dict on unborn HEAD or missing ref returns empty dict cleanly",
        "success_branch": "tree_to_dict on valid commit tree recursively maps paths to blob SHAs",
        "determinism": "Local config isolation (GIT_CONFIG_NOSYSTEM=1, GIT_CONFIG_GLOBAL=/dev/null) ensures identical outputs across runs",
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
        "tree-to-dict isolates environment dependencies" in native.stdout,
        "native suite executes the focused tree-to-dict test",
    )

    git_env = os.environ.copy()
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_CONFIG_GLOBAL"] = os.devnull
    commit_env = git_env.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "tree_to_dict test",
            "GIT_AUTHOR_EMAIL": "tree-to-dict@example.invalid",
            "GIT_AUTHOR_DATE": "2001-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "tree_to_dict test",
            "GIT_COMMITTER_EMAIL": "tree-to-dict@example.invalid",
            "GIT_COMMITTER_DATE": "2001-01-01T00:00:00+00:00",
        }
    )

    with tempfile.TemporaryDirectory(prefix="wyag-treedict-iso-") as temp:
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

        # 1. Check the missing-dependency branch: initial repo before any commit
        # Invoking tree_to_dict on HEAD via python
        sys.path.insert(0, str(ROOT))
        import libwyag
        repo_obj = libwyag.repo_find(str(wyag_repo))
        missing_dict = libwyag.tree_to_dict(repo_obj, "HEAD")
        expect(isinstance(missing_dict, dict), "tree_to_dict returns a dict on missing HEAD")
        expect(len(missing_dict) == 0, "tree_to_dict on missing dependency returns empty dict")

        nonexistent_dict = libwyag.tree_to_dict(repo_obj, "nonexistent-branch-or-tag")
        expect(len(nonexistent_dict) == 0, "tree_to_dict on nonexistent ref returns empty dict")

        # Setup standard fixture
        for repo in (wyag_repo, git_repo):
            (repo / "notes.txt").write_text(inputs["staging"]["notes.txt"]["initial"])
            (repo / "file with space.txt").write_text(
                inputs["staging"]["file with space.txt"]["initial"]
            )
            sub_dir = repo / "sub"
            sub_dir.mkdir()
            (sub_dir / "nested.txt").write_text("nested text\n")
            git(repo, "add", "notes.txt", "file with space.txt", "sub/nested.txt", env=git_env, label="stage initial files")
            git(repo, "commit", "-m", "initial commit", env=commit_env, label="commit initial state")

            # One staged change
            (repo / "notes.txt").write_text(inputs["staging"]["notes.txt"]["updated"])
            git(repo, "add", "notes.txt", env=git_env, label="stage notes update")

            # One unstaged change
            (repo / "file with space.txt").write_text(inputs["staging"]["file with space.txt"]["updated"])

        # 2. Check the success branch: tree_to_dict on valid tree
        success_dict = libwyag.tree_to_dict(repo_obj, "HEAD")
        expect("notes.txt" in success_dict, "success dict contains notes.txt")
        expect("file with space.txt" in success_dict, "success dict contains file with space.txt")
        expect("sub/nested.txt" in success_dict, "success dict recursively contains sub/nested.txt")

        # Verify hashes match git cat-file blob hashes
        notes_blob = git(wyag_repo, "rev-parse", "HEAD:notes.txt", env=git_env, label="get notes blob").strip()
        expect(success_dict["notes.txt"] == notes_blob, "tree_to_dict maps notes.txt to correct blob SHA")

        # 3. Check determinism under isolated environment
        status1 = execute("status run 1", [WYAG, "status"], cwd=wyag_repo, env=git_env)
        status2 = execute("status run 2", [WYAG, "status"], cwd=wyag_repo, env=git_env)
        expect(status1.returncode == 0, "status run 1 succeeds")
        expect(status2.returncode == 0, "status run 2 succeeds")
        expect(status1.stdout == status2.stdout, "isolated environment guarantees deterministic output")


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
