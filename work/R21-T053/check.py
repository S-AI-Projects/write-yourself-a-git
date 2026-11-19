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

        # file with space
        with open(os.path.join(repo_dir, "file with space.txt"), "w") as f:
            f.write("space content\n")

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
        assert rc == 0

        # Unstaged change
        with open(os.path.join(repo_dir, "unstaged.txt"), "w") as f:
            f.write("unstaged content\n")

        repo = libwyag.repo_find(repo_dir)
        commit_sha = libwyag.object_find(repo, "HEAD")

        # Record state before
        ref_heads_dir = os.path.join(repo_dir, ".git", "refs", "heads")
        refs_before = set(os.listdir(ref_heads_dir)) if os.path.exists(ref_heads_dir) else set()
        notes_content_before = open(os.path.join(repo_dir, "notes.txt")).read()
        unstaged_content_before = open(os.path.join(repo_dir, "unstaged.txt")).read()

        # Step: ref_create state transition
        tag_ref_name = "tags/release-v1"
        libwyag.ref_create(repo, tag_ref_name, commit_sha)

        # Record state after
        created_ref_path = os.path.join(repo_dir, ".git", "refs", tag_ref_name)
        assert os.path.exists(created_ref_path), f"Ref file {created_ref_path} not found"
        with open(created_ref_path) as f:
            ref_content = f.read()

        assert ref_content == commit_sha + "\n", f"Expected '{commit_sha}\\n', got '{ref_content}'"

        # Assert unrelated state is unchanged
        refs_after = set(os.listdir(ref_heads_dir)) if os.path.exists(ref_heads_dir) else set()
        assert refs_before == refs_after, "Heads refs changed unexpectedly"
        assert open(os.path.join(repo_dir, "notes.txt")).read() == notes_content_before, "notes.txt changed"
        assert open(os.path.join(repo_dir, "unstaged.txt")).read() == unstaged_content_before, "unstaged.txt changed"

        results.append({
            "test": "ref_create_state_transition",
            "ref_name": tag_ref_name,
            "created_path": created_ref_path,
            "written_content": ref_content.strip(),
            "unrelated_state_preserved": True,
            "status": "PASS"
        })

        # Edge state: nested ref creation (e.g., tags/nested/subtag)
        nested_tag = "tags/sub/nested-tag"
        libwyag.ref_create(repo, nested_tag, commit_sha)
        nested_ref_path = os.path.join(repo_dir, ".git", "refs", nested_tag)
        assert os.path.exists(nested_ref_path), "Nested ref was not created"
        with open(nested_ref_path) as f:
            assert f.read() == commit_sha + "\n"

        results.append({
            "test": "ref_create_nested_hierarchy",
            "ref_name": nested_tag,
            "status": "PASS"
        })

        # CLI command wyag tag
        rc_cli, out_cli, err_cli = run_cmd([wyag_bin, "tag", "v2.0", "HEAD"], cwd=repo_dir)
        assert rc_cli == 0
        assert os.path.exists(os.path.join(repo_dir, ".git", "refs", "tags", "v2.0"))

        results.append({
            "test": "wyag_tag_cli_execution",
            "actual_rc": rc_cli,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"ref_name": tag_ref_name, "commit_sha": commit_sha, "tests_run": len(results)}, f, indent=2)

    print("All R21-T053 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
