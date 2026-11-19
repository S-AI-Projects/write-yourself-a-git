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

        # Setup local config for determinism
        local_cfg = os.path.join(repo_dir, ".git", "config")
        with open(local_cfg, "a") as f:
            f.write("\n[user]\n\tname = Deterministic Tester\n\temail = tester@example.com\n")

        # notes.txt with "alpha\n"
        with open(os.path.join(repo_dir, "notes.txt"), "w") as f:
            f.write("alpha\n")

        # Second file with a space in its name
        space_file = "my spaced document.txt"
        with open(os.path.join(repo_dir, space_file), "w") as f:
            f.write("spaced content\n")

        # Staged change
        with open(os.path.join(repo_dir, "staged.txt"), "w") as f:
            f.write("staged content\n")

        run_cmd(["git", "add", "notes.txt", space_file, "staged.txt"], cwd=repo_dir)

        git_env = dict(os.environ,
                       GIT_AUTHOR_NAME="Deterministic Tester", GIT_AUTHOR_EMAIL="tester@example.com",
                       GIT_AUTHOR_DATE="2020-01-01 00:00:00 +0000",
                       GIT_COMMITTER_NAME="Deterministic Tester", GIT_COMMITTER_EMAIL="tester@example.com",
                       GIT_COMMITTER_DATE="2020-01-01 00:00:00 +0000")
        rc, out, err = run_cmd(["git", "commit", "-m", "Commit 1", "--no-gpg-sign"], cwd=repo_dir, env=git_env)
        assert rc == 0

        # Unstaged change
        with open(os.path.join(repo_dir, "unstaged.txt"), "w") as f:
            f.write("unstaged content\n")

        repo = libwyag.repo_find(repo_dir)

        # Success Case 1: Resolve HEAD (indirect ref pointing to refs/heads/master)
        head_resolved = libwyag.ref_resolve(repo, "HEAD")
        rc_git, git_rev, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        assert head_resolved == git_rev.strip(), f"HEAD mismatch: {head_resolved} vs {git_rev.strip()}"

        results.append({
            "test": "ref_resolve_head_indirect_success",
            "ref": "HEAD",
            "resolved_sha": head_resolved,
            "expected_sha": git_rev.strip(),
            "status": "PASS"
        })

        # Success Case 2: Resolve direct ref (e.g. tag)
        libwyag.ref_create(repo, "tags/direct-tag", head_resolved)
        direct_resolved = libwyag.ref_resolve(repo, "refs/tags/direct-tag")
        assert direct_resolved == head_resolved, f"Direct tag mismatch: {direct_resolved} vs {head_resolved}"

        results.append({
            "test": "ref_resolve_direct_tag_success",
            "ref": "refs/tags/direct-tag",
            "resolved_sha": direct_resolved,
            "status": "PASS"
        })

        # Missing-dependency Branch: Non-existent reference file must return None
        missing_ref_result = libwyag.ref_resolve(repo, "refs/heads/nonexistent-branch")
        assert missing_ref_result is None, f"Expected None on missing ref, got: {missing_ref_result}"

        results.append({
            "test": "ref_resolve_missing_dependency_branch",
            "ref": "refs/heads/nonexistent-branch",
            "expected": None,
            "actual": missing_ref_result,
            "status": "PASS"
        })

        # Broken indirect ref pointing to missing file
        broken_indirect_path = os.path.join(repo_dir, ".git", "refs", "broken_indirect")
        with open(broken_indirect_path, "w") as f:
            f.write("ref: refs/heads/does-not-exist\n")

        broken_resolved = libwyag.ref_resolve(repo, "refs/broken_indirect")
        assert broken_resolved is None, f"Expected None for broken indirect ref, got {broken_resolved}"

        results.append({
            "test": "ref_resolve_broken_indirect_pointer",
            "ref": "refs/broken_indirect",
            "expected": None,
            "actual": broken_resolved,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"resolved_head": head_resolved, "tests_run": len(results)}, f, indent=2)

    print("All R21-T060 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
