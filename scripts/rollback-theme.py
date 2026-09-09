#!/usr/bin/env python3
"""
rollback-theme.py — undo an apply-theme.py rollout, per repo + branch.

Companion to apply-theme.py. Reverts the theme-adoption commit on each affected
branch WITHOUT rewriting history: it creates an inverse commit with
`git revert` and pushes it, so there is never a force-push. Only used if needed.

It is driven by the JSONL manifest apply-theme.py writes (--manifest, required).
For each pushed branch the manifest names the exact commit (after_sha) to revert.
It only reverts when origin's branch tip is STILL that commit (nothing was built
on top); if the tip has moved, it reports the branch for manual handling rather
than guessing.

SAFETY MODEL (same shape as apply-theme.py)
-------------------------------------------
* DRY-RUN BY DEFAULT — prints what it would revert, writes/pushes nothing (only
  a read-only fetch runs).
* --apply required to write, AND must be confirmed (--yes or type YES).
* Detached checkouts only; original checkout restored per repo.
* Dirty worktrees are skipped.
* No force-push, ever. History is preserved; the undo is itself a commit.
* Pipe through `tee` if you want a plain-text transcript of the run.

USAGE
-----
    scripts/rollback-theme.py --manifest scripts/logs/apply-theme-<ts>.jsonl
    scripts/rollback-theme.py --manifest <ts>.jsonl --apply --yes --repo docs_x
"""
from __future__ import annotations
import argparse
import fnmatch
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

COMMIT_SUBJECT = "Adopt shared geoscape-sphinx-theme (pinned @v1)"

GREEN, RED, YELLOW, DIM, CYAN, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[36m", "\033[0m"
)


def log(msg="", color=""):
    print(f"{color}{msg}{RESET}" if color else msg)


def git(repo: Path, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )


def current_ref(repo: Path) -> str:
    b = git(repo, "branch", "--show-current").stdout.strip()
    return b or git(repo, "rev-parse", "HEAD").stdout.strip()


def worktree_dirty(repo: Path) -> bool:
    return bool(git(repo, "status", "--porcelain").stdout.strip())


def find_theme_commit(repo: Path, branch: str) -> str | None:
    """Newest commit on origin/branch whose subject matches the rollout subject."""
    r = git(repo, "log", "--format=%H%x1f%s", f"origin/{branch}", check=False)
    if r.returncode != 0:
        return None
    for ln in r.stdout.splitlines():
        sha, _, subject = ln.partition("\x1f")
        if subject.strip() == COMMIT_SUBJECT:
            return sha.strip()
    return None


def revert_on_branch(repo: Path, branch: str, target_sha: str, apply: bool) -> str:
    """Revert target_sha on origin/branch. Returns a status string."""
    tip = git(repo, "rev-parse", f"origin/{branch}", check=False).stdout.strip()

    # already reverted? (a later commit reverts target_sha)
    r = git(repo, "log", "--format=%s", f"origin/{branch}", check=False)
    if r.returncode == 0 and f'This reverts commit {target_sha}' not in r.stdout \
            and f"Revert \"{COMMIT_SUBJECT}\"" in r.stdout:
        # a revert of our subject already exists on the branch
        log(f"  {GREEN}ALREADY reverted{RESET} {branch}")
        return "ALREADY"

    if not apply:
        log(f"  DRY  {branch}: would revert {target_sha[:9]} and push "
            f"(tip {tip[:9]})")
        return "PLANNED"

    co = git(repo, "checkout", "--detach", f"origin/{branch}", check=False)
    if co.returncode != 0:
        log(f"  {RED}FAILED{RESET} {branch}: checkout: {co.stderr.strip()}", RED)
        return "FAILED"
    rv = git(repo, "revert", "--no-edit", target_sha, check=False)
    if rv.returncode != 0:
        git(repo, "revert", "--abort", check=False)
        log(f"  {RED}FAILED{RESET} {branch}: revert had conflicts "
            f"({rv.stderr.strip()}); handle manually", RED)
        return "FAILED"
    push = git(repo, "push", "origin", f"HEAD:refs/heads/{branch}", check=False)
    if push.returncode != 0:
        log(f"  {RED}FAILED{RESET} {branch}: push: {push.stderr.strip()}", RED)
        return "FAILED"
    log(f"  {GREEN}reverted + pushed{RESET} {branch}")
    return "REVERTED"


def process_repo_manifest(repo: Path, entries: list[dict], apply: bool,
                          branch_glob: str | None,
                          sleep: float = 0.0) -> dict[str, int]:
    name = repo.name
    tally: dict[str, int] = {}

    def bump(k):
        tally[k] = tally.get(k, 0) + 1

    log(f"\n{CYAN}=== {name} ==={RESET}")
    if worktree_dirty(repo):
        log(f"  {RED}SKIP REPO{RESET} {name}: uncommitted changes", RED)
        bump("SKIPPED")
        return tally

    git(repo, "fetch", "--all", "--prune", check=False)
    original = current_ref(repo)
    try:
        for e in entries:
            b = e["branch"]
            if branch_glob and not fnmatch.fnmatch(b, branch_glob):
                continue
            if not e.get("pushed"):
                log(f"  {DIM}SKIP {b}: apply did not push this branch{RESET}")
                bump("SKIPPED")
                continue
            after = e["after_sha"]
            tip = git(repo, "rev-parse", f"origin/{b}", check=False).stdout.strip()
            if tip != after:
                # a revert we already pushed also moves the tip; detect that
                if find_theme_commit(repo, b) is None:
                    log(f"  {GREEN}ALREADY reverted{RESET} {b} "
                        f"(theme commit gone from tip)")
                    bump("ALREADY")
                else:
                    log(f"  {YELLOW}MANUAL {b}: tip {tip[:9]} moved past our "
                        f"commit {after[:9]} — not auto-reverting{RESET}", YELLOW)
                    bump("MANUAL")
                continue
            st = revert_on_branch(repo, b, after, apply)
            bump(st)
            # throttle: a revert push triggers an RTD build like any other
            # commit, so space them out (org-wide build concurrency).
            if st == "REVERTED" and sleep > 0:
                log(f"  {DIM}sleeping {sleep:g}s before next push{RESET}")
                time.sleep(sleep)
    finally:
        git(repo, "checkout", original, check=False)
    return tally


def load_manifest(path: Path) -> dict[str, list[dict]]:
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for ln in path.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        rec = json.loads(ln)
        by_repo[rec["repo"]].append(rec)
    return by_repo


def main():
    ap = argparse.ArgumentParser(
        description="Roll back an apply-theme.py rollout (per repo + branch).")
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parents[2]),
                    help="folder holding the docs_* repos (default: geo-docs dir)")
    ap.add_argument("--manifest", required=True,
                    help="apply-theme JSONL manifest (from scripts/logs/)")
    ap.add_argument("--repo", action="append", default=[],
                    help="limit to this repo (name); repeatable")
    ap.add_argument("--branch", default=None, help="glob to scope branches")
    ap.add_argument("--apply", action="store_true",
                    help="actually revert + push (default: dry-run)")
    ap.add_argument("--yes", action="store_true",
                    help="skip the interactive confirmation for --apply")
    ap.add_argument("--sleep", type=float, default=0.0, metavar="SECONDS",
                    help="pause this many seconds after each revert push, to "
                         "keep RTD's shared build queue from spiking when "
                         "rolling back a repo with many active branches. "
                         "Default: 0 (no pause). Ignored in dry-run.")
    args = ap.parse_args()

    root = Path(args.dir).resolve()
    repo_filter = set(args.repo)

    mode = "APPLY" if args.apply else "DRY-RUN (no changes written)"
    log(f"=== rollback-theme [{mode}] — manifest {args.manifest} ===")

    if args.apply and not args.yes:
        log(f"{YELLOW}About to REVERT + PUSH theme commits. Proceed?{RESET}",
            YELLOW)
        try:
            if input("Type YES to proceed: ").strip() != "YES":
                log("Aborted (no confirmation).", YELLOW)
                sys.exit(1)
        except EOFError:
            log("Aborted (no confirmation).", YELLOW)
            sys.exit(1)

    total: dict[str, int] = {}
    by_repo = load_manifest(Path(args.manifest))
    for repo_name in sorted(by_repo):
        if repo_filter and repo_name not in repo_filter:
            continue
        repo = root / repo_name
        if not (repo / ".git").exists():
            log(f"\n{YELLOW}SKIP {repo_name}: not cloned at {repo}{RESET}", YELLOW)
            total["SKIPPED"] = total.get("SKIPPED", 0) + 1
            continue
        rt = process_repo_manifest(repo, by_repo[repo_name], args.apply,
                                   args.branch, args.sleep)
        for k, v in rt.items():
            total[k] = total.get(k, 0) + v

    log("\n=== summary ===")
    for k in ("REVERTED", "PLANNED", "ALREADY", "MANUAL", "SKIPPED", "FAILED"):
        if total.get(k):
            log(f"  {k}: {total[k]}")
    if not args.apply:
        log(f"{YELLOW}\nDry-run only — nothing was changed. Re-run with "
            f"--apply --yes to revert + push.{RESET}", YELLOW)
    sys.exit(1 if total.get("FAILED") else 0)


if __name__ == "__main__":
    main()
