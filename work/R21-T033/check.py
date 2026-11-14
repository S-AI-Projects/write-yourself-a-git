#!/usr/bin/env python3
import configparser
import hashlib
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


def sha256_of_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


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
    work_dir = tempfile.mkdtemp(prefix="wyag_repo_create_test_")
    results = []
    cases_executed = 0

    try:
        repo_path, env = setup_temp_repo(work_dir)

        # Verify initial repo state
        status_out = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo_path, text=True, env=env)
        assert "second file with space.txt" in status_out and "M " in status_out, "Expected staged change missing"
        assert "notes.txt" in status_out and " M" in status_out, "Expected unstaged change missing"

        # -------------------------------------------------------------
        # Test Case 1: repo_create on a non-existent path
        # Assert intended state transition & unrelated sibling state unchanged
        # -------------------------------------------------------------
        sibling_file = os.path.join(work_dir, "unrelated_sibling.txt")
        with open(sibling_file, "w", encoding="utf-8") as f:
            f.write("unrelated sibling content that must not change\n")
        sibling_hash_before = sha256_of_file(sibling_file)

        new_repo_dir = os.path.join(work_dir, "fresh_repo")
        before_exists = os.path.exists(new_repo_dir)

        repo = libwyag.repo_create(new_repo_dir)
        cases_executed += 1

        after_exists = os.path.exists(new_repo_dir)
        git_dir = os.path.join(new_repo_dir, ".git")

        # Verify intended state transitions
        assert before_exists is False, "Directory existed prior to repo_create"
        assert after_exists is True, "Directory was not created by repo_create"
        assert os.path.isdir(git_dir), ".git directory was not created"
        assert os.path.isdir(os.path.join(git_dir, "branches")), ".git/branches missing"
        assert os.path.isdir(os.path.join(git_dir, "objects")), ".git/objects missing"
        assert os.path.isdir(os.path.join(git_dir, "refs", "tags")), ".git/refs/tags missing"
        assert os.path.isdir(os.path.join(git_dir, "refs", "heads")), ".git/refs/heads missing"

        # Verify HEAD
        with open(os.path.join(git_dir, "HEAD"), "r", encoding="utf-8") as f:
            head_content = f.read()
        assert head_content == "ref: refs/heads/master\n", f"Unexpected HEAD content: {head_content}"

        # Verify config
        config = configparser.ConfigParser()
        config.read(os.path.join(git_dir, "config"))
        assert config.getint("core", "repositoryformatversion") == 0, "Invalid repositoryformatversion"
        assert config.getboolean("core", "filemode") is False, "Invalid filemode"
        assert config.getboolean("core", "bare") is False, "Invalid bare setting"

        # Verify unrelated sibling state unchanged
        sibling_hash_after = sha256_of_file(sibling_file)
        assert sibling_hash_before == sibling_hash_after, "Unrelated sibling state was unexpectedly altered!"

        results.append({
            "case": "1: repo_create-fresh-path-with-unrelated-state-invariant",
            "arguments": {"path": new_repo_dir},
            "exit_status": 0,
            "intended_changes": [".git directory created with branches, objects, refs, HEAD, and config"],
            "unrelated_state": "sibling_file.txt remained untouched and bit-identical",
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 2: repo_create on an existing directory with pre-existing worktree files
        # Assert intended changes & pre-existing worktree content unchanged
        # -------------------------------------------------------------
        existing_worktree = os.path.join(work_dir, "existing_worktree_dir")
        os.makedirs(existing_worktree, exist_ok=True)
        user_doc = os.path.join(existing_worktree, "README.md")
        with open(user_doc, "w", encoding="utf-8") as f:
            f.write("# User Documentation\nThis pre-existing file must not be modified or deleted.\n")
        user_doc_hash_before = sha256_of_file(user_doc)

        libwyag.repo_create(existing_worktree)
        cases_executed += 1

        assert os.path.isdir(os.path.join(existing_worktree, ".git")), ".git missing in existing directory"
        user_doc_hash_after = sha256_of_file(user_doc)
        assert user_doc_hash_before == user_doc_hash_after, "Pre-existing file inside worktree was altered!"

        results.append({
            "case": "2: repo_create-existing-directory-preserves-worktree-contents",
            "arguments": {"path": existing_worktree},
            "exit_status": 0,
            "intended_changes": [".git initialized inside existing directory"],
            "unrelated_state": "README.md inside worktree remained untouched and bit-identical",
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 3: CLI invocation (wyag init)
        # -------------------------------------------------------------
        cli_repo = os.path.join(work_dir, "cli_initialized_repo")
        wyag_bin = os.path.join(REPO_ROOT, "wyag")
        cli_proc = subprocess.run([sys.executable, wyag_bin, "init", cli_repo], capture_output=True, text=True, env=env)
        cases_executed += 1

        assert cli_proc.returncode == 0, f"wyag init failed: {cli_proc.stderr}"
        assert os.path.isdir(os.path.join(cli_repo, ".git")), "CLI failed to create .git"

        results.append({
            "case": "3: cli-wyag-init-invocation",
            "arguments": ["wyag", "init", cli_repo],
            "exit_status": cli_proc.returncode,
            "stdout": cli_proc.stdout.strip(),
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 4: Documented failure - path exists and is a regular file
        # -------------------------------------------------------------
        not_a_dir_file = os.path.join(work_dir, "file_instead_of_dir.txt")
        with open(not_a_dir_file, "w", encoding="utf-8") as f:
            f.write("regular file\n")
        file_hash_before = sha256_of_file(not_a_dir_file)

        err_msg_file = None
        try:
            libwyag.repo_create(not_a_dir_file)
        except Exception as e:
            err_msg_file = str(e)
        cases_executed += 1

        assert err_msg_file is not None and "is not a directory" in err_msg_file, f"Expected not a directory exception, got {err_msg_file}"
        assert sha256_of_file(not_a_dir_file) == file_hash_before, "Target file was modified on failure"

        results.append({
            "case": "4: failure-path-is-not-a-directory",
            "arguments": {"path": not_a_dir_file},
            "exit_status": 1,
            "expected_error": f"{not_a_dir_file} is not a directory!",
            "actual_error": err_msg_file,
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 5: Documented failure - .git exists and is not empty
        # -------------------------------------------------------------
        populated_git_dir = os.path.join(work_dir, "already_populated_repo")
        libwyag.repo_create(populated_git_dir)
        
        # Now try to repo_create on the same path again
        err_msg_nonempty = None
        try:
            libwyag.repo_create(populated_git_dir)
        except Exception as e:
            err_msg_nonempty = str(e)
        cases_executed += 1

        assert err_msg_nonempty is not None and "is not empty" in err_msg_nonempty, f"Expected is not empty exception, got {err_msg_nonempty}"

        results.append({
            "case": "5: failure-gitdir-already-populated",
            "arguments": {"path": populated_git_dir},
            "exit_status": 1,
            "expected_error": f"{populated_git_dir} is not empty!",
            "actual_error": err_msg_nonempty,
            "passed": True
        })

        # Reject zero-case run
        if cases_executed == 0:
            raise RuntimeError("Zero-case run rejected: No test cases were executed!")

        print(f"Total test cases executed: {cases_executed}")
        for res in results:
            print(f"  [PASS] {res['case']}: exit_status={res['exit_status']}")

        # Save artifacts in work/R21-T033/
        out_dir = os.path.join(REPO_ROOT, "work", "R21-T033")
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

        print("\nAll checks completed successfully and artifacts saved to work/R21-T033/")
        return 0

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_checks())
