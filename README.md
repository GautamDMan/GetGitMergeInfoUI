# GetGitMergeInfo — UI edition

A local web UI wrapped around the original [GetGitMergeInfo](https://github.com/GautamDMan/GetGitMergeInfo)
script. Same git logic, same semantics — but instead of editing `input.csv` /
`git_login.json` and reading `output.csv`, you use a form in your browser and
get an interactive, sortable-by-eye results table with one-click CSV export.

Everything still runs **locally** against a repo path you give it. Nothing is
uploaded anywhere; the Flask server only talks to `git` on your own machine.

## What changed vs. the CLI script

| CLI script | UI edition |
|---|---|
| Edit `git_login.json` for repo path/branch | Type them into the form |
| Edit `input.csv` for file names | Paste file names into a textarea, one per line |
| Run `python get_last_merge_info.py ...` | Click "Find merge info" |
| Read `output.csv` | Read an interactive results table in the browser |
| Always hard-resets if `branch` is set | Hard reset only happens if you tick the confirm box — a bare `branch` alone just tells it what to compare merges against |
| `print()` progress to terminal | A collapsible log panel in the page |
| — | "Download output.csv" button reproduces the exact original CSV format |

The underlying git logic (finding the file, walking `--merges --full-history`,
parsing `Merge pull request #N from owner/branch` / `Merge branch 'name'`,
figuring out `pushed_by` from the merge commit's second parent, and collecting
every other merge of the same branch) is unchanged from the original script.

## Requirements

- Python 3
- `git` available on `PATH`
- Flask (see `requirements.txt`)

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

## Using it

1. **Repo path** — local path to the one git repository to search.
2. **Branch** (optional) — if set, a checkbox appears letting you confirm a
   hard reset to that branch before searching. Leaving the checkbox unticked
   reads the repo exactly as it sits on disk (same as leaving `branch` out of
   `git_login.json` in the original script).
3. **File names** — bare file names (not full paths), one per line.
4. Click **Find merge info**. Results appear as a table; a file that couldn't
   be resolved (not found, or ambiguous — multiple files with that name) shows
   up as an error row with the same detail the original script wrote into
   `merge_message`.
5. Click **Download output.csv** to get the same CSV format the CLI script
   produced: `file_name,resolved_path,merge_owner,pushed_by,pushed_by_email,
   merge_message,merged_branch,merge_commit,merged_at,branch_merges`.

## Important caveats (same as the original)

- **Destructive when you opt in:** ticking the reset checkbox runs
  `git checkout <branch>` + `git reset --hard <branch>`, discarding
  uncommitted local changes. Don't point this at a repo with uncommitted work
  you care about unless you're fine losing it.
- **No remote sync:** nothing is fetched or pulled. Merge info reflects
  whatever your local branch tip currently is.

## Files

```
app.py               Flask backend (ported git logic + JSON API)
templates/index.html Single-page UI (form, results table, CSV export)
requirements.txt      Python dependencies
```
