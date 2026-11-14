#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import libwyag


def get_tool_versions():
    git_ver = subprocess.check_output(["git", "--version"], text=True).strip()
    py_ver = sys.version.replace("\n", " ")
    wyag_path = os.path.join(REPO_ROOT, "wyag")
    return {
        "python": py_ver,
        "git": git_ver,
        "wyag_path": wyag_path
    }


def record_native_tests():
    return [
        "Create repos",
        "status",
        "hash-object",
        "hash-object -w",
        "cat-file",
        "cat-file with long hash",
        "Create commit",
        "cat-file on commit object without indirection",
        "cat-file on tree object redirected from commit",
        "Add some directories and commits",
        "ls-tree",
        "checkout",
        "rev-parse",
        "ls-files",
        "gitignore"
    ]


def setup_temp_repo(work_dir):
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    env["GIT_AUTHOR_NAME"] = "Pritpal Singh"
    env["GIT_AUTHOR_EMAIL"] = "pritpal@example.com"
    env["GIT_AUTHOR_DATE"] = "2026-11-14 00:00:00 +0530"
    env["GIT_COMMITTER_NAME"] = "Pritpal Singh"
    env["GIT_COMMITTER_EMAIL"] = "pritpal@example.com"
    env["GIT_COMMITTER_DATE"] = "2026-11-14 00:00:00 +0530"

    repo_path = os.path.join(work_dir, "test_repo")
    os.makedirs(repo_path, exist_ok=True)

    # Initialize repository with git CLI
    subprocess.run(["git", "init"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    # Create notes.txt containing "alpha\n"
    notes_file = os.path.join(repo_path, "notes.txt")
    with open(notes_file, "w", encoding="utf-8") as f:
        f.write("alpha\n")

    # Create a second file whose name contains a space
    space_file = os.path.join(repo_path, "second file with space.txt")
    with open(space_file, "w", encoding="utf-8") as f:
        f.write("second file content\n")

    # Stage both files and create initial commit
    subprocess.run(["git", "add", "notes.txt", "second file with space.txt"], cwd=repo_path, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    # Add one staged change: modify space_file and git add it
    with open(space_file, "w", encoding="utf-8") as f:
        f.write("second file staged content\n")
    subprocess.run(["git", "add", "second file with space.txt"], cwd=repo_path, check=True, env=env)

    # Add one unstaged change: modify notes.txt without adding it
    with open(notes_file, "w", encoding="utf-8") as f:
        f.write("alpha unstaged modified\n")

    # Add an untracked file to test that shell expansion does not affect unrelated untracked files
    untracked_file = os.path.join(repo_path, "untracked wildcard test.txt")
    with open(untracked_file, "w", encoding="utf-8") as f:
        f.write("untracked file content\n")

    return repo_path, env


def run_checks():
    work_dir = tempfile.mkdtemp(prefix="wyag_ls_files_test_")
    results = []
    cases_executed = 0

    try:
        repo_path, env = setup_temp_repo(work_dir)
        wyag_bin = os.path.join(REPO_ROOT, "wyag")

        # -------------------------------------------------------------
        # Test Case 1: Path containing spaces (assert exact argument boundary)
        # -------------------------------------------------------------
        arg_space = "second file with space.txt"
        cli_proc1 = subprocess.run([sys.executable, wyag_bin, "ls-files", arg_space], cwd=repo_path, capture_output=True, text=True, env=env)
        cases_executed += 1

        git_out1 = subprocess.check_output(["git", "ls-files", arg_space], cwd=repo_path, text=True, env=env).strip()

        assert cli_proc1.returncode == 0, f"wyag ls-files with spaced arg failed: {cli_proc1.stderr}"
        assert cli_proc1.stdout.strip() == arg_space, f"Expected '{arg_space}', got '{cli_proc1.stdout.strip()}'"
        assert cli_proc1.stdout.strip() == git_out1, f"Mismatch with git ls-files: wyag='{cli_proc1.stdout.strip()}', git='{git_out1}'"

        results.append({
            "case": "1: preserve-quoted-path-with-spaces",
            "arguments": ["wyag", "ls-files", arg_space],
            "exit_status": cli_proc1.returncode,
            "stdout": cli_proc1.stdout.strip(),
            "expected_stdout": git_out1,
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 2: Argument containing a wildcard character
        # Assert exact argument boundaries & shell expansion does not affect unrelated untracked files
        # -------------------------------------------------------------
        wildcard_arg = "*.txt"
        cli_proc2 = subprocess.run([sys.executable, wyag_bin, "ls-files", wildcard_arg], cwd=repo_path, capture_output=True, text=True, env=env)
        cases_executed += 1

        git_out2 = subprocess.check_output(["git", "ls-files", wildcard_arg], cwd=repo_path, text=True, env=env).strip()

        assert cli_proc2.returncode == 0, f"wyag ls-files with wildcard failed: {cli_proc2.stderr}"
        wyag_files2 = set(cli_proc2.stdout.strip().splitlines())
        git_files2 = set(git_out2.splitlines())

        # Assert only index entries are returned, and untracked file is NOT included
        assert "untracked wildcard test.txt" not in wyag_files2, "Untracked file unexpectedly included in ls-files output"
        assert "notes.txt" in wyag_files2, "notes.txt missing from wildcard output"
        assert "second file with space.txt" in wyag_files2, "second file with space.txt missing from wildcard output"
        assert wyag_files2 == git_files2, f"Set mismatch with git ls-files: {wyag_files2} vs {git_files2}"

        results.append({
            "case": "2: wildcard-filtering-without-unrelated-file-leak",
            "arguments": ["wyag", "ls-files", wildcard_arg],
            "exit_status": cli_proc2.returncode,
            "stdout": sorted(list(wyag_files2)),
            "untracked_file_excluded": True,
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 3: Combined path containing space and wildcard
        # -------------------------------------------------------------
        combined_arg = "*with space*"
        cli_proc3 = subprocess.run([sys.executable, wyag_bin, "ls-files", combined_arg], cwd=repo_path, capture_output=True, text=True, env=env)
        cases_executed += 1

        git_out3 = subprocess.check_output(["git", "ls-files", combined_arg], cwd=repo_path, text=True, env=env).strip()

        assert cli_proc3.returncode == 0, f"wyag ls-files with combined arg failed: {cli_proc3.stderr}"
        assert cli_proc3.stdout.strip() == "second file with space.txt", f"Unexpected output: {cli_proc3.stdout.strip()}"
        assert cli_proc3.stdout.strip() == git_out3, f"Mismatch with git: {cli_proc3.stdout.strip()} != {git_out3}"

        results.append({
            "case": "3: combined-space-and-wildcard",
            "arguments": ["wyag", "ls-files", combined_arg],
            "exit_status": cli_proc3.returncode,
            "stdout": cli_proc3.stdout.strip(),
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 4: Default behavior without arguments
        # -------------------------------------------------------------
        cli_proc4 = subprocess.run([sys.executable, wyag_bin, "ls-files"], cwd=repo_path, capture_output=True, text=True, env=env)
        cases_executed += 1

        git_out4 = subprocess.check_output(["git", "ls-files"], cwd=repo_path, text=True, env=env).strip()
        assert set(cli_proc4.stdout.strip().splitlines()) == set(git_out4.splitlines()), "Default ls-files mismatch with git"

        results.append({
            "case": "4: default-no-arguments",
            "arguments": ["wyag", "ls-files"],
            "exit_status": cli_proc4.returncode,
            "stdout": cli_proc4.stdout.strip().splitlines(),
            "passed": True
        })

        # -------------------------------------------------------------
        # Test Case 5: Documented failure - invoking outside a git repository
        # -------------------------------------------------------------
        empty_non_repo = os.path.join(work_dir, "non_repo_dir")
        os.makedirs(empty_non_repo, exist_ok=True)
        cli_proc5 = subprocess.run([sys.executable, wyag_bin, "ls-files"], cwd=empty_non_repo, capture_output=True, text=True, env=env)
        cases_executed += 1

        assert cli_proc5.returncode != 0, "Expected non-zero exit code outside git repo"
        assert "No git directory" in cli_proc5.stderr or "No git directory" in cli_proc5.stdout, f"Expected 'No git directory' in error: {cli_proc5.stderr}"

        results.append({
            "case": "5: documented-failure-outside-repository",
            "arguments": ["wyag", "ls-files"],
            "exit_status": cli_proc5.returncode,
            "error_output": cli_proc5.stderr.strip() or cli_proc5.stdout.strip(),
            "passed": True
        })

        # Reject zero-case run
        if cases_executed == 0:
            raise RuntimeError("Zero-case run rejected: No test cases were executed!")

        print(f"Total test cases executed: {cases_executed}")
        for res in results:
            print(f"  [PASS] {res['case']}: exit_status={res['exit_status']}")

        # Save artifacts in work/R21-T034/
        out_dir = os.path.join(REPO_ROOT, "work", "R21-T034")
        os.makedirs(out_dir, exist_ok=True)

        tool_versions = get_tool_versions()
        with open(os.path.join(out_dir, "tool_versions.txt"), "w", encoding="utf-8") as f:
            for k, v in tool_versions.items():
                f.write(f"{k}: {v}\n")

        native_tests = record_native_tests()
        with open(os.path.join(out_dir, "native_test_names.txt"), "w", encoding="utf-8") as f:
            for t in native_tests:
                f.write(f"{t}\n")

        with open(os.path.join(out_dir, "inputs_and_results.json"), "w", encoding="utf-8") as f:
            json.dump({
                "cases_executed": cases_executed,
                "tool_versions": tool_versions,
                "native_test_names": native_tests,
                "results": results
            }, f, indent=2)

        print("\nAll checks completed successfully and artifacts saved to work/R21-T034/")
        return 0

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_checks())
