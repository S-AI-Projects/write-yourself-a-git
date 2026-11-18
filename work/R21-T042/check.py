#!/usr/bin/env python3
"""Validation script for R21-T042: Isolate environment dependencies: cmd_status_branch."""

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
        "task": "R21-T042",
        "item": "cmd_status_branch",
        "scenarios": [
            "named active branch",
            "detached HEAD state",
            "environment isolation with sanitized environment"
        ]
    }
    with open(WORK_DIR / "inputs.json", "w") as f:
        json.dump(inputs_record, f, indent=2)

    results_record = {
        "checks": [],
        "passed": False
    }

    # 1. Native test suite check
    print("Running native test suite...")
    test_run = subprocess.run(["./wyag-tests.sh"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert test_run.returncode == 0, f"wyag-tests.sh failed:\n{test_run.stderr}"
    assert "cmd_status_branch isolation" in test_run.stdout, "cmd_status_branch test step missing"
    results_record["checks"].append({
        "name": "native_test_suite",
        "status": "PASS",
        "exit_code": test_run.returncode
    })

    # 2. Branch vs Detached HEAD isolated test
    temp_dir = Path(tempfile.mkdtemp(prefix="wyag_branch_test_"))
    try:
        # Isolated env
        env = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_AUTHOR_NAME": "Tester",
            "GIT_AUTHOR_EMAIL": "tester@example.com",
            "GIT_COMMITTER_NAME": "Tester",
            "GIT_COMMITTER_EMAIL": "tester@example.com",
            "HOME": str(temp_dir)
        }

        # Init with specific branch name
        subprocess.run(["git", "init", "-b", "release-2.0"], cwd=temp_dir, capture_output=True, check=True)
        (temp_dir / "notes.txt").write_text("alpha\n")
        (temp_dir / "file with space.txt").write_text("space content\n")
        subprocess.run(["git", "add", "."], cwd=temp_dir, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial release"], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Stage one change and leave one unstaged
        (temp_dir / "notes.txt").write_text("alpha\nupdated\n")
        subprocess.run(["git", "add", "notes.txt"], cwd=temp_dir, capture_output=True, check=True)
        (temp_dir / "file with space.txt").write_text("space content\nmodified\n")

        # Test active branch
        res_branch = subprocess.run([str(WYAG), "status"], cwd=temp_dir, env=env, capture_output=True, text=True)
        assert res_branch.returncode == 0, f"wyag status failed on branch: {res_branch.stderr}"
        assert "On branch release-2.0." in res_branch.stdout, "Expected active branch name in output"
        results_record["checks"].append({
            "name": "active_branch_resolution",
            "status": "PASS",
            "output": res_branch.stdout.splitlines()[0]
        })

        # Test detached HEAD state
        commit_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_dir, capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["git", "checkout", commit_sha], cwd=temp_dir, env=env, capture_output=True, check=True)
        res_detached = subprocess.run([str(WYAG), "status"], cwd=temp_dir, env=env, capture_output=True, text=True)
        assert res_detached.returncode == 0, f"wyag status failed on detached HEAD: {res_detached.stderr}"
        assert f"HEAD detached at {commit_sha}" in res_detached.stdout, "Expected detached HEAD message with commit sha"
        results_record["checks"].append({
            "name": "detached_head_resolution",
            "status": "PASS",
            "output": res_detached.stdout.splitlines()[0]
        })

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    results_record["passed"] = True
    with open(WORK_DIR / "results.json", "w") as f:
        json.dump(results_record, f, indent=2)

    print("All checks for R21-T042 passed successfully!")

if __name__ == "__main__":
    run_tests()
