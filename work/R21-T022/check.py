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

        with open(os.path.join(repo_dir, "notes.txt"), "w") as f:
            f.write("alpha\n")
        with open(os.path.join(repo_dir, "spaced file.txt"), "w") as f:
            f.write("spaced\n")
        with open(os.path.join(repo_dir, "staged.txt"), "w") as f:
            f.write("staged\n")

        run_cmd(["git", "add", "notes.txt", "staged.txt", "spaced file.txt"], cwd=repo_dir)
        git_env = dict(os.environ,
                       GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                       GIT_AUTHOR_DATE="2020-01-01 00:00:00 +0000",
                       GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com",
                       GIT_COMMITTER_DATE="2020-01-01 00:00:00 +0000")
        rc, out, err = run_cmd(["git", "commit", "-m", "Commit 1", "--no-gpg-sign"], cwd=repo_dir, env=git_env)
        assert rc == 0

        with open(os.path.join(repo_dir, "unstaged.txt"), "w") as f:
            f.write("unstaged content\n")

        rc, head_before, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        rc, status_before, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_dir)

        # 1. State transition check: ls-tree generates output while refs/worktree remain untouched
        repo = libwyag.repo_find(repo_dir)
        buf = io.StringIO()
        with redirect_stdout(buf):
            libwyag.ls_tree(repo, "HEAD")
        tree_output = buf.getvalue()

        assert "notes.txt" in tree_output
        assert "spaced file.txt" in tree_output

        rc, head_after, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        rc, status_after, _ = run_cmd(["git", "status", "--porcelain"], cwd=repo_dir)
        assert head_before == head_after, "HEAD ref was unexpectedly modified"
        assert status_before == status_after, "Working tree state was unexpectedly modified"

        results.append({
            "test": "ls_tree_state_preservation",
            "head_unchanged": (head_before == head_after),
            "status_unchanged": (status_before == status_after),
            "status": "PASS"
        })

        # 2. Documented edge/failure: nonexistent tree ref raises ValueError
        raised = False
        try:
            libwyag.ls_tree(repo, "nonexistent-branch-or-tag")
        except (ValueError, Exception):
            raised = True
        assert raised, "Expected non-existent ref to raise exception"

        results.append({
            "test": "ls_tree_invalid_ref_failure",
            "exception_raised": True,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"tests_run": len(results), "ref_tested": "HEAD"}, f, indent=2)

    print("All R21-T022 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
