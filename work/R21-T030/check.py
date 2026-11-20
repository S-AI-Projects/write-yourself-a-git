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
        # 1. Ordinary success contract with explicit directory
        repo_path = os.path.join(tmpdir, "contract_repo")
        rc, out, err = run_cmd([wyag_bin, "init", repo_path])
        assert rc == 0
        assert os.path.isdir(os.path.join(repo_path, ".git", "objects"))
        assert os.path.isdir(os.path.join(repo_path, ".git", "refs", "heads"))
        assert os.path.isfile(os.path.join(repo_path, ".git", "HEAD"))
        assert os.path.isfile(os.path.join(repo_path, ".git", "config"))

        results.append({
            "test": "ordinary_success_explicit_path",
            "exit_code": rc,
            "status": "PASS"
        })

        # 2. Supported default path contract (no arguments defaults to '.')
        default_dir = os.path.join(tmpdir, "default_repo")
        os.makedirs(default_dir)
        rc, out, err = run_cmd([wyag_bin, "init"], cwd=default_dir)
        assert rc == 0
        assert os.path.isdir(os.path.join(default_dir, ".git"))

        results.append({
            "test": "default_path_cwd",
            "exit_code": rc,
            "status": "PASS"
        })

        # 3. Missing / invalid state assertion (existing file cannot be init target)
        dummy_file = os.path.join(tmpdir, "dummy_file.txt")
        with open(dummy_file, "w") as f:
            f.write("text\n")
        rc_err, out_err, err_err = run_cmd([wyag_bin, "init", dummy_file])
        assert rc_err != 0
        results.append({
            "test": "invalid_state_rejection",
            "exit_code": rc_err,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"tests_executed": len(results)}, f, indent=2)

    print("All R21-T030 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
