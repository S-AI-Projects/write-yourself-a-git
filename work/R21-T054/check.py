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

        # Second file whose name contains a space
        space_filename = "my spaced document.txt"
        with open(os.path.join(repo_dir, space_filename), "w") as f:
            f.write("spaced file content\n")

        # Third file with wildcard character in name
        wildcard_filename = "archive[v1]*.dat"
        with open(os.path.join(repo_dir, wildcard_filename), "w") as f:
            f.write("wildcard content\n")

        # Staged change
        staged_filename = "staged file.txt"
        with open(os.path.join(repo_dir, staged_filename), "w") as f:
            f.write("staged content\n")

        run_cmd(["git", "add", "notes.txt", space_filename, wildcard_filename, staged_filename], cwd=repo_dir)

        # Unstaged change
        with open(os.path.join(repo_dir, "unstaged.txt"), "w") as f:
            f.write("unstaged content\n")

        # Test index_read directly
        repo = libwyag.repo_find(repo_dir)
        index = libwyag.index_read(repo)
        entry_names = [e.name for e in index.entries]

        # Assert exact argument/path boundaries
        assert space_filename in entry_names, f"'{space_filename}' not found in index: {entry_names}"
        assert wildcard_filename in entry_names, f"'{wildcard_filename}' not found in index: {entry_names}"
        assert "notes.txt" in entry_names
        assert "staged file.txt" in entry_names
        assert "unstaged.txt" not in entry_names, "Unstaged file should not be in index"

        results.append({
            "test": "index_read_preserves_spaces_and_wildcards",
            "entry_names": entry_names,
            "space_file_present": True,
            "wildcard_file_present": True,
            "status": "PASS"
        })

        # Compare with git ls-files CLI output
        rc_git, out_git, _ = run_cmd(["git", "ls-files"], cwd=repo_dir)
        rc_wyag, out_wyag, _ = run_cmd([wyag_bin, "ls-files"], cwd=repo_dir)
        assert rc_wyag == 0
        git_files = sorted(out_git.strip().splitlines())
        wyag_files = sorted(out_wyag.strip().splitlines())
        assert git_files == wyag_files, f"Git ls-files ({git_files}) != Wyag ls-files ({wyag_files})"

        results.append({
            "test": "ls_files_comparison_with_git_cli",
            "git_files": git_files,
            "wyag_files": wyag_files,
            "status": "PASS"
        })

        # Test empty repository index handling
        empty_repo_dir = os.path.join(tmpdir, "empty_repo")
        run_cmd([wyag_bin, "init", empty_repo_dir])
        empty_repo = libwyag.repo_find(empty_repo_dir)
        empty_index = libwyag.index_read(empty_repo)
        assert len(empty_index.entries) == 0

        results.append({
            "test": "empty_index_read",
            "entry_count": len(empty_index.entries),
            "status": "PASS"
        })

    with open(os.path.join(work_dir, "expected_vs_actual.json"), "w") as f:
        json.dump(results, f, indent=2)

    with open(os.path.join(work_dir, "inputs.json"), "w") as f:
        json.dump({"filenames_tested": [space_filename, wildcard_filename], "tests_run": len(results)}, f, indent=2)

    print("All R21-T054 assertions PASSED successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
