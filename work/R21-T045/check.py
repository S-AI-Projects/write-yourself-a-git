#!/usr/bin/env python3
"""Validation script for R21-T045: Publish a tested usage example: ref_list."""

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
        "task": "R21-T045",
        "command": "ref_list / show-ref",
        "fixtures": {
            "branch": "refs/heads/master",
            "tag": "refs/tags/v1.0",
            "secondary_branch": "refs/heads/feature"
        }
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
    assert "show-ref and ref_list usage" in test_run.stdout, "show-ref test step missing"
    results_record["checks"].append({
        "name": "native_test_suite",
        "status": "PASS",
        "exit_code": test_run.returncode
    })

    # 2. Complete usage example execution and verification
    temp_dir = Path(tempfile.mkdtemp(prefix="wyag_reflist_test_"))
    try:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_AUTHOR_NAME": "Tester",
            "GIT_AUTHOR_EMAIL": "tester@example.com",
            "GIT_COMMITTER_NAME": "Tester",
            "GIT_COMMITTER_EMAIL": "tester@example.com",
            "HOME": str(temp_dir)
        }

        # Setup repo with commit and multiple refs
        subprocess.run(["git", "init", "-b", "master"], cwd=temp_dir, env=env, capture_output=True, check=True)
        (temp_dir / "notes.txt").write_text("alpha\n")
        (temp_dir / "file with space.txt").write_text("space content\n")
        subprocess.run(["git", "add", "."], cwd=temp_dir, env=env, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "First commit"], cwd=temp_dir, env=env, capture_output=True, check=True)
        subprocess.run(["git", "tag", "v1.0"], cwd=temp_dir, env=env, capture_output=True, check=True)
        subprocess.run(["git", "branch", "feature"], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Execute wyag show-ref
        res = subprocess.run([str(WYAG), "show-ref"], cwd=temp_dir, env=env, capture_output=True, text=True)
        assert res.returncode == 0, f"wyag show-ref failed: {res.stderr}"

        wyag_output = res.stdout.strip().splitlines()
        git_res = subprocess.run(["git", "show-ref"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True)
        git_output = git_res.stdout.strip().splitlines()

        # Both should list refs/heads/feature, refs/heads/master, refs/tags/v1.0
        assert any("refs/heads/master" in line for line in wyag_output), "refs/heads/master missing"
        assert any("refs/heads/feature" in line for line in wyag_output), "refs/heads/feature missing"
        assert any("refs/tags/v1.0" in line for line in wyag_output), "refs/tags/v1.0 missing"

        # Check empty repo handling
        empty_dir = Path(tempfile.mkdtemp(prefix="wyag_empty_refs_"))
        try:
            subprocess.run([str(WYAG), "init", "."], cwd=empty_dir, env=env, capture_output=True, check=True)
            empty_res = subprocess.run([str(WYAG), "show-ref"], cwd=empty_dir, env=env, capture_output=True, text=True)
            assert empty_res.returncode == 0, f"show-ref failed on empty repo: {empty_res.stderr}"
            assert empty_res.stdout.strip() == "", "Expected empty output for empty repo"
        finally:
            shutil.rmtree(empty_dir, ignore_errors=True)

        results_record["checks"].append({
            "name": "usage_example_and_output_verification",
            "status": "PASS",
            "wyag_refs": wyag_output,
            "git_refs": git_output
        })

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    results_record["passed"] = True
    with open(WORK_DIR / "results.json", "w") as f:
        json.dump(results_record, f, indent=2)

    print("All checks for R21-T045 passed successfully!")

if __name__ == "__main__":
    run_tests()
