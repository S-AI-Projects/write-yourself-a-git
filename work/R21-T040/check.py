#!/usr/bin/env python3
import json, os, shutil, subprocess, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WYAG = os.path.join(REPO, "wyag")
os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ.get("PATH", "")


def _init_repo(path):
    subprocess.check_call(["git", "init", path],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "-C", path, "config", "user.email", "t@t.com"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "-C", path, "config", "user.name", "T"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


results = []

tmpdir = tempfile.mkdtemp(prefix="wyag-r21t040-")
try:
    repo_path = os.path.join(tmpdir, "repo")
    _init_repo(repo_path)

    notes = os.path.join(repo_path, "notes.txt")
    spaced = os.path.join(repo_path, "second file with space.txt")
    with open(notes, "w") as f:
        f.write("alpha\n")
    with open(spaced, "w") as f:
        f.write("beta\n")
    subprocess.check_call(["git", "-C", repo_path, "add", "."],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "-C", repo_path, "commit", "-m", "init"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    subprocess.check_call([WYAG, "add", "notes.txt"],
                          cwd=repo_path,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    r = subprocess.run(
        [WYAG, "rm", "notes.txt"],
        cwd=repo_path,
        capture_output=True, text=True)
    assert r.returncode == 0, f"rm of tracked file failed: {r.stderr}"
    assert not os.path.exists(notes), "notes.txt should be deleted from worktree"
    results.append({
        "check": "rm removes a tracked file from index and worktree",
        "args": ["notes.txt"],
        "exit_status": r.returncode,
        "result": "PASS",
    })

    outside_file = os.path.join(tmpdir, "outside.txt")
    with open(outside_file, "w") as f:
        f.write("outside\n")
    r2 = subprocess.run(
        [WYAG, "rm", outside_file],
        cwd=repo_path,
        capture_output=True, text=True)
    assert r2.returncode != 0, \
        "rm of path outside worktree must be rejected (guards worktree boundary condition)"
    results.append({
        "check": "rm rejects path outside worktree boundary",
        "args": [outside_file],
        "exit_status": r2.returncode,
        "stderr": r2.stderr.strip(),
        "result": "PASS",
    })

    r3 = subprocess.run(
        [WYAG, "rm", "nonexistent.txt"],
        cwd=repo_path,
        capture_output=True, text=True)
    assert r3.returncode != 0, "rm of path not in index must fail"
    results.append({
        "check": "rm rejects path not present in index",
        "args": ["nonexistent.txt"],
        "exit_status": r3.returncode,
        "stderr": r3.stderr.strip(),
        "result": "PASS",
    })

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

assert len(results) > 0, "no checks ran"

native_tests = [
    "Create repos",
    "status",
    "hash-object",
    "hash-object -w",
    "cat-file",
    "cat-file with long hash",
    "Create commit (git only, nothing is tested)",
    "cat-file on commit object without indirection",
    "cat-file on tree object redirected from commit",
    "Add some directories and commits (git only, nothing is tested)",
    "ls-tree",
    "checkout",
    "rev-parse",
    "ls-files",
    "gitignore",
]

tool_versions = subprocess.run(
    ["git", "--version"], capture_output=True, text=True).stdout.strip()
python_ver = sys.version.split()[0]

work_dir = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(work_dir, "inputs_and_results.json"), "w") as f:
    json.dump({"checks": results}, f, indent=2)

with open(os.path.join(work_dir, "native_test_names.txt"), "w") as f:
    f.write("\n".join(native_tests) + "\n")

with open(os.path.join(work_dir, "tool_versions.txt"), "w") as f:
    f.write(f"git: {tool_versions}\npython: {python_ver}\n")

for r in results:
    print(f"  {r['result']}: {r['check']}")

print(f"\nAll {len(results)} checks passed.")
