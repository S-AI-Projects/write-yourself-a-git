#!/usr/bin/env python3
"""Validation script for R21-T047: Integrate a focused check: repo_file."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORK_DIR = Path(__file__).resolve().parent
WYAG = REPO_ROOT / "wyag"

def get_tool_versions():
    versions = {}
    versions["python"] = sys.version.split()[0]
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True)
        versions["git"] = r.stdout.strip()
    except Exception as e:
        versions["git"] = str(e)
    try:
        r = subprocess.run(["make", "--version"], capture_output=True, text=True, check=True)
        versions["make"] = r.stdout.splitlines()[0]
    except Exception as e:
        versions["make"] = str(e)
    try:
        r = subprocess.run(["emacs", "--version"], capture_output=True, text=True, check=True)
        versions["emacs"] = r.stdout.splitlines()[0]
    except Exception as e:
        versions["emacs"] = str(e)
    return versions

def run_tests():
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    tool_versions = get_tool_versions()
    with open(WORK_DIR / "tool-versions.json", "w") as f:
        json.dump(tool_versions, f, indent=2)

    inputs_record = {
        "task": "R21-T047",
        "function": "repo_file",
        "test_cases": [
            "native_test_suite_repo_file_step",
            "repo_file_existing_root_path",
            "repo_file_nested_path_mkdir_true",
            "repo_file_missing_parent_mkdir_false_returns_none",
            "repo_file_parent_is_file_raises_exception",
            "worktree_fixture_with_space_and_staged_unstaged_states"
        ]
    }
    with open(WORK_DIR / "inputs.json", "w") as f:
        json.dump(inputs_record, f, indent=2)

    results_record = {
        "checks": [],
        "passed": False
    }

    # 1. Native test suite
    print("Running native test suite...")
    test_run = subprocess.run(["./wyag-tests.sh"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert test_run.returncode == 0, f"wyag-tests.sh failed:\n{test_run.stderr}"
    assert "repo_file focused check" in test_run.stdout, "repo_file focused check test step missing"
    results_record["checks"].append({
        "name": "native_test_suite",
        "status": "PASS",
        "exit_code": test_run.returncode
    })

    # 2. Focused checks with isolated temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix="wyag_repo_file_"))
    try:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(temp_dir),
            "PYTHONPATH": str(REPO_ROOT)
        }
        (temp_dir / ".gitconfig").write_text("[user]\n    name = Tester\n    email = tester@example.com\n")

        # Initialize repository
        subprocess.run([str(WYAG), "init", "."], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Worktree fixture: notes.txt with "alpha\n", second file with space, one staged and one unstaged change
        (temp_dir / "notes.txt").write_text("alpha\n")
        (temp_dir / "file with space.txt").write_text("space content\n")
        subprocess.run([str(WYAG), "add", "notes.txt", "file with space.txt"], cwd=temp_dir, env=env, capture_output=True, check=True)
        # Staged change in notes.txt and new unstaged change in unstaged.txt
        (temp_dir / "notes.txt").write_text("alpha updated\n")
        (temp_dir / "unstaged.txt").write_text("unstaged content\n")

        # Run direct checks on repo_file via python
        sys.path.insert(0, str(REPO_ROOT))
        import libwyag

        repo = libwyag.repo_find(str(temp_dir))
        assert repo is not None, "Failed to find repository"

        # Case A: Existing file at root of gitdir
        config_path = libwyag.repo_file(repo, "config")
        assert config_path and Path(config_path).name == "config", f"Unexpected config path {config_path}"
        results_record["checks"].append({
            "name": "repo_file_existing_file",
            "path": config_path,
            "status": "PASS"
        })

        # Case B: Nested directory created with mkdir=True
        nested_file = libwyag.repo_file(repo, "logs", "refs", "heads", "master", mkdir=True)
        assert nested_file and Path(nested_file).name == "master", f"Unexpected nested path {nested_file}"
        assert Path(nested_file).parent.is_dir(), "Expected parent directories to be created"
        results_record["checks"].append({
            "name": "repo_file_mkdir_true",
            "path": nested_file,
            "parent_exists": True,
            "status": "PASS"
        })

        # Case C: Documented failure/edge-state - missing parent with mkdir=False returns None
        missing_result = libwyag.repo_file(repo, "missing_hierarchy", "deep_dir", "file.txt", mkdir=False)
        assert missing_result is None, f"Expected None for missing hierarchy, got {missing_result}"
        results_record["checks"].append({
            "name": "repo_file_missing_mkdir_false",
            "result": None,
            "status": "PASS"
        })

        # Case D: Documented failure/edge-state - parent path is a regular file, not a directory
        blocker_file = Path(repo.gitdir) / "not_a_dir"
        blocker_file.write_text("dummy file\n")
        exception_caught = False
        try:
            libwyag.repo_file(repo, "not_a_dir", "target.txt", mkdir=True)
        except Exception as e:
            exception_caught = True
            assert "Not a directory" in str(e), f"Unexpected exception message: {e}"
        assert exception_caught, "Expected Exception for parent path that is a file"
        results_record["checks"].append({
            "name": "repo_file_parent_is_file_error",
            "exception_caught": True,
            "status": "PASS"
        })

        # Verify git status in temp worktree
        git_status = subprocess.run(["git", "status", "--porcelain"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True).stdout
        assert "notes.txt" in git_status, "notes.txt missing in git status"
        assert "file with space.txt" in git_status, "file with space.txt missing in git status"
        results_record["checks"].append({
            "name": "git_status_verification",
            "status_output": git_status.strip().splitlines(),
            "status": "PASS"
        })

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    results_record["passed"] = True
    with open(WORK_DIR / "results.json", "w") as f:
        json.dump(results_record, f, indent=2)

    print("All checks for R21-T047 passed successfully!")

if __name__ == "__main__":
    run_tests()
