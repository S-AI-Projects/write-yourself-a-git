#!/usr/bin/env python3
import configparser
import json
import os
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

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

    # Initialize repository with git CLI
    subprocess.run(["git", "init"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    # Create notes.txt containing "alpha\n"
    notes_file = os.path.join(repo_path, "notes.txt")
    with open(notes_file, "w", encoding="utf-8") as f:
        f.write("alpha\n")

    # Create a second file whose name contains a space
    space_file = os.path.join(repo_path, "second file with space.txt")
    with open(space_file, "w", encoding="utf-8") as f:
        f.write("second file content\n")

    # Stage both files and create initial commit
    subprocess.run(["git", "add", "notes.txt", "second file with space.txt"], cwd=repo_path, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    # Add one staged change: modify space_file and git add it
    with open(space_file, "w", encoding="utf-8") as f:
        f.write("second file staged content\n")
    subprocess.run(["git", "add", "second file with space.txt"], cwd=repo_path, check=True, env=env)

    # Add one unstaged change: modify notes.txt without adding it
    with open(notes_file, "w", encoding="utf-8") as f:
        f.write("alpha unstaged modified\n")

    return repo_path, env


def run_checks():
    work_dir = tempfile.mkdtemp(prefix="wyag_gitconfig_user_test_")
    results = []
    cases_executed = 0

    try:
        repo_path, env = setup_temp_repo(work_dir)
        temp_home = os.path.join(work_dir, "isolated_home")
        os.makedirs(temp_home, exist_ok=True)

        # Isolated environment variables pointing to temporary directory
        isolated_env = env.copy()
        isolated_env["HOME"] = temp_home
        isolated_env["XDG_CONFIG_HOME"] = os.path.join(temp_home, ".config")

        # Stub external command execution using patch
        def stub_external_command(*args, **kwargs):
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        # -------------------------------------------------------------
        # Test Case 1: Success branch with local config object
        # -------------------------------------------------------------
        cfg_success = configparser.ConfigParser()
        cfg_success["user"] = {
            "name": "Deterministic Author",
            "email": "author@deterministic.local"
        }
        res1 = libwyag.gitconfig_user_get(cfg_success)
        cases_executed += 1
        expected1 = "Deterministic Author <author@deterministic.local>"
        assert res1 == expected1, f"Expected '{expected1}', got '{res1}'"

        results.append({
            "case": "1: success-branch-with-local-config",
            "arguments": {"user.name": "Deterministic Author", "user.email": "author@deterministic.local"},
            "exit_status": 0,
            "actual_result": res1,
            "expected_result": expected1,
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 2: Success branch via file-based gitconfig_read under isolated home
        # -------------------------------------------------------------
        gitconfig_file = os.path.join(temp_home, ".gitconfig")
        with open(gitconfig_file, "w", encoding="utf-8") as f:
            f.write("[user]\n    name = File Author\n    email = file@example.com\n")

        with patch.dict(os.environ, isolated_env, clear=False), \
             patch("os.path.expanduser", side_effect=lambda p: p.replace("~", temp_home)), \
             patch("subprocess.run", side_effect=stub_external_command):
            cfg_read = libwyag.gitconfig_read()
            res2 = libwyag.gitconfig_user_get(cfg_read)
        cases_executed += 1
        expected2 = "File Author <file@example.com>"
        assert res2 == expected2, f"Expected '{expected2}', got '{res2}'"

        results.append({
            "case": "2: success-branch-file-based-read-isolated-home",
            "arguments": {"config_path": gitconfig_file},
            "exit_status": 0,
            "actual_result": res2,
            "expected_result": expected2,
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 3: Missing-dependency branch - Missing [user] section
        # -------------------------------------------------------------
        cfg_no_user = configparser.ConfigParser()
        cfg_no_user["core"] = {"repositoryformatversion": "0"}
        res3 = libwyag.gitconfig_user_get(cfg_no_user)
        cases_executed += 1
        assert res3 is None, f"Expected None for missing [user] section, got '{res3}'"

        results.append({
            "case": "3: missing-dependency-missing-user-section",
            "arguments": {"sections": list(cfg_no_user.sections())},
            "exit_status": 0,
            "actual_result": res3,
            "expected_result": None,
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 4: Missing-dependency branch - Missing email in [user]
        # -------------------------------------------------------------
        cfg_no_email = configparser.ConfigParser()
        cfg_no_email["user"] = {"name": "Author Without Email"}
        res4 = libwyag.gitconfig_user_get(cfg_no_email)
        cases_executed += 1
        assert res4 is None, f"Expected None for missing email, got '{res4}'"

        results.append({
            "case": "4: missing-dependency-missing-email",
            "arguments": {"user_keys": list(cfg_no_email["user"].keys())},
            "exit_status": 0,
            "actual_result": res4,
            "expected_result": None,
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 5: Missing-dependency branch - Missing name in [user]
        # -------------------------------------------------------------
        cfg_no_name = configparser.ConfigParser()
        cfg_no_name["user"] = {"email": "no-name@example.com"}
        res5 = libwyag.gitconfig_user_get(cfg_no_name)
        cases_executed += 1
        assert res5 is None, f"Expected None for missing name, got '{res5}'"

        results.append({
            "case": "5: missing-dependency-missing-name",
            "arguments": {"user_keys": list(cfg_no_name["user"].keys())},
            "exit_status": 0,
            "actual_result": res5,
            "expected_result": None,
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 6: Missing-dependency branch - Empty config or None
        # -------------------------------------------------------------
        cfg_empty = configparser.ConfigParser()
        res6a = libwyag.gitconfig_user_get(cfg_empty)
        cases_executed += 1
        assert res6a is None, f"Expected None for empty config, got '{res6a}'"

        with patch("libwyag.gitconfig_read", return_value=configparser.ConfigParser()):
            res6b = libwyag.gitconfig_user_get(None)
        cases_executed += 1
        assert res6b is None, f"Expected None for None config, got '{res6b}'"

        results.append({
            "case": "6: missing-dependency-empty-and-none-config",
            "arguments": {"cfg_empty": "empty ConfigParser", "cfg_none": "None"},
            "exit_status": 0,
            "actual_result": {"empty": res6a, "none": res6b},
            "expected_result": {"empty": None, "none": None},
            "passed": True
        })

        # Reject zero-case run
        if cases_executed == 0:
            raise RuntimeError("Zero-case run rejected: No test cases were executed!")

        print(f"Total test cases executed: {cases_executed}")
        for res in results:
            print(f"  [PASS] {res['case']}: exit_status={res['exit_status']}")

        # Save artifacts in work/R21-T035/
        out_dir = os.path.join(REPO_ROOT, "work", "R21-T035")
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

        print("\nAll checks completed successfully and artifacts saved to work/R21-T035/")
        return 0

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_checks())
