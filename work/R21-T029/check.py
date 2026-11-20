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
        # 1. Normal success creation
        valid_path = os.path.join(tmpdir, "valid_repo")
        r = libwyag.repo_create(valid_path)
        assert os.path.isdir(os.path.join(valid_path, ".git"))
        results.append({
            "test": "valid_repo_creation",
            "path": valid_path,
            "status": "PASS"
        })

        # 2. Regression guard: existing regular file as target path must raise Exception
        file_path = os.path.join(tmpdir, "regular_file.txt")
        with open(file_path, "w") as f:
            f.write("hello\n")

        file_rejected = False
        try:
            libwyag.repo_create(file_path)
        except Exception as e:
            file_rejected = True
            err1 = str(e)
        assert file_rejected and "not a directory" in err1
        results.append({
            "test": "reject_file_target",
            "exception_raised": True,
            "status": "PASS"
        })

        # 3. Regression guard: existing non-empty .git directory must raise Exception
        dirty_repo = os.path.join(tmpdir, "dirty_repo")
        os.makedirs(os.path.join(dirty_repo, ".git", "objects"))
        with open(os.path.join(dirty_repo, ".git", "objects", "dummy"), "w") as f:
            f.write("dirty\n")

        dirty_rejected = False
        try:
            libwyag.repo_create(dirty_repo)
        except Exception as e:
            dirty_rejected = True
            err2 = str(e)
        assert dirty_rejected and "not empty" in err2
        results.append({
            "test": "reject_non_empty_gitdir",
            "exception_raised": True,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"tests_executed": len(results)}, f, indent=2)

    print("All R21-T029 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
