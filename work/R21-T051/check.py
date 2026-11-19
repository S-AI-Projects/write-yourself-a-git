#!/usr/bin/env python3
import os
import sys
import subprocess
import tempfile
import json
import shutil

def run_cmd(cmd, cwd=None, env=None):
    proc = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode, proc.stdout, proc.stderr

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    wyag_bin = os.path.join(repo_root, "wyag")
    work_dir = os.path.dirname(os.path.abspath(__file__))

    assert os.path.exists(wyag_bin), f"wyag binary not found at {wyag_bin}"

    results = []
    inputs_log = []

    # Record tool versions
    tool_versions = {}
    rc, out, _ = run_cmd(["git", "--version"])
    tool_versions["git"] = out.strip()
    rc, out, _ = run_cmd(["python3", "--version"])
    tool_versions["python3"] = out.strip()
    with open(os.path.join(work_dir, "tool_versions.txt"), "w") as f:
        for k, v in tool_versions.items():
            f.write(f"{k}: {v}\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = os.path.join(tmpdir, "test_repo")
        # Step 2: Initialize repo
        rc, out, err = run_cmd([wyag_bin, "init", repo_dir])
        assert rc == 0, f"Init failed: {err}"
        inputs_log.append({"step": "init", "cmd": [wyag_bin, "init", repo_dir], "rc": rc})

        # Add gitignore
        gitignore_path = os.path.join(repo_dir, ".gitignore")
        with open(gitignore_path, "w") as f:
            f.write("notes.txt\n*.log\nignore_dir/\n")

        # Create notes.txt containing "alpha\n"
        notes_path = os.path.join(repo_dir, "notes.txt")
        with open(notes_path, "w") as f:
            f.write("alpha\n")

        # Create second file whose name contains a space
        space_file = os.path.join(repo_dir, "file with space.txt")
        with open(space_file, "w") as f:
            f.write("tracked content\n")

        # Create staged and unstaged changes
        staged_file = os.path.join(repo_dir, "staged.txt")
        with open(staged_file, "w") as f:
            f.write("staged content\n")

        run_cmd(["git", "add", "staged.txt", ".gitignore"], cwd=repo_dir)
        run_cmd(["git", "commit", "-m", "initial commit", "--no-gpg-sign"], cwd=repo_dir,
                env=dict(os.environ, GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                         GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com"))

        # Unstaged change
        unstaged_file = os.path.join(repo_dir, "unstaged.txt")
        with open(unstaged_file, "w") as f:
            f.write("unstaged content\n")

        # Case 1: Ordinary success (ignored file)
        cmd1 = [wyag_bin, "check-ignore", "notes.txt"]
        rc1, out1, err1 = run_cmd(cmd1, cwd=repo_dir)
        inputs_log.append({"case": "ignored_single", "cmd": cmd1, "rc": rc1, "out": out1, "err": err1})
        assert rc1 == 0, f"Expected rc 0, got {rc1}"
        assert out1.strip() == "notes.txt", f"Expected 'notes.txt', got '{out1.strip()}'"
        results.append({
            "test": "ignored_single_file",
            "args": cmd1,
            "expected_rc": 0,
            "actual_rc": rc1,
            "expected_stdout": "notes.txt\n",
            "actual_stdout": out1,
            "status": "PASS"
        })

        # Case 2: Supported empty/missing-state test (unignored file yields no output)
        cmd2 = [wyag_bin, "check-ignore", "file with space.txt"]
        rc2, out2, err2 = run_cmd(cmd2, cwd=repo_dir)
        inputs_log.append({"case": "unignored_file_with_space", "cmd": cmd2, "rc": rc2, "out": out2, "err": err2})
        assert rc2 == 0, f"Expected rc 0, got {rc2}"
        assert out2 == "", f"Expected empty stdout for unignored file, got '{out2}'"
        results.append({
            "test": "unignored_file_with_space",
            "args": cmd2,
            "expected_rc": 0,
            "actual_rc": rc2,
            "expected_stdout": "",
            "actual_stdout": out2,
            "status": "PASS"
        })

        # Case 3: Multiple files mixed ignored and unignored
        test_log = os.path.join(repo_dir, "app.log")
        with open(test_log, "w") as f:
            f.write("log data\n")
        cmd3 = [wyag_bin, "check-ignore", "notes.txt", "file with space.txt", "app.log", "unstaged.txt"]
        rc3, out3, err3 = run_cmd(cmd3, cwd=repo_dir)
        inputs_log.append({"case": "mixed_multiple_files", "cmd": cmd3, "rc": rc3, "out": out3, "err": err3})
        assert rc3 == 0, f"Expected rc 0, got {rc3}"
        assert out3.strip().splitlines() == ["notes.txt", "app.log"], f"Unexpected output: {out3.strip().splitlines()}"
        results.append({
            "test": "mixed_multiple_files",
            "args": cmd3,
            "expected_rc": 0,
            "actual_rc": rc3,
            "expected_stdout": "notes.txt\napp.log\n",
            "actual_stdout": out3,
            "status": "PASS"
        })

        # Case 4: Edge state - non-existent path matching rule
        cmd4 = [wyag_bin, "check-ignore", "nonexistent.log"]
        rc4, out4, err4 = run_cmd(cmd4, cwd=repo_dir)
        assert rc4 == 0
        assert out4.strip() == "nonexistent.log"
        results.append({
            "test": "nonexistent_ignored_file",
            "args": cmd4,
            "expected_rc": 0,
            "actual_rc": rc4,
            "expected_stdout": "nonexistent.log\n",
            "actual_stdout": out4,
            "status": "PASS"
        })

    # Save outputs to work/R21-T051/
    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump(inputs_log, f, indent=2)

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)

    print("All R21-T051 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
