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

        # Setup: notes.txt with "alpha\n"
        with open(os.path.join(repo_dir, "notes.txt"), "w") as f:
            f.write("alpha\n")

        # Second file with space
        space_file = "file with space.txt"
        with open(os.path.join(repo_dir, space_file), "w") as f:
            f.write("space text\n")

        # Subdirectory file
        os.makedirs(os.path.join(repo_dir, "dir1", "dir2"), exist_ok=True)
        with open(os.path.join(repo_dir, "dir1", "dir2", "subfile.txt"), "w") as f:
            f.write("subfile content\n")

        # Staged change
        with open(os.path.join(repo_dir, "staged.txt"), "w") as f:
            f.write("staged content\n")

        run_cmd(["git", "add", "notes.txt", space_file, "dir1/dir2/subfile.txt", "staged.txt"], cwd=repo_dir)

        git_env = dict(os.environ,
                       GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                       GIT_AUTHOR_DATE="2020-01-01 00:00:00 +0000",
                       GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com",
                       GIT_COMMITTER_DATE="2020-01-01 00:00:00 +0000")
        rc, out, err = run_cmd(["git", "commit", "-m", "Commit 1", "--no-gpg-sign"], cwd=repo_dir, env=git_env)
        assert rc == 0

        # Unstaged change
        with open(os.path.join(repo_dir, "unstaged.txt"), "w") as f:
            f.write("unstaged content\n")

        repo = libwyag.repo_find(repo_dir)
        tree_sha = libwyag.object_find(repo, "HEAD", fmt=b"tree")
        tree_obj = libwyag.object_read(repo, tree_sha)

        # Characterization Test 1: checkout into empty directory
        target1 = os.path.join(tmpdir, "checkout_target1")
        os.makedirs(target1)
        libwyag.tree_checkout(repo, tree_obj, target1)

        assert os.path.exists(os.path.join(target1, "notes.txt"))
        assert open(os.path.join(target1, "notes.txt")).read() == "alpha\n"
        assert os.path.exists(os.path.join(target1, space_file))
        assert os.path.exists(os.path.join(target1, "dir1", "dir2", "subfile.txt"))
        assert not os.path.exists(os.path.join(target1, "unstaged.txt"))

        results.append({
            "test": "checkout_to_empty_directory",
            "target": target1,
            "status": "PASS"
        })

        # Characterization Test 2: checkout into directory where subdirectories already exist (idempotence)
        target2 = os.path.join(tmpdir, "checkout_target2")
        os.makedirs(os.path.join(target2, "dir1", "dir2"), exist_ok=True)
        libwyag.tree_checkout(repo, tree_obj, target2)
        assert os.path.exists(os.path.join(target2, "dir1", "dir2", "subfile.txt"))

        results.append({
            "test": "checkout_idempotent_existing_directories",
            "target": target2,
            "status": "PASS"
        })

        # CLI command wyag checkout
        target3 = os.path.join(tmpdir, "checkout_target3")
        rc_cli, out_cli, err_cli = run_cmd([wyag_bin, "checkout", "HEAD", target3], cwd=repo_dir)
        assert rc_cli == 0
        assert os.path.exists(os.path.join(target3, "notes.txt"))

        results.append({
            "test": "wyag_checkout_cli",
            "actual_rc": rc_cli,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"tree_sha": tree_sha, "tests_run": len(results)}, f, indent=2)

    print("All R21-T056 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
