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

        # Subdirectory structure
        sub_dir = os.path.join(repo_dir, "dir_a", "dir_b", "dir_c")
        os.makedirs(sub_dir)

        # 1. Characterization test: find from repo root
        r1 = libwyag.repo_find(repo_dir)
        assert r1.worktree == os.path.realpath(repo_dir)
        results.append({
            "test": "find_from_root",
            "worktree": r1.worktree,
            "status": "PASS"
        })

        # 2. Characterization test: find from deep nested subdirectory
        r2 = libwyag.repo_find(sub_dir)
        assert r2.worktree == os.path.realpath(repo_dir)
        results.append({
            "test": "find_from_nested_subdir",
            "worktree": r2.worktree,
            "status": "PASS"
        })

        # 3. Base case: outside repository with required=False returns None
        non_repo = os.path.join(tmpdir, "outside")
        os.makedirs(non_repo)
        r3 = libwyag.repo_find(non_repo, required=False)
        assert r3 is None
        results.append({
            "test": "find_outside_optional_returns_none",
            "result": None,
            "status": "PASS"
        })

        # 4. Base case: outside repository with required=True raises Exception
        exc_raised = False
        try:
            libwyag.repo_find(non_repo, required=True)
        except Exception as e:
            exc_raised = True
            err_msg = str(e)
        assert exc_raised and "No git directory" in err_msg
        results.append({
            "test": "find_outside_required_raises_exception",
            "exception_raised": True,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"tests_executed": len(results)}, f, indent=2)

    print("All R21-T025 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
