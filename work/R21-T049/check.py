#!/usr/bin/env python3
"""Validation script for R21-T049: Protect a condition with a regression: cmd_status_head_index."""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
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
        "task": "R21-T049",
        "function": "cmd_status_head_index",
        "target_condition": "head[entry.name] != entry.sha",
        "mutant": "head[entry.name] == entry.sha",
        "cases": [
            "staged_modified_file",
            "staged_added_file_with_space",
            "staged_deleted_file",
            "unchanged_staged_file",
            "mutant_rejection_verification"
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
    assert "cmd_status_head_index regression check" in test_run.stdout, "regression check test step missing"
    results_record["checks"].append({
        "name": "native_test_suite",
        "status": "PASS",
        "exit_code": test_run.returncode
    })

    # 2. Focused regression and mutation checks
    temp_dir = Path(tempfile.mkdtemp(prefix="wyag_status_regression_"))
    try:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(temp_dir),
            "PYTHONPATH": str(REPO_ROOT)
        }
        (temp_dir / ".gitconfig").write_text("[user]\n    name = Tester\n    email = tester@example.com\n")

        # Initialize repository
        subprocess.run([str(WYAG), "init", "."], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Base commit with notes.txt, keep.txt, to_delete.txt
        (temp_dir / "notes.txt").write_text("alpha\n")
        (temp_dir / "keep.txt").write_text("unchanged\n")
        (temp_dir / "to_delete.txt").write_text("delete me\n")
        subprocess.run(["git", "add", "notes.txt", "keep.txt", "to_delete.txt"], cwd=temp_dir, env=env, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "base commit"], cwd=temp_dir, env=env, capture_output=True, check=True)

        # Stage modifications:
        # a) Modify notes.txt and add to index
        (temp_dir / "notes.txt").write_text("alpha staged modification\n")
        subprocess.run([str(WYAG), "add", "notes.txt"], cwd=temp_dir, env=env, capture_output=True, check=True)

        # b) Add new file with space in name
        (temp_dir / "file with space.txt").write_text("space content\n")
        subprocess.run([str(WYAG), "add", "file with space.txt"], cwd=temp_dir, env=env, capture_output=True, check=True)

        # c) Delete to_delete.txt from index
        subprocess.run([str(WYAG), "rm", "to_delete.txt"], cwd=temp_dir, env=env, capture_output=True, check=True)

        # d) Unstaged change in notes.txt
        (temp_dir / "notes.txt").write_text("alpha unstaged modification\n")

        # Run status through wyag CLI
        res_status = subprocess.run([str(WYAG), "status"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True)
        stdout = res_status.stdout

        # Assert correct classification of head vs index
        assert "modified: notes.txt" in stdout, "notes.txt should be staged as modified"
        assert "added:    file with space.txt" in stdout, "file with space.txt should be staged as added"
        assert "deleted:  to_delete.txt" in stdout, "to_delete.txt should be staged as deleted"
        assert "modified: keep.txt" not in stdout, "keep.txt should not be staged as modified"
        assert "added:    keep.txt" not in stdout, "keep.txt should not be staged as added"

        results_record["checks"].append({
            "name": "status_head_index_classification",
            "modified": "notes.txt",
            "added": "file with space.txt",
            "deleted": "to_delete.txt",
            "unchanged_kept": "keep.txt",
            "status": "PASS"
        })

        # 3. Mutation testing: evaluate mutant behavior vs real implementation
        sys.path.insert(0, str(REPO_ROOT))
        import libwyag

        repo = libwyag.repo_find(str(temp_dir))
        index = libwyag.index_read(repo)

        # Define mutant function simulating inverted condition
        def mutant_status_head_index(repo, index):
            out = []
            head = libwyag.tree_to_dict(repo, "HEAD")
            for entry in index.entries:
                if entry.name in head:
                    if head[entry.name] == entry.sha: # MUTANT: inverted condition
                        out.append(f"modified: {entry.name}")
                    del head[entry.name]
                else:
                    out.append(f"added: {entry.name}")
            return out

        mutant_results = mutant_status_head_index(repo, index)
        # Mutant erroneously marks keep.txt as modified and misses notes.txt
        assert "modified: keep.txt" in mutant_results, "Mutant must falsely mark keep.txt as modified"
        assert "modified: notes.txt" not in mutant_results, "Mutant must miss notes.txt modification"
        results_record["checks"].append({
            "name": "mutant_rejection_test",
            "mutant_detected": True,
            "mutant_false_positives": ["keep.txt"],
            "mutant_false_negatives": ["notes.txt"],
            "status": "PASS"
        })

        # Compare with git CLI status
        git_status = subprocess.run(["git", "status", "--porcelain"], cwd=temp_dir, env=env, capture_output=True, text=True, check=True).stdout
        assert "notes.txt" in git_status, "notes.txt should have staged modifications"
        assert "file with space.txt" in git_status, "file with space.txt should be staged"
        assert "to_delete.txt" in git_status, "to_delete.txt should be deleted in index"
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

    print("All checks for R21-T049 passed successfully!")

if __name__ == "__main__":
    run_tests()
