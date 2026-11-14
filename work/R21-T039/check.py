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


def _make_commit(repo_path, files):
    for name, content in files.items():
        p = os.path.join(repo_path, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
        subprocess.check_call(["git", "-C", repo_path, "add", name],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["git", "-C", repo_path, "commit", "-m", "init"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.check_output(
        ["git", "-C", repo_path, "rev-parse", "HEAD"], text=True).strip()


results = []

tmpdir = tempfile.mkdtemp(prefix="wyag-r21t039-")
try:
    repo_path = os.path.join(tmpdir, "repo")
    _init_repo(repo_path)
    sha = _make_commit(repo_path, {
        "notes.txt": "alpha\n",
        "second file with space.txt": "beta\n",
    })

    out1 = os.path.join(tmpdir, "out1")
    os.makedirs(out1)
    r = subprocess.run([WYAG, "checkout", sha, out1],
                       cwd=repo_path, capture_output=True, text=True)
    assert r.returncode == 0, f"checkout into empty dir failed: {r.stderr}"
    assert os.path.isfile(os.path.join(out1, "notes.txt")), "notes.txt missing"
    assert os.path.isfile(os.path.join(out1, "second file with space.txt")), \
        "file with space missing"
    results.append({
        "check": "checkout into empty dir succeeds",
        "args": [sha, out1],
        "exit_status": r.returncode,
        "result": "PASS",
    })

    r2 = subprocess.run([WYAG, "checkout", sha, out1],
                        cwd=repo_path, capture_output=True, text=True)
    assert r2.returncode != 0, "checkout into non-empty dir should have failed"
    results.append({
        "check": "checkout into non-empty dir rejected",
        "args": [sha, out1],
        "exit_status": r2.returncode,
        "stderr": r2.stderr.strip(),
        "result": "PASS",
    })

    file_dest = os.path.join(tmpdir, "afile")
    with open(file_dest, "w") as f:
        f.write("x")
    r3 = subprocess.run([WYAG, "checkout", sha, file_dest],
                        cwd=repo_path, capture_output=True, text=True)
    assert r3.returncode != 0, "checkout onto file path should have failed"
    results.append({
        "check": "checkout onto file path rejected",
        "args": [sha, file_dest],
        "exit_status": r3.returncode,
        "stderr": r3.stderr.strip(),
        "result": "PASS",
    })

    new_dest = os.path.join(tmpdir, "newdir")
    r4 = subprocess.run([WYAG, "checkout", sha, new_dest],
                        cwd=repo_path, capture_output=True, text=True)
    assert r4.returncode == 0, f"checkout into auto-created dir failed: {r4.stderr}"
    assert os.path.isfile(os.path.join(new_dest, "notes.txt")), \
        "notes.txt missing in auto-created dest"
    results.append({
        "check": "checkout into nonexistent path auto-creates dir",
        "args": [sha, new_dest],
        "exit_status": r4.returncode,
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
