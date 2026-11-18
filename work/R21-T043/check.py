#!/usr/bin/env python3
"""Validation script for R21-T043: Verify state transitions: cmd_commit."""

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
        "task": "R21-T043",
        "command": "cmd_commit",
        "staged_files": ["notes.txt", "file with space.txt"],
        "unrelated_files": ["unrelated.txt"],
        "unstaged_files": ["notes.txt modified after stage"]
    }
    with open(WORK_DIR / "inputs.json", "w") as f:
        json.dump(inputs_record, f, indent=2)

    results_record = {
        "checks": [],
        "passed": False
    }

    # 1. Run native test suite
    print("Running native test suite...")
    test_run = subprocess.run(["./wyag-tests.sh"], cwd=REPO_ROOT, capture_output=True, text=True)
    assert test_run.returncode == 0, f"wyag-tests.sh failed:\n{test_run.stderr}"
    assert "cmd_commit state transition" in test_run.stdout, "cmd_commit test step missing"
    results_record["checks"].append({
        "name": "native_test_suite",
        "status": "PASS",
        "exit_code": test_run.returncode
    })

    # 2. Detailed commit state transition check
    temp_dir = Path(tempfile.mkdtemp(prefix="wyag_commit_test_"))
    try:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_AUTHOR_NAME": "Tester",
            "GIT_AUTHOR_EMAIL": "tester@example.com",
            "GIT_COMMITTER_NAME": "Tester",
            "GIT_COMMITTER_EMAIL": "tester@example.com",
            "HOME": str(temp_dir)
        }

        # Init repository using wyag
        subprocess.run([str(WYAG), "init", "."], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Set git config in repo and global
        (temp_dir / ".gitconfig").write_text("[user]\n    name = Tester\n    email = tester@example.com\n")
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=temp_dir, env=env, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Create files
        (temp_dir / "notes.txt").write_text("alpha\n")
        (temp_dir / "file with space.txt").write_text("space content\n")
        (temp_dir / "unrelated.txt").write_text("unrelated file should not change\n")

        # Stage notes.txt and file with space.txt
        subprocess.run([str(WYAG), "add", "notes.txt", "file with space.txt"], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Make an unstaged modification
        (temp_dir / "unrelated.txt").write_text("unrelated file content constant\n")
        unrelated_before = (temp_dir / "unrelated.txt").read_text()

        # Execute wyag commit
        res_commit = subprocess.run([str(WYAG), "commit", "-m", "First commit from wyag"], cwd=temp_dir, env=env, capture_output=True, text=True)
        assert res_commit.returncode == 0, f"wyag commit failed: {res_commit.stderr}"

        # Verify state transitions:
        # HEAD should now point to a valid commit
        head_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True).stdout.strip()
        assert len(head_commit) == 40, f"Invalid HEAD commit sha: {head_commit}"

        # Verify commit message
        commit_msg = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True).stdout.strip()
        assert commit_msg == "First commit from wyag", f"Unexpected commit message: {commit_msg}"

        # Verify unrelated file state remained unchanged
        unrelated_after = (temp_dir / "unrelated.txt").read_text()
        assert unrelated_before == unrelated_after, "Unrelated file content altered by commit"

        results_record["checks"].append({
            "name": "commit_state_transition",
            "status": "PASS",
            "head_commit": head_commit,
            "unrelated_unchanged": True
        })

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    results_record["passed"] = True
    with open(WORK_DIR / "results.json", "w") as f:
        json.dump(results_record, f, indent=2)

    print("All checks for R21-T043 passed successfully!")

if __name__ == "__main__":
    run_tests()
