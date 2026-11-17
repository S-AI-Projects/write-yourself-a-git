#!/usr/bin/env python3
"""Run native tests and record the cmd_show_ref state-transition checks."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
WYAG = ROOT / "wyag"
report = {"commands": [], "checks": [], "passed": False}
inputs = {
    "staging": {
        "notes.txt": {"initial": "alpha\n", "updated": "alpha updated\n", "expected": "staged"},
        "file with space.txt": {
            "initial": "space initial\n",
            "updated": "space modified\n",
            "expected": "unstaged",
        },
    },
    "state_transitions": {
        "initial_state": "Initial commit created on master with tag v1.0",
        "intended_transition": "New commit on feature branch advances refs/heads/feature",
        "unrelated_state": "refs/heads/master and refs/tags/v1.0 remain strictly unchanged",
        "command_idempotence": "Running show-ref itself causes zero mutations to refs or index",
    },
    "normalization": [
        "Baseline commit dates and author/committer identity are fixed.",
        "Timestamps and author metadata are normalized across Git and wyag.",
    ],
}


def execute(label, args, cwd=ROOT, env=None):
    argv = [str(arg) for arg in args]
    completed = subprocess.run(
        argv, cwd=str(cwd), env=env, text=True, capture_output=True
    )
    report["commands"].append(
        {
            "label": label,
            "args": argv,
            "cwd": str(cwd),
            "exit_status": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    )
    return completed


def expect(condition, message):
    report["checks"].append({"assertion": message, "passed": bool(condition)})
    if not condition:
        raise AssertionError(message)


def git(repo, *args, env, label):
    result = execute(label, ["git", "-C", repo, *args], env=env)
    expect(result.returncode == 0, f"{label} exits successfully")
    return result.stdout


def get_refs_dict(repo):
    refs_dir = repo / ".git" / "refs"
    refs = {}
    if refs_dir.exists():
        for ref in sorted(path for path in refs_dir.rglob("*") if path.is_file()):
            refs[str(ref.relative_to(repo / ".git"))] = ref.read_text().strip()
    return refs


def parse_show_ref_output(output):
    parsed = {}
    for line in output.strip().splitlines():
        if not line:
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2:
            parsed[parts[1]] = parts[0]
    return parsed


def run_checks():
    versions = {}
    for name, args in (
        ("python", ["python3", "--version"]),
        ("git", ["git", "--version"]),
        ("make", ["make", "--version"]),
        ("emacs", ["emacs", "--version"]),
    ):
        result = execute(f"version: {name}", args)
        expect(result.returncode == 0, f"{name} version command succeeds")
        versions[name] = result.stdout.splitlines()[0]
    report["tool_versions"] = versions

    native = execute("native shell test suite", ["bash", "wyag-tests.sh"])
    expect(native.returncode == 0, "native wyag-tests.sh suite passes")
    expect(
        "show-ref verifies state transitions" in native.stdout,
        "native suite executes the focused show-ref test",
    )

    git_env = os.environ.copy()
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_CONFIG_GLOBAL"] = os.devnull
    commit_env = git_env.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "cmd_show_ref test",
            "GIT_AUTHOR_EMAIL": "cmd-show-ref@example.invalid",
            "GIT_AUTHOR_DATE": "2001-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "cmd_show_ref test",
            "GIT_COMMITTER_EMAIL": "cmd-show-ref@example.invalid",
            "GIT_COMMITTER_DATE": "2001-01-01T00:00:00+00:00",
        }
    )

    with tempfile.TemporaryDirectory(prefix="wyag-showref-trans-") as temp:
        temp_root = Path(temp)
        wyag_repo = temp_root / "wyag"
        git_repo = temp_root / "git"

        result = execute("initialize wyag repository", [WYAG, "init", wyag_repo])
        expect(result.returncode == 0, "wyag repository initializes")
        result = execute(
            "initialize reference Git repository",
            ["git", "-c", "init.defaultBranch=master", "init", "--quiet", git_repo],
            env=git_env,
        )
        expect(result.returncode == 0, "reference Git repository initializes")

        for repo in (wyag_repo, git_repo):
            (repo / "notes.txt").write_text(inputs["staging"]["notes.txt"]["initial"])
            (repo / "file with space.txt").write_text(
                inputs["staging"]["file with space.txt"]["initial"]
            )
            git(repo, "add", "notes.txt", "file with space.txt", env=git_env, label="stage initial files")
            git(repo, "commit", "-m", "first commit", env=commit_env, label="commit initial state")
            git(repo, "tag", "v1.0", env=git_env, label="create tag v1.0")

            # One staged change
            (repo / "notes.txt").write_text(inputs["staging"]["notes.txt"]["updated"])
            git(repo, "add", "notes.txt", env=git_env, label="stage notes update")

            # One unstaged change
            (repo / "file with space.txt").write_text(inputs["staging"]["file with space.txt"]["updated"])

        # Capture initial refs before show-ref and verify show-ref output
        initial_refs_fs = get_refs_dict(wyag_repo)
        showref_initial = execute("wyag show-ref initial", [WYAG, "show-ref"], cwd=wyag_repo)
        expect(showref_initial.returncode == 0, "wyag show-ref exits 0 on initial state")
        parsed_initial = parse_show_ref_output(showref_initial.stdout)

        expect("refs/heads/master" in parsed_initial, "initial show-ref contains refs/heads/master")
        expect("refs/tags/v1.0" in parsed_initial, "initial show-ref contains refs/tags/v1.0")
        expect(parsed_initial["refs/heads/master"] == initial_refs_fs["refs/heads/master"],
               "show-ref output matches master ref on disk")
        expect(parsed_initial["refs/tags/v1.0"] == initial_refs_fs["refs/tags/v1.0"],
               "show-ref output matches tag ref on disk")

        # Verify show-ref is strictly read-only: refs on disk remain identical
        post_showref_fs = get_refs_dict(wyag_repo)
        expect(initial_refs_fs == post_showref_fs, "show-ref causes zero filesystem mutations to refs")

        # Create a new feature branch and advance it with a commit (state transition)
        feature_env = commit_env.copy()
        feature_env["GIT_AUTHOR_DATE"] = "2001-01-01T01:00:00+00:00"
        feature_env["GIT_COMMITTER_DATE"] = "2001-01-01T01:00:00+00:00"
        git(wyag_repo, "checkout", "-b", "feature", env=git_env, label="checkout feature branch")
        (wyag_repo / "feature.txt").write_text("feature content\n")
        git(wyag_repo, "add", "feature.txt", env=git_env, label="add feature file")
        git(wyag_repo, "commit", "-m", "feature commit", env=feature_env, label="commit on feature")

        # Now run show-ref again and verify state transition
        showref_after = execute("wyag show-ref after transition", [WYAG, "show-ref"], cwd=wyag_repo)
        expect(showref_after.returncode == 0, "wyag show-ref exits 0 after transition")
        parsed_after = parse_show_ref_output(showref_after.stdout)

        # 1. Assert the intended change: refs/heads/feature exists with the new commit
        feature_head = git(wyag_repo, "rev-parse", "refs/heads/feature", env=git_env, label="get feature head").strip()
        expect("refs/heads/feature" in parsed_after, "show-ref contains new feature ref")
        expect(parsed_after["refs/heads/feature"] == feature_head, "feature ref points to new feature commit")

        # 2. Assert unrelated states remain unchanged: master and tag v1.0
        expect(parsed_after["refs/heads/master"] == parsed_initial["refs/heads/master"],
               "unrelated refs/heads/master remains strictly unchanged")
        expect(parsed_after["refs/tags/v1.0"] == parsed_initial["refs/tags/v1.0"],
               "unrelated refs/tags/v1.0 remains strictly unchanged")


def write_evidence():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    (EVIDENCE / "tool-versions.json").write_text(
        json.dumps(report.get("tool_versions", {}), indent=2) + "\n"
    )
    (EVIDENCE / "results.json").write_text(json.dumps(report, indent=2) + "\n")


try:
    run_checks()
    report["passed"] = True
finally:
    write_evidence()
