#!/usr/bin/env python3
"""Validation script for R21-T048: Explain a failing invocation: index_read."""

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
        "task": "R21-T048",
        "function": "index_read",
        "test_cases": [
            "native_test_suite_index_read_step",
            "truncated_index_header_failure",
            "corrupt_index_signature_failure",
            "unsupported_index_version_failure",
            "recovery_and_corrected_invocation_success",
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
    assert "index_read diagnostic check" in test_run.stdout, "index_read diagnostic check test step missing"
    results_record["checks"].append({
        "name": "native_test_suite",
        "status": "PASS",
        "exit_code": test_run.returncode
    })

    # 2. Focused checks with isolated temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix="wyag_index_read_"))
    try:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(temp_dir),
            "PYTHONPATH": str(REPO_ROOT)
        }
        (temp_dir / ".gitconfig").write_text("[user]\n    name = Tester\n    email = tester@example.com\n")

        # Initialize repository
        subprocess.run([str(WYAG), "init", "."], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Worktree fixture: notes.txt with "alpha\n", second file with space, staged change and unstaged change
        (temp_dir / "notes.txt").write_text("alpha\n")
        (temp_dir / "file with space.txt").write_text("space content\n")
        subprocess.run([str(WYAG), "add", "notes.txt", "file with space.txt"], cwd=temp_dir, env=env, capture_output=True, check=True)
        (temp_dir / "notes.txt").write_text("alpha unstaged\n")

        index_file = temp_dir / ".git" / "index"
        assert index_file.is_file(), "Index file should exist after add"
        valid_index_backup = index_file.read_bytes()

        # Failure Case 1: Truncated index (< 12 bytes)
        index_file.write_bytes(b"DIRC00")
        res_trunc = subprocess.run([str(WYAG), "ls-files"], cwd=temp_dir, env=env, capture_output=True, text=True)
        assert res_trunc.returncode != 0, "Expected non-zero exit for truncated index"
        assert "header is shorter than 12 bytes" in res_trunc.stderr, f"Missing diagnostic: {res_trunc.stderr}"
        results_record["checks"].append({
            "name": "truncated_header_failure",
            "exit_code": res_trunc.returncode,
            "error_message": "header is shorter than 12 bytes",
            "status": "PASS"
        })

        # Failure Case 2: Invalid signature (not DIRC)
        index_file.write_bytes(b"BADS\x00\x00\x00\x02\x00\x00\x00\x01")
        res_sig = subprocess.run([str(WYAG), "ls-files"], cwd=temp_dir, env=env, capture_output=True, text=True)
        assert res_sig.returncode != 0, "Expected non-zero exit for invalid signature"
        assert "Invalid index file signature" in res_sig.stderr, f"Missing diagnostic: {res_sig.stderr}"
        results_record["checks"].append({
            "name": "invalid_signature_failure",
            "exit_code": res_sig.returncode,
            "error_message": "Invalid index file signature",
            "status": "PASS"
        })

        # Failure Case 3: Unsupported version (version 4)
        index_file.write_bytes(b"DIRC\x00\x00\x00\x04\x00\x00\x00\x01")
        res_ver = subprocess.run([str(WYAG), "ls-files"], cwd=temp_dir, env=env, capture_output=True, text=True)
        assert res_ver.returncode != 0, "Expected non-zero exit for unsupported version"
        assert "Unsupported index file version 4" in res_ver.stderr, f"Missing diagnostic: {res_ver.stderr}"
        results_record["checks"].append({
            "name": "unsupported_version_failure",
            "exit_code": res_ver.returncode,
            "error_message": "Unsupported index file version 4",
            "status": "PASS"
        })

        # Recovery Case: Restore valid index or regenerate via add, then verify ls-files success
        index_file.write_bytes(valid_index_backup)
        res_ok = subprocess.run([str(WYAG), "ls-files"], cwd=temp_dir, env=env, capture_output=True, text=True)
        assert res_ok.returncode == 0, f"Expected 0 exit after recovery, got {res_ok.stderr}"
        output_files = set(res_ok.stdout.strip().splitlines())
        assert "notes.txt" in output_files, "notes.txt should be in index"
        assert "file with space.txt" in output_files, "file with space.txt should be in index"
        results_record["checks"].append({
            "name": "recovered_invocation_success",
            "exit_code": res_ok.returncode,
            "files_found": sorted(list(output_files)),
            "status": "PASS"
        })

        # Compare worktree status with Git CLI
        git_status = subprocess.run(["git", "status", "--porcelain"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True).stdout
        assert "notes.txt" in git_status, "notes.txt missing from git status"
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

    print("All checks for R21-T048 passed successfully!")

if __name__ == "__main__":
    run_tests()
