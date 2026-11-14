#!/usr/bin/env python3
from datetime import datetime, timezone
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import libwyag


def get_tool_versions():
    git_ver = subprocess.check_output(["git", "--version"], text=True).strip()
    py_ver = sys.version.replace("\n", " ")
    wyag_path = os.path.join(REPO_ROOT, "wyag")
    return {
        "python": py_ver,
        "git": git_ver,
        "wyag_path": wyag_path
    }


def record_native_tests():
    return [
        "Create repos",
        "status",
        "hash-object",
        "hash-object -w",
        "cat-file",
        "cat-file with long hash",
        "Create commit",
        "cat-file on commit object without indirection",
        "cat-file on tree object redirected from commit",
        "Add some directories and commits",
        "ls-tree",
        "checkout",
        "rev-parse",
        "ls-files",
        "gitignore"
    ]


def setup_temp_repo(work_dir):
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    env["GIT_AUTHOR_NAME"] = "Pritpal Singh"
    env["GIT_AUTHOR_EMAIL"] = "pritpal@example.com"
    env["GIT_AUTHOR_DATE"] = "2026-11-14 00:00:00 +0530"
    env["GIT_COMMITTER_NAME"] = "Pritpal Singh"
    env["GIT_COMMITTER_EMAIL"] = "pritpal@example.com"
    env["GIT_COMMITTER_DATE"] = "2026-11-14 00:00:00 +0530"

    repo_path = os.path.join(work_dir, "test_repo")
    os.makedirs(repo_path, exist_ok=True)

    subprocess.run(["git", "init"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    notes_file = os.path.join(repo_path, "notes.txt")
    with open(notes_file, "w", encoding="utf-8") as f:
        f.write("alpha\n")

    space_file = os.path.join(repo_path, "second file with space.txt")
    with open(space_file, "w", encoding="utf-8") as f:
        f.write("second file content\n")

    subprocess.run(["git", "add", "notes.txt", "second file with space.txt"], cwd=repo_path, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    with open(space_file, "w", encoding="utf-8") as f:
        f.write("second file staged content\n")
    subprocess.run(["git", "add", "second file with space.txt"], cwd=repo_path, check=True, env=env)

    with open(notes_file, "w", encoding="utf-8") as f:
        f.write("alpha unstaged modified\n")

    return repo_path, env


def run_checks():
    work_dir = tempfile.mkdtemp(prefix="wyag_commit_create_test_")
    results = []
    cases_executed = 0

    try:
        repo_path, env = setup_temp_repo(work_dir)
        repo = libwyag.GitRepository(repo_path)

        tree_sha = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=repo_path, text=True, env=env).strip()
        author = "Pritpal Singh <pritpal@example.com>"
        ts = datetime(2026, 11, 14, 0, 0, 0, tzinfo=timezone.utc)
        message = "Tested usage example root commit"

        commit_sha1 = libwyag.commit_create(repo, tree_sha, None, author, ts, message)
        cases_executed += 1

        assert len(commit_sha1) == 40
        obj1 = libwyag.object_read(repo, commit_sha1)
        assert obj1.fmt == b"commit"
        assert obj1.kvlm[b"tree"] == tree_sha.encode("ascii")
        assert b"parent" not in obj1.kvlm
        assert obj1.kvlm[None] == b"Tested usage example root commit\n"

        git_cat = subprocess.check_output(["git", "cat-file", "-p", commit_sha1], cwd=repo_path, text=True, env=env)
        assert f"tree {tree_sha}" in git_cat
        assert message in git_cat

        results.append({
            "case": "1: tested_usage_example_root_commit",
            "arguments": {
                "tree": tree_sha,
                "parent": None,
                "author": author,
                "timestamp": str(ts),
                "message": message
            },
            "exit_status": 0,
            "commit_sha": commit_sha1,
            "state_verified": True,
            "passed": True
        })

        message2 = "Second commit with parent"
        commit_sha2 = libwyag.commit_create(repo, tree_sha, commit_sha1, author, ts, message2)
        cases_executed += 1

        obj2 = libwyag.object_read(repo, commit_sha2)
        assert obj2.kvlm[b"parent"] == commit_sha1.encode("ascii")

        git_cat2 = subprocess.check_output(["git", "cat-file", "-p", commit_sha2], cwd=repo_path, text=True, env=env)
        assert f"parent {commit_sha1}" in git_cat2

        results.append({
            "case": "2: commit_with_parent",
            "arguments": {
                "tree": tree_sha,
                "parent": commit_sha1,
                "author": author,
                "timestamp": str(ts),
                "message": message2
            },
            "exit_status": 0,
            "commit_sha": commit_sha2,
            "state_verified": True,
            "passed": True
        })

        tree_err = None
        try:
            libwyag.commit_create(repo, None, None, author, ts, "Invalid tree")
        except Exception as e:
            tree_err = str(e)
        cases_executed += 1
        assert tree_err is not None

        results.append({
            "case": "3: failure_none_tree",
            "arguments": {"tree": None},
            "exit_status": 1,
            "actual_error": tree_err,
            "passed": True
        })

        ts_err = None
        try:
            libwyag.commit_create(repo, tree_sha, None, author, "invalid_timestamp", "Invalid ts")
        except Exception as e:
            ts_err = str(e)
        cases_executed += 1
        assert ts_err is not None

        results.append({
            "case": "4: failure_invalid_timestamp_type",
            "arguments": {"timestamp": "invalid_timestamp"},
            "exit_status": 1,
            "actual_error": ts_err,
            "passed": True
        })

        if cases_executed == 0:
            raise RuntimeError("Zero-case run rejected: No test cases were executed!")

        print(f"Total test cases executed: {cases_executed}")
        for res in results:
            print(f"  [PASS] {res['case']}: exit_status={res['exit_status']}")

        out_dir = os.path.join(REPO_ROOT, "work", "R21-T037")
        os.makedirs(out_dir, exist_ok=True)

        tool_versions = get_tool_versions()
        with open(os.path.join(out_dir, "tool_versions.txt"), "w", encoding="utf-8") as f:
            for k, v in tool_versions.items():
                f.write(f"{k}: {v}\n")

        native_tests = record_native_tests()
        with open(os.path.join(out_dir, "native_test_names.txt"), "w", encoding="utf-8") as f:
            for t in native_tests:
                f.write(f"{t}\n")

        with open(os.path.join(out_dir, "inputs_and_results.json"), "w", encoding="utf-8") as f:
            json.dump({
                "cases_executed": cases_executed,
                "tool_versions": tool_versions,
                "native_test_names": native_tests,
                "results": results
            }, f, indent=2)

        print("\nAll checks completed successfully and artifacts saved to work/R21-T037/")
        return 0

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_checks())
