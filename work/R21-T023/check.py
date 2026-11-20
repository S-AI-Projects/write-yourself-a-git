#!/usr/bin/env python3
import os
import sys
import subprocess
import tempfile
import json

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

        # Test Case 1: Missing index dependency branch in freshly initialized repository
        repo = libwyag.repo_find(repo_dir)
        index_missing = libwyag.index_read(repo)
        assert isinstance(index_missing, libwyag.GitIndex)
        assert len(index_missing.entries) == 0
        results.append({
            "test": "missing_index_branch",
            "entries_count": 0,
            "status": "PASS"
        })

        # Add files and commit to create .git/index
        with open(os.path.join(repo_dir, "notes.txt"), "w") as f:
            f.write("alpha\n")
        with open(os.path.join(repo_dir, "spaced file.txt"), "w") as f:
            f.write("spaced data\n")
        with open(os.path.join(repo_dir, "staged.txt"), "w") as f:
            f.write("staged data\n")

        run_cmd(["git", "add", "notes.txt", "staged.txt"], cwd=repo_dir)
        git_env = dict(os.environ,
                       GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                       GIT_AUTHOR_DATE="2020-01-01 00:00:00 +0000",
                       GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com",
                       GIT_COMMITTER_DATE="2020-01-01 00:00:00 +0000")
        run_cmd(["git", "commit", "-m", "Commit 1", "--no-gpg-sign"], cwd=repo_dir, env=git_env)

        with open(os.path.join(repo_dir, "unstaged.txt"), "w") as f:
            f.write("unstaged data\n")

        # Test Case 2: Success branch with existing index file
        index_existing = libwyag.index_read(repo)
        paths = [e.name for e in index_existing.entries]
        assert "notes.txt" in paths
        assert "staged.txt" in paths
        results.append({
            "test": "existing_index_success_branch",
            "entries_found": paths,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"tests_executed": len(results)}, f, indent=2)

    print("All R21-T023 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
