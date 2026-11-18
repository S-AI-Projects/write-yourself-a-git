#!/usr/bin/env python3
"""Validation script for R21-T044: Preserve quoted arguments: cmd_add."""

import glob
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
        "task": "R21-T044",
        "command": "cmd_add",
        "fixtures": {
            "file_with_space": "file with space.txt",
            "wildcard_targets": ["target_a.txt", "target_b.txt"],
            "unrelated_file": "unrelated.txt"
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
    assert "cmd_add path quoting" in test_run.stdout, "cmd_add quoting test step missing"
    results_record["checks"].append({
        "name": "native_test_suite",
        "status": "PASS",
        "exit_code": test_run.returncode
    })

    # 2. Detailed quoting & wildcard check
    temp_dir = Path(tempfile.mkdtemp(prefix="wyag_add_test_"))
    try:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(temp_dir)
        }

        # Initialize repository
        subprocess.run([str(WYAG), "init", "."], cwd=temp_dir, env=env, capture_output=True, check=True)

        (temp_dir / "notes.txt").write_text("alpha\n")
        (temp_dir / "file with space.txt").write_text("space content\n")
        (temp_dir / "target_a.txt").write_text("wildcard a\n")
        (temp_dir / "target_b.txt").write_text("wildcard b\n")
        (temp_dir / "unrelated.txt").write_text("should remain unstaged\n")

        # Invoke add with spaced filename and wildcard arguments
        wildcard_files = [os.path.basename(p) for p in glob.glob(str(temp_dir / "target_*.txt"))]
        add_args = ["file with space.txt"] + wildcard_files

        res_add = subprocess.run([str(WYAG), "add"] + add_args, cwd=temp_dir, env=env, capture_output=True, text=True)
        assert res_add.returncode == 0, f"wyag add failed: {res_add.stderr}"

        # Inspect staged entries
        res_ls = subprocess.run([str(WYAG), "ls-files"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True)
        staged_files = res_ls.stdout.splitlines()

        assert "file with space.txt" in staged_files, "Spaced file not preserved in index"
        assert "target_a.txt" in staged_files, "Target A missing from index"
        assert "target_b.txt" in staged_files, "Target B missing from index"
        assert "unrelated.txt" not in staged_files, "Unrelated file incorrectly added"
        assert "notes.txt" not in staged_files, "notes.txt incorrectly added"

        results_record["checks"].append({
            "name": "argument_boundaries_and_isolation",
            "status": "PASS",
            "staged_entries": staged_files
        })

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    results_record["passed"] = True
    with open(WORK_DIR / "results.json", "w") as f:
        json.dump(results_record, f, indent=2)

    print("All checks for R21-T044 passed successfully!")

if __name__ == "__main__":
    run_tests()
