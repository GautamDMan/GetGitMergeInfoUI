#!/usr/bin/env python3
"""
GetGitMergeInfo - UI edition (optimized)
========================================
Local web UI over the original get_last_merge_info.py logic. Everything runs
locally against the repo path you give it.

If a file name exists in several folders, merge info is returned for EVERY
location (one result row per location).

Performance notes (vs. the previous version)
--------------------------------------------
* Files are located with ONE `git ls-files` call, indexed by file name,
  instead of an os.walk of the whole working tree per file name.
* The "all merges of the same branch" lookup runs ONE `git log --merges --all`
  for the whole request and is indexed by branch, instead of one full-history
  scan per distinct branch.
* The merge-commit lookup returns parent hashes in the same call, saving one
  git invocation per location; "pushed by" lookups are cached per commit.
* Per-location git lookups run in a small thread pool (they're subprocess
  bound), with results kept in input order.
* Duplicate file names in the input are processed once.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000
(Set FLASK_DEBUG=1 if you want the Werkzeug debugger; it is off by default.)
"""

import csv
import io
import os
import re
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, render_template, request, Response

app = Flask(__name__)

MAX_WORKERS = 8

# "Merge pull request #123 from owner/branch-name"
PR_MERGE_RE = re.compile(r"Merge pull request #\d+ from ([^\s/]+)/(\S+)")
# "Merge branch 'branch-name' into target"
BRANCH_MERGE_RE = re.compile(r"Merge branch '([^']+)'")

ROW_FIELDS = [
    "file_name", "resolved_path", "merge_owner", "pushed_by", "pushed_by_email",
    "merge_message", "merged_branch", "merge_commit", "merged_at", "branch_merges",
]


# --------------------------------------------------------------------------
# Git helpers
# --------------------------------------------------------------------------

def run_git(repo_path, args, check=True):
    result = subprocess.run(
        ["git", "-C", repo_path] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def validate_repo(repo_path):
    if not repo_path or not os.path.isdir(repo_path):
        raise ValueError(f"'{repo_path}' is not a directory that exists on this machine")
    # rev-parse (rather than checking for a .git folder) also accepts
    # worktrees and submodules, where .git is a file.
    out = run_git(repo_path, ["rev-parse", "--is-inside-work-tree"], check=False)
    if out != "true":
        raise ValueError(f"'{repo_path}' does not look like a git repository")


def hard_reset_to_branch(repo_path, branch):
    """Checks out the branch and hard-resets the working tree to it,
    discarding local changes. Destructive - only runs when confirmed."""
    if branch.startswith("-"):
        raise ValueError(f"invalid branch name '{branch}'")
    run_git(repo_path, ["checkout", branch, "--"])
    run_git(repo_path, ["reset", "--hard", branch, "--"])


def parse_merge_subject(subject):
    """Returns (pr_owner_or_None, branch_or_'')."""
    m = PR_MERGE_RE.search(subject)
    if m:
        return m.group(1), m.group(2)
    m = BRANCH_MERGE_RE.search(subject)
    if m:
        return None, m.group(1)
    return None, ""


def index_repo_files(repo_path):
    """One `git ls-files` call -> {file_name: [sorted repo-relative paths]}.
    Only tracked files are indexed (untracked/ignored files can't have merge
    history anyway, and this skips things like node_modules copies)."""
    out = run_git(repo_path, ["-c", "core.quotepath=off", "ls-files", "-z"], check=False)
    index = defaultdict(list)
    for path in out.split("\0"):
        if path:
            index[path.rsplit("/", 1)[-1]].append(path)
    for paths in index.values():
        paths.sort()
    return index


def get_pushed_by(repo_path, merge_commit, parents, cache):
    """Author of the merge's second parent (the tip of the merged branch);
    falls back to the merge commit itself. Cached per target commit."""
    target = parents[1] if len(parents) >= 2 else merge_commit
    if target not in cache:
        info = run_git(repo_path, ["log", "-1", "--pretty=format:%an%x01%ae", target], check=False)
        name, _, email = info.partition("\x01")
        cache[target] = (name, email)
    return cache[target]


def get_last_merge_info_for_file(repo_path, rel_path, pushed_by_cache):
    """Most recent merge commit touching rel_path. --full-history is needed
    alongside --merges because default history simplification hides merges
    whose result equals one parent."""
    fmt = "%H%x01%an%x01%s%x01%cI%x01%P"
    out = run_git(
        repo_path,
        ["log", "--merges", "--full-history", "-1", f"--pretty=format:{fmt}", "--", rel_path],
        check=False,
    )
    if not out:
        return {"error": "no merge commit found that touched this file"}

    commit_hash, author, subject, committed_at, parents = out.split("\x01")
    pr_owner, merged_branch = parse_merge_subject(subject)
    name, email = get_pushed_by(repo_path, commit_hash, parents.split(), pushed_by_cache)

    return {
        "merge_owner": pr_owner or author,
        "pushed_by": name,
        "pushed_by_email": email,
        "merge_message": subject,
        "merged_branch": merged_branch,
        "merge_commit": commit_hash,
        "merged_at": committed_at,
    }


def build_branch_merge_index(repo_path):
    """ONE scan of every merge commit in the repo -> {branch: "hash8 (date); ..."}."""
    out = run_git(repo_path, ["log", "--merges", "--all", "--pretty=format:%H%x01%s%x01%cI"], check=False)
    entries = defaultdict(list)
    for line in out.split("\n"):
        parts = line.split("\x01")
        if len(parts) != 3:
            continue
        commit_hash, subject, committed_at = parts
        _, branch = parse_merge_subject(subject)
        if branch:
            entries[branch].append(f"{commit_hash[:8]} ({committed_at})")
    return {b: "; ".join(v) for b, v in entries.items()}


# --------------------------------------------------------------------------
# Row building / pipeline
# --------------------------------------------------------------------------

def blank_row(file_name, error, resolved_path=""):
    row = {k: "" for k in ROW_FIELDS}
    row["file_name"] = file_name
    row["resolved_path"] = resolved_path
    row["merge_message"] = f"ERROR: {error}"
    return row


def build_row_for_path(repo_path, file_name, rel_path, pushed_by_cache):
    try:
        info = get_last_merge_info_for_file(repo_path, rel_path, pushed_by_cache)
    except Exception as e:  # noqa: BLE001 - surface any git error into the row
        return blank_row(file_name, str(e), rel_path)
    if "error" in info:
        return blank_row(file_name, info["error"], rel_path)
    row = {k: "" for k in ROW_FIELDS}
    row.update(info)
    row["file_name"] = file_name
    row["resolved_path"] = rel_path
    return row


def process(repo_path, branch, do_reset, file_names):
    log = []
    validate_repo(repo_path)

    if branch and do_reset:
        log.append(f"Hard-resetting {repo_path} to branch '{branch}'...")
        hard_reset_to_branch(repo_path, branch)
        log.append(f"Done. Working tree now matches '{branch}'.")
    elif branch:
        log.append(f"Branch '{branch}' set but reset not confirmed - reading repo as-is on disk.")
    else:
        log.append("No branch given - reading repo exactly as it currently sits on disk.")

    # De-duplicate names, keep input order.
    file_names = list(dict.fromkeys(file_names))

    file_index = index_repo_files(repo_path)

    # Plan: a list of slots in output order; each is either a ready row or a
    # (file_name, rel_path) job to run.
    slots = []
    for name in file_names:
        matches = file_index.get(name, [])
        log.append(f"Searching for '{name}'...")
        if not matches:
            slots.append(blank_row(name, f"file '{name}' not found in repo"))
            log.append(f"  '{name}' not found.")
            continue
        if len(matches) > 1:
            log.append(f"  Found {len(matches)} locations for '{name}':")
            log.extend(f"    - {p}" for p in matches)
        else:
            log.append(f"  Found at {matches[0]}")
        slots.extend((name, p) for p in matches)

    jobs = [s for s in slots if isinstance(s, tuple)]
    pushed_by_cache = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = iter(pool.map(
            lambda j: build_row_for_path(repo_path, j[0], j[1], pushed_by_cache), jobs
        ))
    rows = [next(results) if isinstance(s, tuple) else s for s in slots]

    # Fill branch_merges from a single repo-wide scan, only if needed.
    if any(r["merged_branch"] for r in rows):
        branch_index = build_branch_merge_index(repo_path)
        for r in rows:
            if r["merged_branch"]:
                r["branch_merges"] = branch_index.get(r["merged_branch"], "")

    log.append(f"Done. Processed {len(file_names)} file name(s) -> {len(rows)} result row(s).")
    return rows, log


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/run", methods=["POST"])
def api_run():
    data = request.get_json(force=True) or {}
    repo_path = (data.get("repo_path") or "").strip()
    branch = (data.get("branch") or "").strip()
    do_reset = bool(data.get("confirm_reset"))
    raw_files = data.get("file_names") or ""
    file_names = [line.strip() for line in raw_files.splitlines() if line.strip()]

    if not file_names:
        return jsonify({"error": "Add at least one file name."}), 400

    try:
        rows, log = process(repo_path, branch, do_reset, file_names)
    except Exception as e:  # noqa: BLE001 - surface setup errors to the UI
        return jsonify({"error": str(e)}), 400

    return jsonify({"rows": rows, "log": log})


@app.route("/api/download", methods=["POST"])
def api_download():
    """Streams the rows the browser already has back as output.csv."""
    data = request.get_json(force=True) or {}
    rows = data.get("rows") or []

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=ROW_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in ROW_FIELDS})

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=output.csv"},
    )


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5000)
