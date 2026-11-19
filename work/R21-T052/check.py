#!/usr/bin/env python3
import os
import sys
import subprocess
import tempfile
import json
import io
from contextlib import redirect_stdout

def run_cmd(cmd, cwd=None, env=None):
    proc = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode, proc.stdout, proc.stderr

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    wyag_bin = os.path.join(repo_root, "wyag")
    work_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, repo_root)

    import libwyag

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
        rc, out, err = run_cmd([wyag_bin, "init", repo_dir])
        assert rc == 0, f"Init failed: {err}"

        # notes.txt with "alpha\n"
        with open(os.path.join(repo_dir, "notes.txt"), "w") as f:
            f.write("alpha\n")

        # file with space
        with open(os.path.join(repo_dir, "file with space.txt"), "w") as f:
            f.write("data\n")

        # Staged change
        with open(os.path.join(repo_dir, "staged.txt"), "w") as f:
            f.write("staged content\n")

        run_cmd(["git", "add", "notes.txt", "staged.txt"], cwd=repo_dir)
        git_env = dict(os.environ,
                       GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                       GIT_AUTHOR_DATE="2020-01-01 00:00:00 +0000",
                       GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com",
                       GIT_COMMITTER_DATE="2020-01-01 00:00:00 +0000")
        rc, out, err = run_cmd(["git", "commit", "-m", "Commit 1", "--no-gpg-sign"], cwd=repo_dir, env=git_env)
        assert rc == 0, f"Commit 1 failed: {err}"

        # Unstaged change
        with open(os.path.join(repo_dir, "unstaged.txt"), "w") as f:
            f.write("unstaged\n")

        # Commit 2
        with open(os.path.join(repo_dir, "notes.txt"), "a") as f:
            f.write("beta\n")
        run_cmd(["git", "add", "notes.txt"], cwd=repo_dir)
        run_cmd(["git", "commit", "-m", "Commit 2", "--no-gpg-sign"], cwd=repo_dir, env=git_env)

        repo = libwyag.repo_find(repo_dir)
        head_sha = libwyag.object_find(repo, "HEAD")

        # Test Case 1: Minimum accepted argument list (repo, sha) - seen defaults to None/set()
        f_buf = io.StringIO()
        with redirect_stdout(f_buf):
            libwyag.log_graphviz(repo, head_sha)
        out1 = f_buf.getvalue()
        assert f"c_{head_sha}" in out1
        assert "Commit 2" in out1
        results.append({
            "test": "minimum_arguments_repo_sha",
            "inputs": {"sha": head_sha, "seen": "omitted"},
            "actual_rc": 0,
            "status": "PASS"
        })

        # Test Case 2: Optional argument provided (repo, sha, seen)
        seen_set = set()
        f_buf = io.StringIO()
        with redirect_stdout(f_buf):
            libwyag.log_graphviz(repo, head_sha, seen_set)
        out2 = f_buf.getvalue()
        assert len(seen_set) >= 2  # visited both commits
        results.append({
            "test": "optional_argument_seen_provided",
            "inputs": {"sha": head_sha, "seen_count": len(seen_set)},
            "actual_rc": 0,
            "status": "PASS"
        })

        # Test Case 3: Documented invalid combination (invalid sha raises Exception)
        invalid_raised = False
        try:
            libwyag.log_graphviz(repo, "0000000000000000000000000000000000000000")
        except Exception as e:
            invalid_raised = True
            invalid_err = str(e)
        assert invalid_raised, "Expected invalid sha to raise exception"
        results.append({
            "test": "invalid_combination_nonexistent_sha",
            "inputs": {"sha": "0000000000000000000000000000000000000000"},
            "exception_raised": True,
            "status": "PASS"
        })

        # Test Case 4: CLI invocation via wyag log
        rc_cli, out_cli, err_cli = run_cmd([wyag_bin, "log", "HEAD"], cwd=repo_dir)
        assert rc_cli == 0
        assert "digraph wyaglog" in out_cli
        results.append({
            "test": "cli_wyag_log_invocation",
            "actual_rc": rc_cli,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"test_commit_sha": head_sha, "tests_run": len(results)}, f, indent=2)

    print("All R21-T052 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
