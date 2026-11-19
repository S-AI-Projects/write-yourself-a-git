#!/usr/bin/env python3
"""Validation script for R21-T050: Exercise argument boundaries: object_read."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zlib
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
        "task": "R21-T050",
        "function": "object_read",
        "boundary_cases": [
            "valid_sha_blob_read",
            "none_argument_returns_none",
            "empty_string_returns_none",
            "single_char_returns_none",
            "invalid_type_returns_none",
            "nonexistent_40_char_hex_returns_none",
            "bytes_encoded_sha_handled",
            "malformed_header_delimiter_raises_exception",
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
    assert "object_read argument boundaries" in test_run.stdout, "object_read argument boundaries step missing"
    results_record["checks"].append({
        "name": "native_test_suite",
        "status": "PASS",
        "exit_code": test_run.returncode
    })

    # 2. Focused checks with isolated temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix="wyag_object_read_"))
    try:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(temp_dir),
            "PYTHONPATH": str(REPO_ROOT)
        }
        (temp_dir / ".gitconfig").write_text("[user]\n    name = Tester\n    email = tester@example.com\n")

        # Initialize repository
        subprocess.run([str(WYAG), "init", "."], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Worktree fixture: notes.txt with "alpha\n", file with space, staged and unstaged edits
        (temp_dir / "notes.txt").write_text("alpha\n")
        (temp_dir / "file with space.txt").write_text("space content\n")
        subprocess.run([str(WYAG), "add", "notes.txt", "file with space.txt"], cwd=temp_dir, env=env, capture_output=True, check=True)
        (temp_dir / "notes.txt").write_text("alpha unstaged edit\n")

        # Hash an object
        hash_res = subprocess.run([str(WYAG), "hash-object", "-w", "file with space.txt"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True)
        valid_sha = hash_res.stdout.strip()

        sys.path.insert(0, str(REPO_ROOT))
        import libwyag

        repo = libwyag.repo_find(str(temp_dir))
        assert repo is not None, "Failed to find repository"

        # Case 1: Valid SHA
        obj = libwyag.object_read(repo, valid_sha)
        assert isinstance(obj, libwyag.GitBlob), f"Expected GitBlob, got {type(obj)}"
        assert obj.blobdata == b"space content\n"
        results_record["checks"].append({
            "name": "valid_sha",
            "sha": valid_sha,
            "type": "blob",
            "status": "PASS"
        })

        # Case 2: None input
        assert libwyag.object_read(repo, None) is None
        results_record["checks"].append({"name": "none_input", "result": None, "status": "PASS"})

        # Case 3: Empty string
        assert libwyag.object_read(repo, "") is None
        results_record["checks"].append({"name": "empty_string_input", "result": None, "status": "PASS"})

        # Case 4: Length < 2 chars
        assert libwyag.object_read(repo, "a") is None
        results_record["checks"].append({"name": "single_char_input", "result": None, "status": "PASS"})

        # Case 5: Invalid type input (integer)
        assert libwyag.object_read(repo, 12345) is None
        results_record["checks"].append({"name": "invalid_type_input", "result": None, "status": "PASS"})

        # Case 6: Non-existent 40-char SHA
        assert libwyag.object_read(repo, "0000000000000000000000000000000000000000") is None
        results_record["checks"].append({"name": "nonexistent_sha", "result": None, "status": "PASS"})

        # Case 7: Bytes-encoded SHA
        obj_bytes = libwyag.object_read(repo, valid_sha.encode("ascii"))
        assert isinstance(obj_bytes, libwyag.GitBlob)
        assert obj_bytes.blobdata == b"space content\n"
        results_record["checks"].append({"name": "bytes_encoded_sha", "status": "PASS"})

        # Case 8: Malformed object header (missing space delimiter)
        malformed_sha = "ff" + "00" * 19
        malformed_path = Path(repo.gitdir) / "objects" / malformed_sha[:2] / malformed_sha[2:]
        malformed_path.parent.mkdir(parents=True, exist_ok=True)
        # Create malformed zlib data with no space header
        malformed_path.write_bytes(zlib.compress(b"blob14\x00malformeddata!"))
        malformed_caught = False
        try:
            libwyag.object_read(repo, malformed_sha)
        except Exception as e:
            malformed_caught = True
            assert "missing type header delimiter" in str(e)
        assert malformed_caught, "Expected Exception for missing header delimiter"
        results_record["checks"].append({"name": "malformed_header_exception", "exception_caught": True, "status": "PASS"})

        # Check git CLI status
        git_status = subprocess.run(["git", "status", "--porcelain"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True).stdout
        assert "notes.txt" in git_status
        assert "file with space.txt" in git_status
        results_record["checks"].append({
            "name": "git_cli_comparison",
            "status_output": git_status.strip().splitlines(),
            "status": "PASS"
        })

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    results_record["passed"] = True
    with open(WORK_DIR / "results.json", "w") as f:
        json.dump(results_record, f, indent=2)

    print("All checks for R21-T050 passed successfully!")

if __name__ == "__main__":
    run_tests()
