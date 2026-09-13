#!/usr/bin/env python3
"""
GetGitMergeInfo - UI edition
============================
A local web UI over the original get_last_merge_info.py logic.

Instead of input.csv / git_login.json / output.csv, you point this at a repo
in the browser, paste in file names, and get an interactive results table
(with CSV export). All git interaction is unchanged from the original script
and still runs 100% locally against the repo path you give it - nothing is
sent anywhere over the network.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://127.0.0.1:5000
"""
import csv
import io
import os
import re
import subprocess

from flask import Flask, jsonify, render_template, request, Response

app = Flask(__name__)

# Matches: "Merge pull request #123 from owner/branch-name"
PR_MERGE_RE = re.compile(r"Merge pull request #\d+ from ([^\s/]+)/(\S+)")
# Matches: "Merge branch 'branch-name' into target" (or without "into target")
BRANCH_MERGE_RE = re.compile(r"Merge branch '([^']+)'")


# --------------------------------------------------------------------------
# Core git logic (ported as-is from get_last_merge_info.py)
# --------------------------------------------------------------------------

def run_git(repo_path, args, check=True):
    result = subprocess.run(
        ["git", "-C", repo_path] + args,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def validate_repo(repo_path):
    if not repo_path or not os.path.isdir(repo_path):
        raise ValueError(f"'{repo_path}' is not a directory that exists on this machine")
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        raise ValueError(f"'{repo_path}' does not look like a git repository (no .git folder)")


def hard_reset_to_branch(repo_path, branch):
    """Checks out the given branch and hard-resets the working tree to it,
    discarding any local changes/commits that aren't on that branch tip."""
    run_git(repo_path, ["checkout", branch])
    run_git(repo_path, ["reset", "--hard", branch])


def find_file_in_repo(repo_path, file_name):
    """Search repo_path for a file named file_name (excluding .git internals).
    Returns (relative_path_or_None, list_of_all_relative_matches)."""
    matches = []
    for dirpath, dirnames, filenames in os.walk(repo_path):
        if ".git" in dirnames:
            dirnames.remove(".git")
        if file_name in filenames:
            full_path = os.path.join(dirpath, file_name)
            rel_path = os.path.relpath(full_path, repo_path)
            matches.append(rel_path)
    if len(matches) == 1:
        return matches[0], matches
    return None, matches


def get_pushed_by(repo_path, merge_commit_hash):
    """The merge commit's author is whoever performed the merge (often a
    maintainer or a bot), not necessarily who wrote the code. The actual dev
    who pushed the changes is the author of the tip commit on the branch that
    got merged in - i.e. the merge commit's second parent. Falls back to the
    merge commit's own author if there's no second parent."""
    parents = run_git(repo_path, ["log", "-1", "--pretty=format:%P", merge_commit_hash], check=False)
    parent_hashes = parents.split()
    target_commit = parent_hashes[1] if len(parent_hashes) >= 2 else merge_commit_hash
    info = run_git(repo_path, ["log", "-1", "--pretty=format:%an%x01%ae", target_commit], check=False)
    name, _, email = info.partition("\x01")
    return name, email


def get_last_merge_info_for_file(repo_path, rel_file_path):
    """Find the most recent merge commit that touched rel_file_path and parse
    owner/message/branch from it. Uses --full-history alongside --merges
    because git's default path-based history simplification hides merge
    commits whose result is identical to one parent."""
    log_format = "%H%x01%an%x01%s%x01%cI"
    output = run_git(
        repo_path,
        ["log", "--merges", "--full-history", "-1", f"--pretty=format:{log_format}", "--", rel_file_path],
        check=False,
    )
    if not output:
        return {"error": "no merge commit found that touched this file"}

    commit_hash, author, subject, committed_at = output.split("\x01")

    merged_branch = ""
    pr_owner = None
    m = PR_MERGE_RE.search(subject)
    if m:
        pr_owner, merged_branch = m.group(1), m.group(2)
    else:
        m = BRANCH_MERGE_RE.search(subject)
        if m:
            merged_branch = m.group(1)

    pushed_by_name, pushed_by_email = get_pushed_by(repo_path, commit_hash)

    return {
        "merge_owner": pr_owner or author,
        "pushed_by": pushed_by_name,
        "pushed_by_email": pushed_by_email,
        "merge_message": subject,
        "merged_branch": merged_branch,
        "merge_commit": commit_hash,
        "merged_at": committed_at,
    }


def get_all_merges_for_branch(repo_path, branch_name, cache):
    """Find every merge commit anywhere in the repo's history whose subject
    references branch_name, not just the most recent one. Cached per branch."""
    if not branch_name:
        return ""
    if branch_name in cache:
        return cache[branch_name]

    log_format = "%H%x01%s%x01%cI"
    output = run_git(repo_path, ["log", "--merges", "--all", f"--pretty=format:{log_format}"], check=False)

    entries = []
    if output:
        for line in output.split("\n"):
            if not line:
                continue
            parts = line.split("\x01")
            if len(parts) != 3:
                continue
            commit_hash, subject, committed_at = parts
            matched_branch = None
            m = PR_MERGE_RE.search(subject)
            if m:
                matched_branch = m.group(2)
            else:
                m = BRANCH_MERGE_RE.search(subject)
                if m:
                    matched_branch = m.group(1)
            if matched_branch == branch_name:
                entries.append(f"{commit_hash[:8]} ({committed_at})")

    result = "; ".join(entries)
    cache[branch_name] = result
    return result


ROW_FIELDS = [
    "file_name", "resolved_path", "merge_owner", "pushed_by", "pushed_by_email",
    "merge_message", "merged_branch", "merge_commit", "merged_at", "branch_merges",
]


def blank_row(file_name, error):
    row = {k: "" for k in ROW_FIELDS}
    row["file_name"] = file_name
    row["merge_message"] = f"ERROR: {error}"
    return row


def process(repo_path, branch, do_reset, file_names):
    """Runs the same pipeline as the CLI script's main(), but returns rows
    (list of dicts) plus a log of what happened instead of writing files."""
    log = []

    validate_repo(repo_path)

    if branch and do_reset:
        log.append(f"Hard-resetting {repo_path} to branch '{branch}'...")
        hard_reset_to_branch(repo_path, branch)
        log.append(f"Done. Working tree now matches '{branch}'.")
    elif branch and not do_reset:
        log.append(f"Branch '{branch}' set but reset not confirmed - reading repo as-is on disk.")
    else:
        log.append("No branch given - reading repo exactly as it currently sits on disk.")

    rows = []
    branch_merges_cache = {}

    for file_name in file_names:
        log.append(f"Searching for '{file_name}'...")
        rel_path, matches = find_file_in_repo(repo_path, file_name)

        if rel_path is None:
            if not matches:
                err = f"file '{file_name}' not found in repo"
            else:
                err = f"ambiguous: found {len(matches)} files named '{file_name}': {matches}"
            rows.append(blank_row(file_name, err))
            continue

        row = {"file_name": file_name, "resolved_path": rel_path}
        try:
            info = get_last_merge_info_for_file(repo_path, rel_path)
            if "error" in info:
                row.update({k: "" for k in ROW_FIELDS if k not in row})
                row["merge_message"] = f"ERROR: {info['error']}"
            else:
                row.update(info)
                row["branch_merges"] = get_all_merges_for_branch(
                    repo_path, info["merged_branch"], branch_merges_cache
                )
        except Exception as e:  # noqa: BLE001 - surface any git error into the row
            row.update({k: "" for k in ROW_FIELDS if k not in row})
            row["merge_message"] = f"ERROR: {e}"

        rows.append(row)

    log.append(f"Done. Processed {len(rows)} file(s).")
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
    except Exception as e:  # noqa: BLE001 - surface setup errors (bad path, git failure) to the UI
        return jsonify({"error": str(e)}), 400

    return jsonify({"rows": rows, "log": log})


@app.route("/api/download", methods=["POST"])
def api_download():
    """Takes the rows the browser already has and streams them back as
    output.csv, matching the original script's output format exactly."""
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
    app.run(debug=True, port=5000)
