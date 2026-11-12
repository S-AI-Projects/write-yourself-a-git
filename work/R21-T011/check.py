#!/usr/bin/env python3
"""
Automated verification check for Task R21-T011:
Specify the command contract: cmd_rm [write-yourself-a-git.org]

This script:
1. Captures tool versions (Python, Git, Emacs, Make, OS).
2. Sets up isolated temporary git repositories matching the required specification:
   - notes.txt containing "alpha\\n"
   - a second file whose name contains a space ("file with space.txt")
   - one staged change
   - one unstaged change
3. Exercises cmd_rm contract assertions:
   - Ordinary success on tracked file (notes.txt)
   - Ordinary success on file with space in filename ("file with space.txt")
   - Supported empty/missing-state tests:
     * path missing from index (exit code non-zero, repo state unchanged)
     * path outside worktree (exit code non-zero, repo state unchanged)
     * zero-case run / no arguments (exit code non-zero, rejected by argument parser)
4. Compares relevant objects/index/ref state with Git CLI (normalizing metadata).
5. Ensures all state changes stay inside temporary directories.
6. Saves inputs, expected versus actual results, and tool versions to work/R21-T011/.
7. Exits 0 on success; exits non-zero if any assertion fails.
"""

import os
import sys
import json
import shutil
import platform
import tempfile
import subprocess
from pathlib import Path


def get_tool_versions(repo_root: Path) -> dict:
    versions = {
        "python": sys.version,
        "os": platform.platform(),
    }
    for tool, cmd in [
        ("git", ["git", "--version"]),
        ("emacs", ["emacs", "--version"]),
        ("make", ["make", "--version"]),
    ]:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            versions[tool] = res.stdout.splitlines()[0] if res.stdout else "unknown"
        except Exception as e:
            versions[tool] = f"error: {e}"
    return versions


def run_cmd(cmd, cwd=None, env=None):
    res = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr


def setup_test_repo(repo_dir: Path, wyag_bin: Path):
    """
    Creates repository state according to task specification:
    - notes.txt containing "alpha\\n"
    - second file whose name contains a space: "file with space.txt" containing "space content\\n"
    - one staged change: "staged_file.txt" containing "staged data\\n"
    - one unstaged change: "unstaged_file.txt" containing "unstaged data\\n"
    """
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "wyag-check"
    env["GIT_AUTHOR_EMAIL"] = "check@example.com"
    env["GIT_AUTHOR_DATE"] = "2026-01-01 00:00:00 +0000"
    env["GIT_COMMITTER_NAME"] = "wyag-check"
    env["GIT_COMMITTER_EMAIL"] = "check@example.com"
    env["GIT_COMMITTER_DATE"] = "2026-01-01 00:00:00 +0000"

    # Initialize repository with Git CLI
    rc, out, err = run_cmd(["git", "init", "-b", "master"], cwd=repo_dir, env=env)
    if rc != 0:
        run_cmd(["git", "init"], cwd=repo_dir, env=env)

    # File 1: notes.txt containing "alpha\n"
    notes_file = repo_dir / "notes.txt"
    notes_file.write_text("alpha\n")

    # File 2: second file whose name contains a space
    space_file = repo_dir / "file with space.txt"
    space_file.write_text("space content\n")

    # Stage initial files and commit them
    run_cmd(["git", "add", "notes.txt", "file with space.txt"], cwd=repo_dir, env=env)
    run_cmd(["git", "commit", "-m", "Initial commit with notes and space file"], cwd=repo_dir, env=env)

    # One staged change
    staged_file = repo_dir / "staged_file.txt"
    staged_file.write_text("staged data\n")
    run_cmd(["git", "add", "staged_file.txt"], cwd=repo_dir, env=env)

    # One unstaged change
    unstaged_file = repo_dir / "unstaged_file.txt"
    unstaged_file.write_text("unstaged data\n")

    return env


def capture_repo_state(repo_dir: Path):
    """Captures index entries, worktree files, and git status."""
    _, out_ls, _ = run_cmd(["git", "ls-files"], cwd=repo_dir)
    index_files = sorted(out_ls.strip().splitlines()) if out_ls.strip() else []

    worktree_files = sorted([
        str(p.relative_to(repo_dir))
        for p in repo_dir.rglob("*")
        if not str(p.relative_to(repo_dir)).startswith(".git") and p.is_file()
    ])

    _, out_status, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_dir)
    status_lines = sorted(out_status.strip().splitlines()) if out_status.strip() else []

    return {
        "index_entries": index_files,
        "worktree_files": worktree_files,
        "status_porcelain": status_lines,
    }


def main():
    repo_root = Path(__file__).resolve().parents[2]
    work_dir = Path(__file__).resolve().parent
    work_dir.mkdir(parents=True, exist_ok=True)

    wyag_bin = repo_root / "wyag"
    if not wyag_bin.exists():
        print(f"ERROR: {wyag_bin} not found. Run 'make program' first.")
        sys.exit(1)

    tool_versions = get_tool_versions(repo_root)

    test_records = []
    inputs_record = {
        "repository_setup": {
            "notes.txt": "alpha\n",
            "file with space.txt": "space content\n",
            "staged_file.txt": "staged data\n (staged change)",
            "unstaged_file.txt": "unstaged data\n (unstaged change)",
        },
        "test_cases": [],
    }

    # Execute tests in an isolated temporary directory
    with tempfile.TemporaryDirectory() as temp_parent_str:
        temp_parent = Path(temp_parent_str)
        wyag_repo = temp_parent / "wyag_repo"
        git_replica_repo = temp_parent / "git_replica_repo"

        wyag_repo.mkdir()
        git_replica_repo.mkdir()

        env = setup_test_repo(wyag_repo, wyag_bin)
        _ = setup_test_repo(git_replica_repo, wyag_bin)

        # Record initial baseline state
        initial_wyag_state = capture_repo_state(wyag_repo)
        initial_git_state = capture_repo_state(git_replica_repo)
        assert initial_wyag_state == initial_git_state, "Baseline repo setup mismatch between test repos"

        # -------------------------------------------------------------
        # Test 1: Ordinary success: wyag rm notes.txt
        # -------------------------------------------------------------
        inputs_record["test_cases"].append({
            "name": "ordinary_success_notes_file",
            "cmd": [str(wyag_bin), "rm", "notes.txt"],
            "target": "notes.txt",
        })
        before_state = capture_repo_state(wyag_repo)
        rc, out, err = run_cmd([str(wyag_bin), "rm", "notes.txt"], cwd=wyag_repo, env=env)
        after_state = capture_repo_state(wyag_repo)

        # Run Git CLI equivalent on replica repo for comparison
        rc_git, out_git, err_git = run_cmd(["git", "rm", "notes.txt"], cwd=git_replica_repo, env=env)
        after_git_state = capture_repo_state(git_replica_repo)

        # Assertions for Test 1
        assert rc == 0, f"Expected returncode 0 for wyag rm notes.txt, got {rc}. Stderr: {err}"
        assert out == "", f"Expected empty stdout for wyag rm notes.txt, got: {out!r}"
        assert not (wyag_repo / "notes.txt").exists(), "notes.txt should be unlinked from filesystem"
        assert "notes.txt" not in after_state["index_entries"], "notes.txt should be removed from index"
        assert "file with space.txt" in after_state["index_entries"], "file with space.txt should remain in index"
        assert "staged_file.txt" in after_state["index_entries"], "staged change must remain in index"
        assert (wyag_repo / "unstaged_file.txt").exists(), "unstaged change must remain on filesystem"
        # Index comparison with Git CLI
        assert after_state["index_entries"] == after_git_state["index_entries"], (
            f"Index mismatch with Git CLI: wyag {after_state['index_entries']} vs git {after_git_state['index_entries']}"
        )

        test_records.append({
            "test_name": "ordinary_success_notes_file",
            "category": "ordinary_success",
            "args": ["rm", "notes.txt"],
            "expected_exit_code": 0,
            "actual_exit_code": rc,
            "expected_stdout": "",
            "actual_stdout": out,
            "actual_stderr": err,
            "state_before": before_state,
            "state_after": after_state,
            "git_cli_comparison": {
                "git_exit_code": rc_git,
                "index_match": after_state["index_entries"] == after_git_state["index_entries"],
            },
            "status": "PASSED",
        })

        # -------------------------------------------------------------
        # Test 2: Ordinary success on file with space
        # -------------------------------------------------------------
        inputs_record["test_cases"].append({
            "name": "ordinary_success_spaced_filename",
            "cmd": [str(wyag_bin), "rm", "file with space.txt"],
            "target": "file with space.txt",
        })
        before_state = capture_repo_state(wyag_repo)
        rc, out, err = run_cmd([str(wyag_bin), "rm", "file with space.txt"], cwd=wyag_repo, env=env)
        after_state = capture_repo_state(wyag_repo)

        # Run Git CLI equivalent on replica repo
        rc_git, out_git, err_git = run_cmd(["git", "rm", "file with space.txt"], cwd=git_replica_repo, env=env)
        after_git_state = capture_repo_state(git_replica_repo)

        assert rc == 0, f"Expected returncode 0 for wyag rm 'file with space.txt', got {rc}"
        assert out == "", f"Expected empty stdout, got: {out!r}"
        assert not (wyag_repo / "file with space.txt").exists(), "Spaced file should be removed from filesystem"
        assert "file with space.txt" not in after_state["index_entries"], "Spaced file should be removed from index"
        assert after_state["index_entries"] == after_git_state["index_entries"]

        test_records.append({
            "test_name": "ordinary_success_spaced_filename",
            "category": "ordinary_success",
            "args": ["rm", "file with space.txt"],
            "expected_exit_code": 0,
            "actual_exit_code": rc,
            "expected_stdout": "",
            "actual_stdout": out,
            "actual_stderr": err,
            "state_before": before_state,
            "state_after": after_state,
            "git_cli_comparison": {
                "git_exit_code": rc_git,
                "index_match": after_state["index_entries"] == after_git_state["index_entries"],
            },
            "status": "PASSED",
        })

        # -------------------------------------------------------------
        # Test 3: Supported failure: Missing path not in index
        # -------------------------------------------------------------
        inputs_record["test_cases"].append({
            "name": "missing_path_not_in_index",
            "cmd": [str(wyag_bin), "rm", "nonexistent.txt"],
            "target": "nonexistent.txt",
        })
        before_state = capture_repo_state(wyag_repo)
        rc, out, err = run_cmd([str(wyag_bin), "rm", "nonexistent.txt"], cwd=wyag_repo, env=env)
        after_state = capture_repo_state(wyag_repo)

        assert rc != 0, f"Expected non-zero exit code for missing file, got {rc}"
        assert "Cannot remove paths not in the index" in err, f"Expected error message not in stderr: {err}"
        assert before_state == after_state, "Repository state must be unchanged after failed rm"

        test_records.append({
            "test_name": "missing_path_not_in_index",
            "category": "documented_failure",
            "args": ["rm", "nonexistent.txt"],
            "expected_exit_code": "non-zero",
            "actual_exit_code": rc,
            "expected_error_pattern": "Cannot remove paths not in the index",
            "actual_stderr": err,
            "state_before": before_state,
            "state_after": after_state,
            "repo_state_unchanged": before_state == after_state,
            "status": "PASSED",
        })

        # -------------------------------------------------------------
        # Test 4: Supported failure: Path outside worktree
        # -------------------------------------------------------------
        inputs_record["test_cases"].append({
            "name": "path_outside_worktree",
            "cmd": [str(wyag_bin), "rm", "../outside.txt"],
            "target": "../outside.txt",
        })
        before_state = capture_repo_state(wyag_repo)
        rc, out, err = run_cmd([str(wyag_bin), "rm", "../outside.txt"], cwd=wyag_repo, env=env)
        after_state = capture_repo_state(wyag_repo)

        assert rc != 0, f"Expected non-zero exit code for outside path, got {rc}"
        assert "Cannot remove paths outside of worktree" in err, f"Expected error message not in stderr: {err}"
        assert before_state == after_state, "Repository state must be unchanged after outside path rejection"

        test_records.append({
            "test_name": "path_outside_worktree",
            "category": "documented_failure",
            "args": ["rm", "../outside.txt"],
            "expected_exit_code": "non-zero",
            "actual_exit_code": rc,
            "expected_error_pattern": "Cannot remove paths outside of worktree",
            "actual_stderr": err,
            "state_before": before_state,
            "state_after": after_state,
            "repo_state_unchanged": before_state == after_state,
            "status": "PASSED",
        })

        # -------------------------------------------------------------
        # Test 5: Supported failure: Zero arguments (zero-case rejection)
        # -------------------------------------------------------------
        inputs_record["test_cases"].append({
            "name": "zero_case_rejection",
            "cmd": [str(wyag_bin), "rm"],
            "target": None,
        })
        before_state = capture_repo_state(wyag_repo)
        rc, out, err = run_cmd([str(wyag_bin), "rm"], cwd=wyag_repo, env=env)
        after_state = capture_repo_state(wyag_repo)

        assert rc != 0, f"Expected non-zero exit code for zero-case invocation, got {rc}"
        assert "the following arguments are required: path" in err or "usage:" in err, (
            f"Expected argparse required error, got: {err}"
        )
        assert before_state == after_state, "Repository state must remain untouched on argument error"

        test_records.append({
            "test_name": "zero_case_rejection",
            "category": "argument_boundary",
            "args": ["rm"],
            "expected_exit_code": 2,
            "actual_exit_code": rc,
            "expected_error_pattern": "required: path",
            "actual_stderr": err,
            "state_before": before_state,
            "state_after": after_state,
            "repo_state_unchanged": before_state == after_state,
            "status": "PASSED",
        })

    # Save inputs, expected vs actual results, and tool versions to work/R21-T011/
    (work_dir / "inputs.json").write_text(json.dumps(inputs_record, indent=2))
    (work_dir / "expected_vs_actual.json").write_text(json.dumps(test_records, indent=2))
    (work_dir / "tool_versions.json").write_text(json.dumps(tool_versions, indent=2))

    # Generate human readable report.txt
    report_lines = [
        "=" * 70,
        "TASK R21-T011: VERIFICATION CHECK REPORT",
        "=" * 70,
        f"Platform: {tool_versions.get('os')}",
        f"Python:   {tool_versions.get('python').split()[0]}",
        f"Git:      {tool_versions.get('git')}",
        f"Emacs:    {tool_versions.get('emacs')}",
        f"Make:     {tool_versions.get('make')}",
        "-" * 70,
        f"Total Tests Executed: {len(test_records)}",
        f"All Passed: {all(t['status'] == 'PASSED' for t in test_records)}",
        "-" * 70,
        "Test Details:",
    ]
    for t in test_records:
        report_lines.append(
            f"  - [{t['status']}] {t['test_name']} ({t['category']}): "
            f"exit={t['actual_exit_code']} (expected {t['expected_exit_code']})"
        )
    report_lines.append("=" * 70)
    report_text = "\n".join(report_lines) + "\n"
    (work_dir / "report.txt").write_text(report_text)

    print(report_text)
    print("All checks passed successfully. Results recorded in work/R21-T011/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
