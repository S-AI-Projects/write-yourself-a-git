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

        # notes.txt with "alpha\n"
        with open(os.path.join(repo_dir, "notes.txt"), "w") as f:
            f.write("alpha\n")

        # Second file with a space in its name
        space_file = "spaced file.txt"
        with open(os.path.join(repo_dir, space_file), "w") as f:
            f.write("spaced content\n")

        # Staged change
        with open(os.path.join(repo_dir, "staged.txt"), "w") as f:
            f.write("staged content\n")

        run_cmd(["git", "add", "notes.txt", space_file, "staged.txt"], cwd=repo_dir)

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

        # Baseline: normal object_find
        commit_sha = libwyag.object_find(repo, "HEAD", fmt=b"commit", follow=False)
        assert commit_sha is not None, "Failed to find commit object"

        tree_sha = libwyag.object_find(repo, "HEAD", fmt=b"tree", follow=True)
        assert tree_sha is not None, "Failed to resolve tree from commit"

        # Regression condition 1: follow=False with fmt mismatch must return None
        no_follow_result = libwyag.object_find(repo, "HEAD", fmt=b"tree", follow=False)
        assert no_follow_result is None, f"Expected None when follow=False on mismatched fmt, got {no_follow_result}"

        results.append({
            "test": "object_find_follow_false_returns_none",
            "commit_sha": commit_sha,
            "result": no_follow_result,
            "status": "PASS"
        })

        # Regression condition 2: follow=True follows commit to tree
        assert tree_sha != commit_sha, "Tree SHA should differ from commit SHA"
        results.append({
            "test": "object_find_follow_true_resolves_tree",
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
            "status": "PASS"
        })

        # Mutant test: simulate the condition mutant where follow flag is inverted
        def mutant_object_find(repo, name, fmt=None, follow=True):
            # Mutate: invert follow condition
            sha = libwyag.object_resolve(repo, name)
            if not sha:
                raise Exception(f"No such reference {name}.")
            sha = sha[0]
            if not fmt:
                return sha
            while True:
                obj = libwyag.object_read(repo, sha)
                if obj.fmt == fmt:
                    return sha
                # MUTANT: if follow (instead of if not follow)
                if follow:
                    return None
                if obj.fmt == b'tag':
                    sha = obj.kvlm[b'object'].decode("ascii")
                elif obj.fmt == b'commit' and fmt == b'tree':
                    sha = obj.kvlm[b'tree'].decode("ascii")
                else:
                    return None

        # Verify that our test input rejects the mutant
        mutant_result = mutant_object_find(repo, "HEAD", fmt=b"tree", follow=True)
        assert mutant_result is None, "Mutant unexpectedly succeeded"
        # The true implementation returned tree_sha, so the mutant is killed/rejected!
        assert mutant_result != tree_sha, "Mutant produced the correct output, mutant was not killed"

        results.append({
            "test": "mutant_rejected_by_test_input",
            "mutant_result": mutant_result,
            "expected_result": tree_sha,
            "mutant_killed": True,
            "status": "PASS"
        })

        # Test error branch: nonexistent ref
        nonexistent_raised = False
        try:
            libwyag.object_find(repo, "nonexistent_ref_xyz")
        except Exception:
            nonexistent_raised = True
        assert nonexistent_raised, "Expected exception on nonexistent reference"

        results.append({
            "test": "nonexistent_ref_error",
            "exception_raised": True,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"commit_sha": commit_sha, "tree_sha": tree_sha, "tests_run": len(results)}, f, indent=2)

    print("All R21-T059 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
