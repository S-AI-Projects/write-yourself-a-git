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
        assert rc == 0

        with open(os.path.join(repo_dir, "notes.txt"), "w") as f:
            f.write("alpha\n")
        with open(os.path.join(repo_dir, "spaced file.txt"), "w") as f:
            f.write("spaced\n")
        with open(os.path.join(repo_dir, "staged.txt"), "w") as f:
            f.write("staged\n")

        run_cmd(["git", "add", "notes.txt", "staged.txt"], cwd=repo_dir)
        git_env = dict(os.environ,
                       GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                       GIT_AUTHOR_DATE="2020-01-01 00:00:00 +0000",
                       GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com",
                       GIT_COMMITTER_DATE="2020-01-01 00:00:00 +0000")
        rc, out, err = run_cmd(["git", "commit", "-m", "Commit 1", "--no-gpg-sign"], cwd=repo_dir, env=git_env)
        assert rc == 0

        # 1. Focused check: wyag rev-parse HEAD matches git rev-parse HEAD
        rc_wyag, wyag_head, _ = run_cmd([wyag_bin, "rev-parse", "HEAD"], cwd=repo_dir)
        rc_git, git_head, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        assert rc_wyag == 0
        assert wyag_head.strip() == git_head.strip()

        results.append({
            "test": "rev_parse_head_match",
            "wyag_sha": wyag_head.strip(),
            "git_sha": git_head.strip(),
            "status": "PASS"
        })

        # 2. Focused check: typed resolution
        rc_tree, wyag_tree, _ = run_cmd([wyag_bin, "rev-parse", "--wyag-type", "tree", "HEAD"], cwd=repo_dir)
        rc_git_tree, git_tree, _ = run_cmd(["git", "rev-parse", "HEAD^{tree}"], cwd=repo_dir)
        assert rc_tree == 0
        assert wyag_tree.strip() == git_tree.strip()

        results.append({
            "test": "rev_parse_tree_match",
            "wyag_sha": wyag_tree.strip(),
            "git_sha": git_tree.strip(),
            "status": "PASS"
        })

        # 3. Failure propagation: invalid rev
        rc_fail, _, err_fail = run_cmd([wyag_bin, "rev-parse", "nonexistent-ref"], cwd=repo_dir)
        assert rc_fail != 0
        results.append({
            "test": "rev_parse_invalid_ref_error",
            "exit_code": rc_fail,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"tests_executed": len(results)}, f, indent=2)

    print("All R21-T028 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
