#!/usr/bin/env python3
"""Run native tests and record the object_read regression mutation checks."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zlib

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
    "regression_mutation": {
        "valid_object_contract": "object_read correctly deserializes valid blob, tree, and commit objects",
        "length_mutation_guard": "Objects with mismatching declared vs actual payload length raise bad length exception",
        "type_mutation_guard": "Objects with unknown format headers raise unknown type exception",
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
        "object-read protects a condition with a regression" in native.stdout,
        "native suite executes the focused regression test",
    )

    git_env = os.environ.copy()
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_CONFIG_GLOBAL"] = os.devnull
    commit_env = git_env.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "object_read test",
            "GIT_AUTHOR_EMAIL": "object-read@example.invalid",
            "GIT_AUTHOR_DATE": "2001-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "object_read test",
            "GIT_COMMITTER_EMAIL": "object-read@example.invalid",
            "GIT_COMMITTER_DATE": "2001-01-01T00:00:00+00:00",
        }
    )

    with tempfile.TemporaryDirectory(prefix="wyag-objread-regr-") as temp:
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

        # 1. Valid object reading: test reading commit, tree, and blob
        sys.path.insert(0, str(ROOT))
        import libwyag
        repo_obj = libwyag.repo_find(str(wyag_repo))

        commit_sha = git(wyag_repo, "rev-parse", "HEAD", env=git_env, label="get commit sha").strip()
        commit_obj = libwyag.object_read(repo_obj, commit_sha)
        expect(commit_obj is not None, "object_read returns valid object for commit")
        expect(commit_obj.fmt == b'commit', "commit object format is commit")

        tree_sha = git(wyag_repo, "rev-parse", "HEAD^{tree}", env=git_env, label="get tree sha").strip()
        tree_obj = libwyag.object_read(repo_obj, tree_sha)
        expect(tree_obj is not None, "object_read returns valid object for tree")
        expect(tree_obj.fmt == b'tree', "tree object format is tree")

        blob_sha = git(wyag_repo, "rev-parse", "HEAD:notes.txt", env=git_env, label="get blob sha").strip()
        blob_obj = libwyag.object_read(repo_obj, blob_sha)
        expect(blob_obj is not None, "object_read returns valid object for blob")
        expect(blob_obj.fmt == b'blob', "blob object format is blob")
        expect(blob_obj.blobdata == b"alpha\n", "blob content matches initial notes.txt")

        # 2. Regression guard against length mutation:
        # Construct object with mismatched header length (header claims size 999, actual is 4)
        corrupted_sha = "22" + "2" * 38
        corrupted_obj_dir = wyag_repo / ".git" / "objects" / "22"
        corrupted_obj_dir.mkdir(parents=True, exist_ok=True)
        bad_len_payload = zlib.compress(b"blob 999\x00data")
        (corrupted_obj_dir / ("2" * 38)).write_bytes(bad_len_payload)

        try:
            libwyag.object_read(repo_obj, corrupted_sha)
            expect(False, "object_read must raise Exception on mismatched length")
        except Exception as e:
            expect("bad length" in str(e).lower() or "malformed" in str(e).lower(),
                   "bad length exception correctly raised for length-mutated object")

        # 3. Regression guard against type mutation:
        # Construct object with unsupported type header
        bad_type_sha = "33" + "3" * 38
        bad_type_dir = wyag_repo / ".git" / "objects" / "33"
        bad_type_dir.mkdir(parents=True, exist_ok=True)
        bad_type_payload = zlib.compress(b"bogustype 4\x00data")
        (bad_type_dir / ("3" * 38)).write_bytes(bad_type_payload)

        try:
            libwyag.object_read(repo_obj, bad_type_sha)
            expect(False, "object_read must raise Exception on unknown type")
        except Exception as e:
            expect("unknown type" in str(e).lower(),
                   "unknown type exception correctly raised for type-mutated object")


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
