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

        # Setup: notes.txt with "alpha\n"
        with open(os.path.join(repo_dir, "notes.txt"), "w") as f:
            f.write("alpha\n")

        # Second file with a space in its name
        space_file = "sample file with space.txt"
        with open(os.path.join(repo_dir, space_file), "w") as f:
            f.write("data in spaced file\n")

        # Staged change
        staged_file = "staged.txt"
        with open(os.path.join(repo_dir, staged_file), "w") as f:
            f.write("staged content\n")

        run_cmd(["git", "add", "notes.txt", space_file, staged_file], cwd=repo_dir)

        # Unstaged change
        with open(os.path.join(repo_dir, "unstaged.txt"), "w") as f:
            f.write("unstaged content\n")

        # Failure test: invocation on nonexistent file
        missing_file = "nonexistent_file_fixture.txt"
        cmd_fail = [wyag_bin, "hash-object", missing_file]
        rc_fail, out_fail, err_fail = run_cmd(cmd_fail, cwd=repo_dir)

        inputs_log.append({"step": "failure_invocation", "cmd": cmd_fail, "rc": rc_fail, "stderr": err_fail})
        assert rc_fail == 128, f"Expected exit status 128 on missing file, got {rc_fail}"
        assert "fatal: Cannot open" in err_fail, f"Expected diagnostic message in stderr, got: {err_fail}"

        results.append({
            "test": "missing_file_failure_diagnostic",
            "cmd": cmd_fail,
            "expected_rc": 128,
            "actual_rc": rc_fail,
            "stderr": err_fail.strip(),
            "status": "PASS"
        })

        # Corrected invocation: creating the file and re-running
        with open(os.path.join(repo_dir, missing_file), "w") as f:
            f.write("recovered content\n")

        cmd_success = [wyag_bin, "hash-object", missing_file]
        rc_success, out_success, err_success = run_cmd(cmd_success, cwd=repo_dir)

        assert rc_success == 0, f"Expected success (rc 0), got {rc_success}: {err_success}"
        assert len(out_success.strip()) == 40, f"Expected 40-char SHA, got: {out_success}"

        # Cross-check with git hash-object
        rc_git, out_git, _ = run_cmd(["git", "hash-object", missing_file], cwd=repo_dir)
        assert rc_git == 0
        assert out_success.strip() == out_git.strip(), f"wyag SHA {out_success.strip()} != git SHA {out_git.strip()}"

        results.append({
            "test": "corrected_invocation_success",
            "cmd": cmd_success,
            "expected_rc": 0,
            "actual_rc": rc_success,
            "sha": out_success.strip(),
            "matches_git": True,
            "status": "PASS"
        })

        # Test hash-object on file with space
        cmd_space = [wyag_bin, "hash-object", space_file]
        rc_sp, out_sp, _ = run_cmd(cmd_space, cwd=repo_dir)
        rc_sp_git, out_sp_git, _ = run_cmd(["git", "hash-object", space_file], cwd=repo_dir)
        assert rc_sp == 0
        assert out_sp.strip() == out_sp_git.strip()

        results.append({
            "test": "file_with_space_hash_object",
            "cmd": cmd_space,
            "actual_rc": rc_sp,
            "sha": out_sp.strip(),
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"inputs_log": inputs_log, "tests_run": len(results)}, f, indent=2)

    print("All R21-T057 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
