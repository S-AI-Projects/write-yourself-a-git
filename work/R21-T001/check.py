#!/usr/bin/env python3
"""Run native tests and record the cmd_add contract checks."""

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
        "notes.txt": {"initial": "before\n", "updated": "alpha\n", "expected": "staged"},
        "file with space.txt": {
            "initial": "space before\n",
            "updated": "space changed\n",
            "expected": "unstaged",
        },
    },
    "edge_cases": {
        "empty arguments": "exit 2, required-path diagnostic, no repository state change",
        "missing file": "non-zero exit, missing-file diagnostic, no index creation",
    },
    "normalization": [
        "Baseline commit dates and author/committer identity are fixed.",
        "Index metadata timestamps are excluded by comparing git ls-files --stage.",
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


def git_state(repo, env, label):
    return {
        "head": git(repo, "rev-parse", "HEAD", env=env, label=f"{label}: HEAD"),
        "index_entries": git(
            repo, "ls-files", "--stage", env=env, label=f"{label}: index"
        ),
        "status": git(
            repo,
            "status",
            "--porcelain",
            "--untracked-files=all",
            env=env,
            label=f"{label}: status",
        ),
    }


def parse_index_entries(output):
    entries = {}
    for line in output.splitlines():
        metadata, path = line.split("\t", 1)
        mode, object_id, stage = metadata.split()
        entries[path] = {"mode": mode, "object_id": object_id, "stage": stage}
    return entries


def empty_repo_state(repo):
    index = repo / ".git" / "index"
    head = repo / ".git" / "HEAD"
    refs_dir = repo / ".git" / "refs"
    refs = {}
    if refs_dir.exists():
        for ref in sorted(path for path in refs_dir.rglob("*") if path.is_file()):
            refs[str(ref.relative_to(repo / ".git"))] = ref.read_text()
    return {
        "index_exists": index.exists(),
        "index_sha256": (
            hashlib.sha256(index.read_bytes()).hexdigest() if index.exists() else None
        ),
        "head": head.read_text() if head.exists() else None,
        "refs": refs,
    }


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
        "add stages files and rejects empty and missing paths" in native.stdout,
        "native suite executes the focused add test",
    )

    git_env = os.environ.copy()
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_CONFIG_GLOBAL"] = os.devnull
    commit_env = git_env.copy()
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": "cmd_add contract test",
            "GIT_AUTHOR_EMAIL": "cmd-add@example.invalid",
            "GIT_AUTHOR_DATE": "2001-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "cmd_add contract test",
            "GIT_COMMITTER_EMAIL": "cmd-add@example.invalid",
            "GIT_COMMITTER_DATE": "2001-01-01T00:00:00+00:00",
        }
    )

    with tempfile.TemporaryDirectory(prefix="wyag-add-contract-") as temp:
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
            git(
                repo,
                "add",
                "--",
                "notes.txt",
                "file with space.txt",
                env=git_env,
                label=f"stage baseline in {repo.name}",
            )
            result = execute(
                f"create baseline commit in {repo.name}",
                [
                    "git",
                    "-C",
                    repo,
                    "-c",
                    "commit.gpgsign=false",
                    "-c",
                    "user.name=cmd_add contract test",
                    "-c",
                    "user.email=cmd-add@example.invalid",
                    "commit",
                    "--no-gpg-sign",
                    "-m",
                    "baseline",
                ],
                env=commit_env,
            )
            expect(result.returncode == 0, f"baseline commit exists in {repo.name}")

        before = {
            "wyag": git_state(wyag_repo, git_env, "before wyag add"),
            "git": git_state(git_repo, git_env, "before git add"),
        }
        for repo in (wyag_repo, git_repo):
            (repo / "notes.txt").write_text(inputs["staging"]["notes.txt"]["updated"])
            (repo / "file with space.txt").write_text(
                inputs["staging"]["file with space.txt"]["updated"]
            )

        wyag_add = execute(
            "wyag add notes.txt",
            [WYAG, "add", "notes.txt"],
            cwd=wyag_repo,
        )
        git_add = execute(
            "git add notes.txt",
            ["git", "-C", git_repo, "add", "--", "notes.txt"],
            env=git_env,
        )
        expect(wyag_add.returncode == 0, "wyag add exits with status 0")
        expect(wyag_add.stdout == "", "wyag add has no standard output")
        expect(wyag_add.stderr == "", "wyag add has no standard error")
        expect(git_add.returncode == 0, "reference git add exits with status 0")

        after = {
            "wyag": git_state(wyag_repo, git_env, "after wyag add"),
            "git": git_state(git_repo, git_env, "after git add"),
        }
        wyag_entries = parse_index_entries(after["wyag"]["index_entries"])
        git_entries = parse_index_entries(after["git"]["index_entries"])
        expect(
            wyag_entries == git_entries,
            "Wyag and Git index entries match, including the path with spaces",
        )
        expect(
            after["wyag"]["head"] == before["wyag"]["head"],
            "wyag add leaves HEAD unchanged",
        )
        expect(
            after["git"]["head"] == before["git"]["head"],
            "reference git add leaves HEAD unchanged",
        )
        expected_status = ' M "file with space.txt"\nM  notes.txt\n'
        expect(
            after["wyag"]["status"] == expected_status,
            "wyag state has one staged and one unstaged change",
        )
        expect(
            after["wyag"]["status"] == after["git"]["status"],
            "Wyag and Git report the same staged and unstaged state",
        )
        expected_notes = git(
            wyag_repo,
            "hash-object",
            "notes.txt",
            env=git_env,
            label="hash staged notes",
        ).strip()
        expected_space = git(
            wyag_repo,
            "rev-parse",
            "HEAD:file with space.txt",
            env=git_env,
            label="resolve unstaged file baseline",
        ).strip()
        expect(
            wyag_entries["notes.txt"]["object_id"] == expected_notes,
            "staged notes entry points to the alpha blob",
        )
        expect(
            wyag_entries["file with space.txt"]["object_id"] == expected_space,
            "unstaged path retains its baseline blob in the index",
        )
        blob = git(
            wyag_repo,
            "cat-file",
            "-p",
            expected_notes,
            env=git_env,
            label="read staged notes blob",
        )
        expect(blob == "alpha\n", "staged blob contains alpha and a newline")
        worktree = {
            "wyag": {
                "notes.txt": (wyag_repo / "notes.txt").read_text(),
                "file with space.txt": (wyag_repo / "file with space.txt").read_text(),
            },
            "git": {
                "notes.txt": (git_repo / "notes.txt").read_text(),
                "file with space.txt": (git_repo / "file with space.txt").read_text(),
            },
        }
        expect(worktree["wyag"] == worktree["git"], "add leaves both worktrees unchanged")
        report["staging_scenario"] = {"before": before, "after": after, "worktree": worktree}

        empty_repo = temp_root / "empty"
        result = execute("initialize empty repository", [WYAG, "init", empty_repo])
        expect(result.returncode == 0, "empty repository initializes")
        empty_before = empty_repo_state(empty_repo)

        no_args = execute("wyag add with no paths", [WYAG, "add"], cwd=empty_repo)
        empty_after_no_args = empty_repo_state(empty_repo)
        expect(no_args.returncode == 2, "empty add invocation exits with status 2")
        expect(no_args.stdout == "", "empty add invocation has no standard output")
        expect(
            "required: path" in no_args.stderr,
            "empty add invocation reports the required path argument",
        )
        expect(
            empty_after_no_args == empty_before,
            "empty add invocation does not change repository state",
        )

        missing = execute(
            "wyag add missing.txt",
            [WYAG, "add", "missing.txt"],
            cwd=empty_repo,
        )
        empty_after_missing = empty_repo_state(empty_repo)
        expect(missing.returncode != 0, "missing-file add exits non-zero")
        expect(missing.stdout == "", "missing-file add has no standard output")
        expect(
            "Not a file, or outside the worktree" in missing.stderr,
            "missing-file add reports the invalid path",
        )
        expect(
            empty_after_missing == empty_before,
            "missing-file add does not create or alter the index or refs",
        )
        report["empty_repository_scenario"] = {
            "before": empty_before,
            "after_empty_arguments": empty_after_no_args,
            "after_missing_file": empty_after_missing,
        }


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