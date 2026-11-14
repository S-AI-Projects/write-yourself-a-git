#!/usr/bin/env python3
import io
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
    work_dir = tempfile.mkdtemp(prefix="wyag_object_hash_test_")
    results = []
    cases_executed = 0

    try:
        repo_path, env = setup_temp_repo(work_dir)
        repo = libwyag.GitRepository(repo_path)
        notes_path = os.path.join(repo_path, "notes.txt")

        # Compare repo state with Git CLI
        status_out = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo_path, text=True, env=env)
        assert "second file with space.txt" in status_out and "M " in status_out, "Expected staged change missing"
        assert "notes.txt" in status_out and " M" in status_out, "Expected unstaged change missing"

        # -----------------------------------------------------------------
        # Test Case 1: Minimum accepted argument list (fd, fmt) without optional repo
        # -----------------------------------------------------------------
        with open(notes_path, "rb") as fd:
            sha1 = libwyag.object_hash(fd, b'blob')
        cases_executed += 1

        # Git CLI verification for hash-object
        cli_sha = subprocess.check_output(["git", "hash-object", notes_path], cwd=repo_path, text=True, env=env).strip()
        assert sha1 == cli_sha, f"Expected {cli_sha}, got {sha1}"

        # Verify object was NOT written to database (repo is None)
        obj_path = os.path.join(repo_path, ".git", "objects", sha1[:2], sha1[2:])
        assert not os.path.exists(obj_path), f"Object should not have been written to disk at {obj_path}"

        results.append({
            "case": "1: minimum-arguments-without-repo",
            "arguments": {"fd": "notes.txt stream", "fmt": "b'blob'", "repo": "None"},
            "exit_status": 0,
            "expected_sha": cli_sha,
            "actual_sha": sha1,
            "object_written_to_disk": False,
            "passed": True
        })

        # -----------------------------------------------------------------
        # Test Case 2: CLI invocation with minimum arguments
        # -----------------------------------------------------------------
        wyag_bin = os.path.join(REPO_ROOT, "wyag")
        cli_proc = subprocess.run([sys.executable, wyag_bin, "hash-object", notes_path], cwd=repo_path, capture_output=True, text=True, env=env)
        cases_executed += 1
        assert cli_proc.returncode == 0, f"wyag hash-object failed: {cli_proc.stderr}"
        assert cli_proc.stdout.strip() == cli_sha, f"wyag stdout {cli_proc.stdout.strip()} != {cli_sha}"

        results.append({
            "case": "2: cli-hash-object-minimum-arguments",
            "arguments": ["wyag", "hash-object", "notes.txt"],
            "exit_status": cli_proc.returncode,
            "stdout": cli_proc.stdout.strip(),
            "passed": True
        })

        # -----------------------------------------------------------------
        # Test Case 3: Optional argument exercised (repo=repo)
        # -----------------------------------------------------------------
        sample_data = b"unique content for write testing\n"
        fd_write = io.BytesIO(sample_data)
        
        # Verify before state: object does not exist
        temp_sha = subprocess.check_output(["git", "hash-object", "--stdin"], input=sample_data.decode("utf-8"), text=True, env=env).strip()
        temp_obj_path = os.path.join(repo_path, ".git", "objects", temp_sha[:2], temp_sha[2:])
        before_exists = os.path.exists(temp_obj_path)

        sha3 = libwyag.object_hash(fd_write, b'blob', repo=repo)
        cases_executed += 1

        after_exists = os.path.exists(temp_obj_path)
        assert sha3 == temp_sha, f"Expected SHA {temp_sha}, got {sha3}"
        assert before_exists is False, "Object existed before write"
        assert after_exists is True, f"Object was not written to database at {temp_obj_path}"

        # Read back written object using wyag object_read
        read_obj = libwyag.object_read(repo, sha3)
        assert read_obj.fmt == b'blob', f"Expected blob fmt, got {read_obj.fmt}"
        assert read_obj.blobdata == sample_data, "Read back object data mismatch"

        results.append({
            "case": "3: optional-argument-repo-exercised",
            "arguments": {"fd": "BytesIO stream", "fmt": "b'blob'", "repo": "GitRepository"},
            "exit_status": 0,
            "sha": sha3,
            "before_state": f"object exists: {before_exists}",
            "after_state": f"object exists: {after_exists}",
            "passed": True
        })

        # -----------------------------------------------------------------
        # Test Case 4: CLI invocation with optional -w (write to repo)
        # -----------------------------------------------------------------
        cli_w_proc = subprocess.run([sys.executable, wyag_bin, "hash-object", "-w", notes_path], cwd=repo_path, capture_output=True, text=True, env=env)
        cases_executed += 1
        assert cli_w_proc.returncode == 0, f"wyag hash-object -w failed: {cli_w_proc.stderr}"
        assert os.path.exists(obj_path), f"Object should now be written to {obj_path}"

        results.append({
            "case": "4: cli-hash-object-with-write-flag",
            "arguments": ["wyag", "hash-object", "-w", "notes.txt"],
            "exit_status": cli_w_proc.returncode,
            "stdout": cli_w_proc.stdout.strip(),
            "object_written": True,
            "passed": True
        })

        # -----------------------------------------------------------------
        # Test Case 5: Argument boundary - string vs bytes fmt
        # -----------------------------------------------------------------
        with open(notes_path, "rb") as fd:
            sha_str_fmt = libwyag.object_hash(fd, "blob")
        cases_executed += 1
        assert sha_str_fmt == sha1, f"String format 'blob' yielded {sha_str_fmt}, expected {sha1}"

        results.append({
            "case": "5: argument-boundary-string-fmt",
            "arguments": {"fmt": "'blob' (str)"},
            "exit_status": 0,
            "sha": sha_str_fmt,
            "passed": True
        })

        # -----------------------------------------------------------------
        # Test Case 6: Documented failure - Unsupported format type
        # -----------------------------------------------------------------
        invalid_err = None
        try:
            with open(notes_path, "rb") as fd:
                libwyag.object_hash(fd, b'invalid_unknown_type')
        except Exception as e:
            invalid_err = str(e)
        cases_executed += 1

        assert invalid_err is not None and "Unknown type" in invalid_err, f"Expected Unknown type error, got {invalid_err}"

        results.append({
            "case": "6: documented-failure-unknown-type",
            "arguments": {"fmt": "b'invalid_unknown_type'"},
            "exit_status": 1,
            "expected_error": "Unknown type b'invalid_unknown_type'!",
            "actual_error": invalid_err,
            "passed": True
        })

        # -----------------------------------------------------------------
        # Test Case 7: Documented failure - Missing required fmt argument
        # -----------------------------------------------------------------
        missing_arg_err = None
        try:
            with open(notes_path, "rb") as fd:
                libwyag.object_hash(fd)  # Missing required positional argument 'fmt'
        except TypeError as e:
            missing_arg_err = str(e)
        cases_executed += 1

        assert missing_arg_err is not None and "missing 1 required positional argument" in missing_arg_err, f"Expected TypeError for missing fmt, got {missing_arg_err}"

        results.append({
            "case": "7: documented-failure-missing-required-argument",
            "arguments": {"fd": "notes.txt"},
            "exit_status": 1,
            "expected_error": "missing 1 required positional argument: 'fmt'",
            "actual_error": missing_arg_err,
            "passed": True
        })

        # Reject zero-case run
        if cases_executed == 0:
            raise RuntimeError("Zero-case run rejected: No test cases were executed!")

        print(f"Total test cases executed: {cases_executed}")
        for res in results:
            print(f"  [PASS] {res['case']}: exit_status={res['exit_status']}")

        # Save artifacts in work/R21-T032/
        out_dir = os.path.join(REPO_ROOT, "work", "R21-T032")
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

        print("\nAll checks completed successfully and artifacts saved to work/R21-T032/")
        return 0

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_checks())
