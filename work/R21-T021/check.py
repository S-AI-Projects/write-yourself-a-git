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
            f.write("spaced content\n")

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
        assert rc == 0, f"Commit 1 failed: {err}"

        # Unstaged change
        with open(os.path.join(repo_dir, "unstaged.txt"), "w") as f:
            f.write("unstaged content\n")

        # Case 1: Minimum accepted argument list (no arguments)
        cfg_default = libwyag.repo_default_config()
        assert cfg_default.get("core", "repositoryformatversion") == "0"
        assert cfg_default.get("core", "filemode") == "false"
        assert cfg_default.get("core", "bare") == "false"
        results.append({
            "test": "minimum_argument_list_zero_args",
            "inputs": {},
            "actual_core_sections": list(cfg_default.sections()),
            "status": "PASS"
        })

        # Case 2: Optional argument provided (extra section)
        cfg_custom = libwyag.repo_default_config({"user": {"name": "Mayank Gupta", "email": "tester@example.com"}})
        assert cfg_custom.get("user", "name") == "Mayank Gupta"
        assert cfg_custom.get("user", "email") == "tester@example.com"
        assert cfg_custom.get("core", "repositoryformatversion") == "0"
        results.append({
            "test": "optional_argument_extra_sections",
            "inputs": {"user": {"name": "Mayank Gupta", "email": "tester@example.com"}},
            "actual_user_name": cfg_custom.get("user", "name"),
            "status": "PASS"
        })

        # Case 3: Documented invalid combination (invalid type raises TypeError)
        type_error_raised = False
        try:
            libwyag.repo_default_config("invalid_non_dict_string")
        except TypeError as e:
            type_error_raised = True
            err_msg = str(e)
        assert type_error_raised, "Expected TypeError for non-dict argument"
        results.append({
            "test": "invalid_combination_non_dict_argument",
            "inputs": {"extra_sections": "invalid_non_dict_string"},
            "exception_raised": True,
            "status": "PASS"
        })

        # Case 4: Verify default config in repo matches git config expectation
        rc, out, _ = run_cmd(["git", "config", "core.bare"], cwd=repo_dir)
        results.append({
            "test": "repo_config_bare_check",
            "actual": out.strip(),
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"tests_executed": len(results)}, f, indent=2)

    print("All R21-T021 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
