#!/usr/bin/env python3
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
    work_dir = tempfile.mkdtemp(prefix="wyag_tree_checkout_test_")
    results = []
    cases_executed = 0

    try:
        repo_path, env = setup_temp_repo(work_dir)
        repo = libwyag.GitRepository(repo_path)

        tree_sha = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=repo_path, text=True, env=env).strip()
        tree_obj = libwyag.object_read(repo, tree_sha)

        missing_dest = os.path.join(work_dir, "nonexistent_checkout_dir")
        failure_err = None
        try:
            libwyag.tree_checkout(repo, tree_obj, missing_dest)
        except Exception as e:
            failure_err = str(e)
        cases_executed += 1

        expected_failure_msg = f"Checkout destination '{missing_dest}' is not a directory."
        assert failure_err == expected_failure_msg, f"Expected '{expected_failure_msg}', got '{failure_err}'"
        assert not os.path.exists(missing_dest)

        results.append({
            "case": "1: failure_branch_nonexistent_destination",
            "arguments": {"path": missing_dest},
            "exit_status": 1,
            "actual_error": failure_err,
            "diagnostic_explanation": "Destination directory does not exist; tree_checkout requires caller to provide an existing directory.",
            "passed": True
        })

        os.makedirs(missing_dest, exist_ok=True)
        libwyag.tree_checkout(repo, tree_obj, missing_dest)
        cases_executed += 1

        checked_out_notes = os.path.join(missing_dest, "notes.txt")
        checked_out_space = os.path.join(missing_dest, "second file with space.txt")
        assert os.path.isfile(checked_out_notes)
        assert os.path.isfile(checked_out_space)

        with open(checked_out_notes, "r", encoding="utf-8") as f:
            assert f.read() == "alpha\n"
        with open(checked_out_space, "r", encoding="utf-8") as f:
            assert f.read() == "second file content\n"

        results.append({
            "case": "2: corrected_invocation_succeeds",
            "arguments": {"path": missing_dest},
            "exit_status": 0,
            "state_verification": "Both files successfully extracted with matching contents",
            "passed": True
        })

        regular_file_dest = os.path.join(work_dir, "dest_is_file.txt")
        with open(regular_file_dest, "w", encoding="utf-8") as f:
            f.write("regular file\n")

        file_collision_err = None
        try:
            libwyag.tree_checkout(repo, tree_obj, regular_file_dest)
        except Exception as e:
            file_collision_err = str(e)
        cases_executed += 1

        expected_collision_msg = f"Checkout destination '{regular_file_dest}' is not a directory."
        assert file_collision_err == expected_collision_msg

        results.append({
            "case": "3: failure_branch_file_instead_of_dir",
            "arguments": {"path": regular_file_dest},
            "exit_status": 1,
            "actual_error": file_collision_err,
            "diagnostic_explanation": "Target path exists but is a regular file; tree_checkout requires a directory.",
            "passed": True
        })

        wyag_bin = os.path.join(REPO_ROOT, "wyag")
        cli_dest = os.path.join(work_dir, "cli_checkout_dir")
        cli_proc = subprocess.run([sys.executable, wyag_bin, "checkout", "HEAD", cli_dest], cwd=repo_path, capture_output=True, text=True, env=env)
        cases_executed += 1
        assert cli_proc.returncode == 0
        assert os.path.isfile(os.path.join(cli_dest, "notes.txt"))

        results.append({
            "case": "4: cli_checkout_invocation",
            "arguments": ["wyag", "checkout", "HEAD", cli_dest],
            "exit_status": cli_proc.returncode,
            "passed": True
        })

        if cases_executed == 0:
            raise RuntimeError("Zero-case run rejected: No test cases were executed!")

        print(f"Total test cases executed: {cases_executed}")
        for res in results:
            print(f"  [PASS] {res['case']}: exit_status={res['exit_status']}")

        out_dir = os.path.join(REPO_ROOT, "work", "R21-T038")
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

        print("\nAll checks completed successfully and artifacts saved to work/R21-T038/")
        return 0

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_checks())
