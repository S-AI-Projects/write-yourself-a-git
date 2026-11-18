#!/usr/bin/env python3
"""Validation script for R21-T046: Clarify one source responsibility: commit_create."""

from datetime import datetime, timezone, timedelta
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
        "task": "R21-T046",
        "function": "commit_create",
        "characterization_cases": [
            "root commit without parent",
            "child commit with parent SHA",
            "timezone offset formatting",
            "commit message trimming"
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
    assert "commit_create characterization" in test_run.stdout, "commit_create characterization test step missing"
    results_record["checks"].append({
        "name": "native_test_suite",
        "status": "PASS",
        "exit_code": test_run.returncode
    })

    # 2. Detailed characterization test
    temp_dir = Path(tempfile.mkdtemp(prefix="wyag_commit_create_"))
    try:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(temp_dir)
        }
        (temp_dir / ".gitconfig").write_text("[user]\n    name = Tester\n    email = tester@example.com\n")

        subprocess.run([str(WYAG), "init", "."], cwd=temp_dir, env=env, capture_output=True, check=True)
        (temp_dir / "notes.txt").write_text("alpha\n")
        (temp_dir / "file with space.txt").write_text("space content\n")
        subprocess.run([str(WYAG), "add", "notes.txt", "file with space.txt"], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Root commit
        res_c1 = subprocess.run([str(WYAG), "commit", "-m", "  Root message with spaces  "], cwd=temp_dir, env=env, capture_output=True, text=True)
        assert res_c1.returncode == 0, f"wyag commit root failed: {res_c1.stderr}"

        c1_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True).stdout.strip()
        cat_c1 = subprocess.run([str(WYAG), "cat-file", "commit", c1_sha], cwd=temp_dir, env=env, capture_output=True, text=True, check=True).stdout
        assert "parent" not in cat_c1, "Root commit must not have parent header"
        assert "Root message with spaces" in cat_c1, "Message content missing"

        # Child commit
        (temp_dir / "notes.txt").write_text("alpha beta\n")
        subprocess.run([str(WYAG), "add", "notes.txt"], cwd=temp_dir, env=env, capture_output=True, check=True)
        res_c2 = subprocess.run([str(WYAG), "commit", "-m", "Child commit"], cwd=temp_dir, env=env, capture_output=True, text=True)
        assert res_c2.returncode == 0, f"wyag commit child failed: {res_c2.stderr}"

        c2_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True).stdout.strip()
        cat_c2 = subprocess.run([str(WYAG), "cat-file", "commit", c2_sha], cwd=temp_dir, env=env, capture_output=True, text=True, check=True).stdout
        assert f"parent {c1_sha}" in cat_c2, "Child commit must reference parent commit SHA"

        results_record["checks"].append({
            "name": "commit_create_characterization",
            "status": "PASS",
            "root_sha": c1_sha,
            "child_sha": c2_sha,
            "parent_verified": True
        })

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    results_record["passed"] = True
    with open(WORK_DIR / "results.json", "w") as f:
        json.dump(results_record, f, indent=2)

    print("All checks for R21-T046 passed successfully!")

if __name__ == "__main__":
    run_tests()
