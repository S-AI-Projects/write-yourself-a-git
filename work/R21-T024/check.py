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
        # Standard fixture files
        notes_path = os.path.join(tmpdir, "notes.txt")
        with open(notes_path, "w") as f:
            f.write("alpha\n")

        # 1. Path containing spaces
        space_path = os.path.join(tmpdir, "my custom repo with spaces")
        rc, out, err = run_cmd([wyag_bin, "init", space_path])
        assert rc == 0, f"Init on path with spaces failed: {err}"
        assert os.path.isdir(os.path.join(space_path, ".git")), ".git directory not found in spaced path"
        results.append({
            "test": "init_path_with_spaces",
            "path": space_path,
            "status": "PASS"
        })

        # 2. Path containing wildcard and glob characters
        # Create unrelated files in tmpdir that could falsely match globbing
        with open(os.path.join(tmpdir, "wild_match1.txt"), "w") as f:
            f.write("unrelated 1\n")
        with open(os.path.join(tmpdir, "wild_match2.txt"), "w") as f:
            f.write("unrelated 2\n")

        wildcard_path = os.path.join(tmpdir, "repo_*_[wild]")
        rc, out, err = run_cmd([wyag_bin, "init", wildcard_path])
        assert rc == 0, f"Init on path with wildcards failed: {err}"
        assert os.path.isdir(os.path.join(wildcard_path, ".git")), ".git directory not found in wildcard path"
        assert os.path.isfile(os.path.join(tmpdir, "wild_match1.txt")), "Unrelated file modified by globbing"

        results.append({
            "test": "init_path_with_wildcards",
            "path": wildcard_path,
            "unrelated_files_intact": True,
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"tests_executed": len(results)}, f, indent=2)

    print("All R21-T024 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
