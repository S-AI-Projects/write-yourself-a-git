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

        # Second file with a space in its name
        space_file = "my test file.txt"
        with open(os.path.join(repo_dir, space_file), "w") as f:
            f.write("space content\n")

        # Nested directory with file
        os.makedirs(os.path.join(repo_dir, "subdir", "nested"), exist_ok=True)
        with open(os.path.join(repo_dir, "subdir", "nested", "leaf.txt"), "w") as f:
            f.write("leaf content\n")

        # Staged change
        staged_file = "staged.txt"
        with open(os.path.join(repo_dir, staged_file), "w") as f:
            f.write("staged\n")

        run_cmd(["git", "add", "notes.txt", space_file, "subdir/nested/leaf.txt", staged_file], cwd=repo_dir)

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

        # Command & State Verification:
        repo = libwyag.repo_find(repo_dir)
        tree_dict = libwyag.tree_to_dict(repo, "HEAD")

        # Assert output matches expected tree dictionary
        assert "notes.txt" in tree_dict, "notes.txt missing from tree_to_dict"
        assert space_file in tree_dict, f"'{space_file}' missing from tree_to_dict"
        assert os.path.join("subdir", "nested", "leaf.txt") in tree_dict, "nested path missing from tree_to_dict"
        assert "unstaged.txt" not in tree_dict, "unstaged file should not be in tree_to_dict"

        # Verify blob SHAs match git rev-parse
        for path, sha in tree_dict.items():
            rc, expected_sha, _ = run_cmd(["git", "rev-parse", f"HEAD:{path}"], cwd=repo_dir)
            assert rc == 0
            assert sha == expected_sha.strip(), f"SHA mismatch for {path}: expected {expected_sha.strip()}, got {sha}"

        results.append({
            "test": "complete_usage_example_tree_to_dict",
            "paths_in_tree": list(tree_dict.keys()),
            "status": "PASS"
        })

        # Test failure/edge case: invalid ref
        raised = False
        try:
            libwyag.tree_to_dict(repo, "NONEXISTENT_REF_12345")
        except Exception:
            raised = True
        assert raised, "Expected exception on nonexistent ref"

        results.append({
            "test": "nonexistent_ref_error",
            "exception_raised": True,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"files_tested": ["notes.txt", space_file, "subdir/nested/leaf.txt"], "tests_run": len(results)}, f, indent=2)

    print("All R21-T055 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
