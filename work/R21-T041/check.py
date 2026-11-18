#!/usr/bin/env python3
"""Validation script for R21-T041: Specify the command contract: cmd_status."""

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
    # Python
    versions["python"] = sys.version.split()[0]
    # Git
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True)
        versions["git"] = r.stdout.strip()
    except Exception as e:
        versions["git"] = str(e)
    # Make
    try:
        r = subprocess.run(["make", "--version"], capture_output=True, text=True, check=True)
        versions["make"] = r.stdout.splitlines()[0]
    except Exception as e:
        versions["make"] = str(e)
    # Emacs
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
        "task": "R21-T041",
        "command": "cmd_status",
        "fixture": {
            "file_1": "notes.txt",
            "file_1_content": "alpha\n",
            "file_2": "file with space.txt",
            "file_2_content": "space test\n",
            "staged_change": "notes.txt updated\n",
            "unstaged_change": "file with space.txt updated\n"
        },
        "edge_cases": [
            "invocation outside git repository",
            "ordinary success with staged and unstaged entries"
        ]
    }
    with open(WORK_DIR / "inputs.json", "w") as f:
        json.dump(inputs_record, f, indent=2)

    results_record = {
        "checks": [],
        "passed": False
    }

    # 1. Native wyag-tests.sh check
    print("Running native test suite...")
    test_run = subprocess.run(["./wyag-tests.sh"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert test_run.returncode == 0, f"wyag-tests.sh failed:\n{test_run.stderr}"
    assert "cmd_status contract" in test_run.stdout, "cmd_status contract test step not found in wyag-tests.sh output"
    results_record["checks"].append({
        "name": "native_test_suite",
        "status": "PASS",
        "exit_code": test_run.returncode
    })

    # 2. Temporary repo fixture check
    temp_dir = Path(tempfile.mkdtemp(prefix="wyag_status_test_"))
    try:
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "Tester"
        env["GIT_AUTHOR_EMAIL"] = "tester@example.com"
        env["GIT_COMMITTER_NAME"] = "Tester"
        env["GIT_COMMITTER_EMAIL"] = "tester@example.com"

        # Initialize repository
        subprocess.run(["git", "init"], cwd=temp_dir, capture_output=True, check=True)
        (temp_dir / "notes.txt").write_text("alpha\n")
        (temp_dir / "file with space.txt").write_text("space test\n")
        subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Make one staged change and one unstaged change
        (temp_dir / "notes.txt").write_text("alpha\nalpha updated\n")
        subprocess.run(["git", "add", "notes.txt"], cwd=temp_dir, capture_output=True, check=True)
        (temp_dir / "file with space.txt").write_text("space test\nspace modified\n")

        # Snapshot git state before running status
        status_before = subprocess.run(["git", "status", "--porcelain"], cwd=temp_dir, capture_output=True, text=True, check=True).stdout
        diff_before = subprocess.run(["git", "diff"], cwd=temp_dir, capture_output=True, text=True, check=True).stdout

        # Run wyag status
        res = subprocess.run([str(WYAG), "status"], cwd=temp_dir, capture_output=True, text=True)
        assert res.returncode == 0, f"wyag status exited with code {res.returncode}:\n{res.stderr}"

        # Output assertions
        assert "Changes to be committed:" in res.stdout, "Missing staged changes header"
        assert "modified: notes.txt" in res.stdout, "Staged file not reported as modified"
        assert "modified: file with space.txt" in res.stdout, "Unstaged file with space not reported as modified"

        # State immutability assertion
        status_after = subprocess.run(["git", "status", "--porcelain"], cwd=temp_dir, capture_output=True, text=True, check=True).stdout
        diff_after = subprocess.run(["git", "diff"], cwd=temp_dir, capture_output=True, text=True, check=True).stdout
        assert status_before == status_after, "Repository status changed after wyag status"
        assert diff_before == diff_after, "Repository diff changed after wyag status"

        results_record["checks"].append({
            "name": "ordinary_success_and_state_immutability",
            "status": "PASS",
            "exit_code": res.returncode,
            "stdout": res.stdout
        })

        # 3. Edge case: missing / non-repo directory
        non_repo = Path(tempfile.mkdtemp(prefix="wyag_non_repo_"))
        try:
            non_repo_res = subprocess.run([str(WYAG), "status"], cwd=non_repo, capture_output=True, text=True)
            assert non_repo_res.returncode != 0, "wyag status should fail when outside a git repository"
            results_record["checks"].append({
                "name": "non_repo_failure_handling",
                "status": "PASS",
                "exit_code": non_repo_res.returncode,
                "stderr": non_repo_res.stderr
            })
        finally:
            shutil.rmtree(non_repo, ignore_errors=True)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    results_record["passed"] = True
    with open(WORK_DIR / "results.json", "w") as f:
        json.dump(results_record, f, indent=2)

    print("All checks for R21-T041 passed successfully!")

if __name__ == "__main__":
    run_tests()
