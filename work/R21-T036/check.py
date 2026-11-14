#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import libwyag


def get_tool_versions():
    git_ver = subprocess.check_output(["git", "--version"], text=True).strip()
    py_ver = sys.version.replace("\n", " ")
    wyag_path = os.path.join(REPO_ROOT, "wyag")
    return {
        "python": py_ver,
        "git": git_ver,
        "wyag_path": wyag_path
    }


def record_native_tests():
    return [
        "Create repos",
        "status",
        "hash-object",
        "hash-object -w",
        "cat-file",
        "cat-file with long hash",
        "Create commit",
        "cat-file on commit object without indirection",
        "cat-file on tree object redirected from commit",
        "Add some directories and commits",
        "ls-tree",
        "checkout",
        "rev-parse",
        "ls-files",
        "gitignore"
    ]


def setup_temp_repo(work_dir):
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    env["GIT_AUTHOR_NAME"] = "Pritpal Singh"
    env["GIT_AUTHOR_EMAIL"] = "pritpal@example.com"
    env["GIT_AUTHOR_DATE"] = "2026-11-14 00:00:00 +0530"
    env["GIT_COMMITTER_NAME"] = "Pritpal Singh"
    env["GIT_COMMITTER_EMAIL"] = "pritpal@example.com"
    env["GIT_COMMITTER_DATE"] = "2026-11-14 00:00:00 +0530"

    repo_path = os.path.join(work_dir, "test_repo")
    os.makedirs(repo_path, exist_ok=True)

    subprocess.run(["git", "init"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    notes_file = os.path.join(repo_path, "notes.txt")
    with open(notes_file, "w", encoding="utf-8") as f:
        f.write("alpha\n")

    space_file = os.path.join(repo_path, "second file with space.txt")
    with open(space_file, "w", encoding="utf-8") as f:
        f.write("second file content\n")

    sub_dir = os.path.join(repo_path, "subdir")
    os.makedirs(sub_dir, exist_ok=True)
    with open(os.path.join(sub_dir, "nested.txt"), "w", encoding="utf-8") as f:
        f.write("nested content\n")

    subprocess.run(["git", "add", "notes.txt", "second file with space.txt", "subdir/nested.txt"], cwd=repo_path, check=True, env=env)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    with open(space_file, "w", encoding="utf-8") as f:
        f.write("second file staged content\n")
    subprocess.run(["git", "add", "second file with space.txt"], cwd=repo_path, check=True, env=env)

    with open(notes_file, "w", encoding="utf-8") as f:
        f.write("alpha unstaged modified\n")

    return repo_path, env


def run_checks():
    work_dir = tempfile.mkdtemp(prefix="wyag_tree_to_dict_test_")
    results = []
    cases_executed = 0

    try:
        repo_path, env = setup_temp_repo(work_dir)
        repo = libwyag.GitRepository(repo_path)

        res_dict = libwyag.tree_to_dict(repo, "HEAD")
        cases_executed += 1

        git_ls = subprocess.check_output(["git", "ls-tree", "-r", "HEAD"], cwd=repo_path, text=True, env=env).strip()
        expected_dict = {}
        for line in git_ls.splitlines():
            parts = line.split()
            sha = parts[2]
            path = line.split("\t", 1)[1]
            expected_dict[path] = sha

        assert res_dict == expected_dict, f"Dict mismatch: {res_dict} != {expected_dict}"
        assert "notes.txt" in res_dict
        assert "second file with space.txt" in res_dict
        assert "subdir/nested.txt" in res_dict

        results.append({
            "case": "1: tree_to_dict_recursive_characterization",
            "arguments": {"ref": "HEAD", "prefix": ""},
            "exit_status": 0,
            "paths_matched": sorted(list(res_dict.keys())),
            "passed": True
        })

        sub_sha = subprocess.check_output(["git", "rev-parse", "HEAD:subdir"], cwd=repo_path, text=True, env=env).strip()
        sub_dict = libwyag.tree_to_dict(repo, sub_sha, prefix="custom_prefix")
        cases_executed += 1
        assert "custom_prefix/nested.txt" in sub_dict
        assert sub_dict["custom_prefix/nested.txt"] == expected_dict["subdir/nested.txt"]

        results.append({
            "case": "2: tree_to_dict_prefix_and_subtree",
            "arguments": {"ref": sub_sha, "prefix": "custom_prefix"},
            "exit_status": 0,
            "paths_matched": list(sub_dict.keys()),
            "passed": True
        })

        index = libwyag.index_read(repo)
        libwyag.cmd_status_head_index(repo, index)
        cases_executed += 1

        results.append({
            "case": "3: tree_to_dict_status_integration",
            "arguments": {"command": "cmd_status_head_index"},
            "exit_status": 0,
            "passed": True
        })

        nonexistent_err = None
        try:
            libwyag.tree_to_dict(repo, "missing_ref_abc123")
        except Exception as e:
            nonexistent_err = str(e)
        cases_executed += 1
        assert nonexistent_err is not None and "No such reference" in nonexistent_err

        results.append({
            "case": "4: tree_to_dict_nonexistent_ref_failure",
            "arguments": {"ref": "missing_ref_abc123"},
            "exit_status": 1,
            "expected_error": "No such reference missing_ref_abc123.",
            "actual_error": nonexistent_err,
            "passed": True
        })

        notes_blob_sha = expected_dict["notes.txt"]
        blob_err = None
        try:
            libwyag.tree_to_dict(repo, notes_blob_sha)
        except Exception as e:
            blob_err = str(e)
        cases_executed += 1
        assert blob_err is not None

        results.append({
            "case": "5: tree_to_dict_non_tree_object_failure",
            "arguments": {"ref": notes_blob_sha},
            "exit_status": 1,
            "actual_error": blob_err,
            "passed": True
        })

        if cases_executed == 0:
            raise RuntimeError("Zero-case run rejected: No test cases were executed!")

        print(f"Total test cases executed: {cases_executed}")
        for res in results:
            print(f"  [PASS] {res['case']}: exit_status={res['exit_status']}")

        out_dir = os.path.join(REPO_ROOT, "work", "R21-T036")
        os.makedirs(out_dir, exist_ok=True)

        tool_versions = get_tool_versions()
        with open(os.path.join(out_dir, "tool_versions.txt"), "w", encoding="utf-8") as f:
            for k, v in tool_versions.items():
                f.write(f"{k}: {v}\n")

        native_tests = record_native_tests()
        with open(os.path.join(out_dir, "native_test_names.txt"), "w", encoding="utf-8") as f:
            for t in native_tests:
                f.write(f"{t}\n")

        with open(os.path.join(out_dir, "inputs_and_results.json"), "w", encoding="utf-8") as f:
            json.dump({
                "cases_executed": cases_executed,
                "tool_versions": tool_versions,
                "native_test_names": native_tests,
                "results": results
            }, f, indent=2)

        print("\nAll checks completed successfully and artifacts saved to work/R21-T036/")
        return 0

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run_checks())
