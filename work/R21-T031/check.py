#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile

# Ensure the repository root is in sys.path
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
    # Names of native tests from wyag-tests.sh
    test_names = [
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
    return test_names


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
    work_dir = tempfile.mkdtemp(prefix="wyag_tag_test_")
    results = []
    cases_executed = 0

    try:
        repo_path, env = setup_temp_repo(work_dir)
        repo = libwyag.GitRepository(repo_path)

        # Verify initial repo state: HEAD commit
        head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_path, text=True, env=env).strip()

        # -------------------------------------------------------------
        # Test Case 1: Ordinary Success - Lightweight tag creation
        # -------------------------------------------------------------
        tag_name_1 = "v1.0-light"
        ref_target_1 = "HEAD"
        before_state_1 = os.path.exists(os.path.join(repo_path, ".git", "refs", "tags", tag_name_1))
        
        libwyag.tag_create(repo, tag_name_1, ref_target_1, create_tag_object=False)
        cases_executed += 1
        
        tag_file_1 = os.path.join(repo_path, ".git", "refs", "tags", tag_name_1)
        after_state_1 = os.path.exists(tag_file_1)
        with open(tag_file_1, "r", encoding="utf-8") as f:
            created_sha_1 = f.read().strip()
            
        assert after_state_1 is True, "Lightweight tag ref file was not created"
        assert created_sha_1 == head_sha, f"Expected SHA {head_sha}, got {created_sha_1}"

        # Git CLI verification
        cli_sha_1 = subprocess.check_output(["git", "rev-parse", f"refs/tags/{tag_name_1}"], cwd=repo_path, text=True, env=env).strip()
        assert cli_sha_1 == head_sha, f"Git CLI returned {cli_sha_1}, expected {head_sha}"

        results.append({
            "case": "1: ordinary-success-lightweight-tag",
            "arguments": {"name": tag_name_1, "ref": ref_target_1, "create_tag_object": False},
            "exit_status": 0,
            "before_state": f"refs/tags/{tag_name_1} exists: {before_state_1}",
            "after_state": f"refs/tags/{tag_name_1} exists: {after_state_1}, sha: {created_sha_1}",
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 2: Ordinary Success - CLI command invocation
        # -------------------------------------------------------------
        tag_name_cli = "v1.1-cli"
        wyag_bin = os.path.join(REPO_ROOT, "wyag")
        cli_proc = subprocess.run([sys.executable, wyag_bin, "tag", tag_name_cli, "HEAD"], cwd=repo_path, capture_output=True, text=True, env=env)
        cases_executed += 1
        
        tag_file_cli = os.path.join(repo_path, ".git", "refs", "tags", tag_name_cli)
        cli_after_state = os.path.exists(tag_file_cli)
        assert cli_proc.returncode == 0, f"wyag tag CLI failed: {cli_proc.stderr}"
        assert cli_after_state is True, "CLI tag ref file not created"

        results.append({
            "case": "2: ordinary-success-cli-invocation",
            "arguments": ["wyag", "tag", tag_name_cli, "HEAD"],
            "exit_status": cli_proc.returncode,
            "stdout": cli_proc.stdout.strip(),
            "after_state": f"refs/tags/{tag_name_cli} exists: {cli_after_state}",
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 3: Ordinary Success - Annotated tag object creation
        # -------------------------------------------------------------
        tag_name_2 = "v2.0-annotated"
        before_state_2 = os.path.exists(os.path.join(repo_path, ".git", "refs", "tags", tag_name_2))

        libwyag.tag_create(repo, tag_name_2, "HEAD", create_tag_object=True)
        cases_executed += 1

        tag_file_2 = os.path.join(repo_path, ".git", "refs", "tags", tag_name_2)
        after_state_2 = os.path.exists(tag_file_2)
        assert after_state_2 is True, "Annotated tag ref file was not created"

        with open(tag_file_2, "r", encoding="utf-8") as f:
            annotated_tag_sha = f.read().strip()

        # Read the tag object and verify fields
        tag_obj = libwyag.object_read(repo, annotated_tag_sha)
        assert tag_obj.fmt == b'tag', f"Expected format 'tag', got {tag_obj.fmt}"
        assert tag_obj.kvlm[b'object'] == head_sha.encode(), "Tag object target SHA mismatch"
        assert tag_obj.kvlm[b'type'] == b'commit', "Tag object target type mismatch"
        assert tag_obj.kvlm[b'tag'] == tag_name_2.encode(), "Tag object tag name mismatch"

        results.append({
            "case": "3: ordinary-success-annotated-tag",
            "arguments": {"name": tag_name_2, "ref": "HEAD", "create_tag_object": True},
            "exit_status": 0,
            "before_state": f"refs/tags/{tag_name_2} exists: {before_state_2}",
            "after_state": f"refs/tags/{tag_name_2} exists: {after_state_2}, tag_sha: {annotated_tag_sha}",
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 4: Documented Failure - Empty tag name
        # -------------------------------------------------------------
        empty_err = None
        try:
            libwyag.tag_create(repo, "", "HEAD")
        except ValueError as e:
            empty_err = str(e)
        cases_executed += 1

        assert empty_err == "Tag name cannot be empty.", f"Unexpected error for empty name: {empty_err}"
        results.append({
            "case": "4: failure-empty-tag-name",
            "arguments": {"name": "", "ref": "HEAD"},
            "exit_status": 1,
            "expected_error": "Tag name cannot be empty.",
            "actual_error": empty_err,
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 5: Documented Failure - Whitespace tag name
        # -------------------------------------------------------------
        ws_err = None
        try:
            libwyag.tag_create(repo, "   ", "HEAD")
        except ValueError as e:
            ws_err = str(e)
        cases_executed += 1

        assert ws_err == "Tag name cannot be empty.", f"Unexpected error for whitespace name: {ws_err}"
        results.append({
            "case": "5: failure-whitespace-tag-name",
            "arguments": {"name": "   ", "ref": "HEAD"},
            "exit_status": 1,
            "expected_error": "Tag name cannot be empty.",
            "actual_error": ws_err,
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 6: Documented Failure - None tag name
        # -------------------------------------------------------------
        none_err = None
        try:
            libwyag.tag_create(repo, None, "HEAD")
        except ValueError as e:
            none_err = str(e)
        cases_executed += 1

        assert none_err == "Tag name cannot be empty.", f"Unexpected error for None name: {none_err}"
        results.append({
            "case": "6: failure-none-tag-name",
            "arguments": {"name": None, "ref": "HEAD"},
            "exit_status": 1,
            "expected_error": "Tag name cannot be empty.",
            "actual_error": none_err,
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 7: Documented Failure - Empty reference
        # -------------------------------------------------------------
        empty_ref_err = None
        try:
            libwyag.tag_create(repo, "v3.0-fail", "")
        except ValueError as e:
            empty_ref_err = str(e)
        cases_executed += 1

        assert empty_ref_err == "Reference cannot be empty.", f"Unexpected error for empty ref: {empty_ref_err}"
        assert not os.path.exists(os.path.join(repo_path, ".git", "refs", "tags", "v3.0-fail"))
        results.append({
            "case": "7: failure-empty-ref",
            "arguments": {"name": "v3.0-fail", "ref": ""},
            "exit_status": 1,
            "expected_error": "Reference cannot be empty.",
            "actual_error": empty_ref_err,
            "after_state": "Tag was not created",
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 8: Documented Failure - Nonexistent reference
        # -------------------------------------------------------------
        nonexistent_err = None
        try:
            libwyag.tag_create(repo, "v4.0-fail", "nonexistent-sha-or-branch")
        except Exception as e:
            nonexistent_err = str(e)
        cases_executed += 1

        assert "No such reference" in nonexistent_err, f"Unexpected error for non-existent ref: {nonexistent_err}"
        assert not os.path.exists(os.path.join(repo_path, ".git", "refs", "tags", "v4.0-fail"))
        results.append({
            "case": "8: failure-nonexistent-ref",
            "arguments": {"name": "v4.0-fail", "ref": "nonexistent-sha-or-branch"},
            "exit_status": 1,
            "expected_error": "No such reference nonexistent-sha-or-branch.",
            "actual_error": nonexistent_err,
            "after_state": "Tag was not created",
            "passed": True
        })

        # Reject zero-case run
        if cases_executed == 0:
            raise RuntimeError("Zero-case run rejected: No test cases were executed!")

        print(f"Total test cases executed: {cases_executed}")
        for res in results:
            print(f"  [PASS] {res['case']}: exit_status={res['exit_status']}")

        # Save artifacts in work/R21-T031/
        out_dir = os.path.join(REPO_ROOT, "work", "R21-T031")
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

        print("\nAll checks completed successfully and artifacts saved to work/R21-T031/")
        return 0

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_checks())
