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
        repo = libwyag.repo_find(repo_dir)

        # 1. Failing invocation: pass invalid object
        err_msg = ""
        failed = False
        try:
            libwyag.object_write(None, repo)
        except ValueError as e:
            failed = True
            err_msg = str(e)

        assert failed, "Expected object_write to raise ValueError on invalid input"
        assert "object_write failed" in err_msg
        results.append({
            "test": "failing_invocation_invalid_object",
            "exception_raised": True,
            "diagnostic_message": err_msg,
            "status": "PASS"
        })

        # 2. Corrected invocation succeeds
        blob = libwyag.GitBlob(b"alpha\n")
        sha = libwyag.object_write(blob, repo)
        assert len(sha) == 40

        # Verify object exists in repo
        obj_file = libwyag.repo_file(repo, "objects", sha[:2], sha[2:])
        assert os.path.exists(obj_file)

        results.append({
            "test": "corrected_invocation_success",
            "sha": sha,
            "object_created": True,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"tests_executed": len(results)}, f, indent=2)

    print("All R21-T027 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
