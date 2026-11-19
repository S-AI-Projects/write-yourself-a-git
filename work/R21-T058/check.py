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
        space_file = "my spaced notes.txt"
        with open(os.path.join(repo_dir, space_file), "w") as f:
            f.write("space content\n")

        # Staged change
        with open(os.path.join(repo_dir, "staged.txt"), "w") as f:
            f.write("staged content\n")

        run_cmd(["git", "add", "notes.txt", space_file, "staged.txt"], cwd=repo_dir)

        git_env = dict(os.environ,
                       GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                       GIT_AUTHOR_DATE="2020-01-01 00:00:00 +0000",
                       GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com",
                       GIT_COMMITTER_DATE="2020-01-01 00:00:00 +0000")
        rc, out, err = run_cmd(["git", "commit", "-m", "Initial commit", "--no-gpg-sign"], cwd=repo_dir, env=git_env)
        assert rc == 0

        # Unstaged change
        with open(os.path.join(repo_dir, "unstaged.txt"), "w") as f:
            f.write("unstaged content\n")

        # Test Case 1: List tags when no tags exist (should not crash with KeyError)
        rc_list1, out_list1, err_list1 = run_cmd([wyag_bin, "tag"], cwd=repo_dir)
        inputs_log.append({"test": "list_empty_tags", "rc": rc_list1, "out": out_list1, "err": err_list1})
        assert rc_list1 == 0, f"Expected rc 0 on empty tag list, got {rc_list1}: {err_list1}"
        assert out_list1.strip() == "", f"Expected empty output, got: {out_list1}"

        results.append({
            "test": "list_empty_tags",
            "expected_rc": 0,
            "actual_rc": rc_list1,
            "output": out_list1.strip(),
            "status": "PASS"
        })

        # Test Case 2: Create a lightweight tag
        rc_create1, out_create1, err_create1 = run_cmd([wyag_bin, "tag", "v1.0", "HEAD"], cwd=repo_dir)
        assert rc_create1 == 0
        tag_file = os.path.join(repo_dir, ".git", "refs", "tags", "v1.0")
        assert os.path.exists(tag_file), "Lightweight tag file not created"

        results.append({
            "test": "create_lightweight_tag",
            "expected_rc": 0,
            "actual_rc": rc_create1,
            "status": "PASS"
        })

        # Test Case 3: Create an annotated tag (-a flag)
        rc_create2, out_create2, err_create2 = run_cmd([wyag_bin, "tag", "-a", "v1.1", "HEAD"], cwd=repo_dir)
        assert rc_create2 == 0
        tag_file2 = os.path.join(repo_dir, ".git", "refs", "tags", "v1.1")
        assert os.path.exists(tag_file2), "Annotated tag file not created"

        results.append({
            "test": "create_annotated_tag",
            "expected_rc": 0,
            "actual_rc": rc_create2,
            "status": "PASS"
        })

        # Test Case 4: List tags now that tags exist
        rc_list2, out_list2, err_list2 = run_cmd([wyag_bin, "tag"], cwd=repo_dir)
        assert rc_list2 == 0
        tags_found = set(out_list2.strip().splitlines())
        assert "v1.0" in tags_found and "v1.1" in tags_found, f"Tags missing in list: {tags_found}"

        results.append({
            "test": "list_existing_tags",
            "expected_rc": 0,
            "actual_rc": rc_list2,
            "tags_found": sorted(list(tags_found)),
            "status": "PASS"
        })

        # Test Case 5: Failure on invalid reference target
        rc_invalid, out_invalid, err_invalid = run_cmd([wyag_bin, "tag", "badtag", "NONEXISTENT_COMMIT_REF"], cwd=repo_dir)
        assert rc_invalid != 0, "Expected failure on nonexistent commit ref"

        results.append({
            "test": "tag_nonexistent_ref_failure",
            "expected_nonzero": True,
            "actual_rc": rc_invalid,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"inputs_log": inputs_log, "tests_run": len(results)}, f, indent=2)

    print("All R21-T058 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
