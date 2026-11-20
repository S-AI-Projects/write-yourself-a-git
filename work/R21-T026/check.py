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

        # Create files and stage
        with open(os.path.join(repo_dir, "notes.txt"), "w") as f:
            f.write("alpha\n")
        with open(os.path.join(repo_dir, "spaced file.txt"), "w") as f:
            f.write("spaced\n")
        with open(os.path.join(repo_dir, "staged.txt"), "w") as f:
            f.write("staged\n")

        run_cmd(["git", "add", "notes.txt", "staged.txt"], cwd=repo_dir)

        repo = libwyag.repo_find(repo_dir)

        # Execute documented usage example
        index_before = libwyag.index_read(repo)
        libwyag.index_write(repo, index_before)

        # State verification: verify written binary index file
        index_path = os.path.join(repo_dir, ".git", "index")
        assert os.path.exists(index_path), "index file was not written"
        with open(index_path, "rb") as f:
            data = f.read()
        assert data[:4] == b"DIRC", "Invalid index signature"
        version = int.from_bytes(data[4:8], "big")
        assert version == 2, f"Unexpected index version: {version}"

        index_after = libwyag.index_read(repo)
        assert len(index_after.entries) == len(index_before.entries)
        for e1, e2 in zip(index_before.entries, index_after.entries):
            assert e1.name == e2.name
            assert e1.sha == e2.sha

        results.append({
            "test": "documented_usage_example_execution",
            "index_signature": "DIRC",
            "index_version": version,
            "entries_verified": len(index_after.entries),
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)
    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"tests_executed": len(results)}, f, indent=2)

    print("All R21-T026 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
