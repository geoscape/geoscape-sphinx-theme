#!/usr/bin/env python3
"""
apply-theme.py — roll the geoscape-sphinx-theme out to Geoscape docs repos.

Loops over `docs_*` repos in a folder and, for EVERY remote branch of each repo,
makes the edits needed to consume the shared theme package instead of an in-repo
copy, then commits and pushes that branch directly. Idempotent: safe to re-run —
a branch that is already migrated is reported ALREADY and left untouched.

This replaces the earlier single-`docs-ux-improvement`-branch flow: the theme is
proven, so it now goes to all repos and all branches.

SAFETY MODEL
------------
* DRY-RUN BY DEFAULT. Prints what it would change, per repo and per branch, and
  touches nothing (no writes, no branch switches, no commits, no pushes). Only a
  read-only `git fetch` runs, so the dry-run is a truthful preview.
* --apply is required to write, AND must be confirmed (--yes, or type YES).
* Direct commit + push to each branch. No PR, no staging branch.
* Uses a DETACHED checkout of each remote branch, so your existing local
  branches are never reset or clobbered; the original checkout is restored after
  each repo.
* A dirty worktree makes a repo unsafe to touch — such repos are SKIPPED.
* Each edited conf.py is compile-checked before commit; a repo/branch whose
  result won't parse is reported FAILED and left alone.
* Every apply run writes a machine-readable JSONL manifest under scripts/logs/
  (git-ignored) — the precise input for rollback-theme.py. Pipe the run through
  `tee` if you also want a plain-text transcript.

USAGE
-----
    scripts/apply-theme.py                       # dry-run over every docs_* repo
    scripts/apply-theme.py --repo docs_x         # dry-run one repo (repeatable)
    scripts/apply-theme.py --repos a,b,c         # dry-run a batch
    scripts/apply-theme.py --branch 'DEC-*'      # scope to matching branches
    scripts/apply-theme.py --apply --yes --repo docs_x   # actually do one repo
    scripts/apply-theme.py --apply --yes                 # all repos

Run flexibility: --repo (repeatable) / --repos (comma list) / no filter (=all),
optionally narrowed by --branch <glob>. To review the built pages between chunks,
apply a repo or batch at a time and run the next when you're ready — re-running is
safe (already-migrated branches report ALREADY). Ctrl-C stops cleanly: the
manifest is flushed per branch, so a re-run resumes where you left off.
"""
from __future__ import annotations
import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --- configuration ----------------------------------------------------------
THEME_PKG = "geoscape-sphinx-theme"
THEME_TAG = "v1"  # bump this when adopting a newer theme release
THEME_REQ = (
    f"{THEME_PKG} @ git+https://github.com/geoscape/"
    f"geoscape-sphinx-theme.git@{THEME_TAG}"
)
THEME_REQ_COMMENT = (
    "# Geoscape docs theme (single source of truth). Pinned to an exact release "
    "for reproducible builds; bump this tag to adopt a new theme version."
)
COMMIT_SUBJECT = "Adopt shared geoscape-sphinx-theme (pinned @v1)"
COMMIT_BODY = (
    "Consume the shared geoscape-sphinx-theme package.\n"
    "Automated rollout via scripts/apply-theme.py."
)
COMMIT_MSG = f"{COMMIT_SUBJECT}\n\n{COMMIT_BODY}\n"

GREEN, RED, YELLOW, DIM, CYAN, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[36m", "\033[0m"
)

# populated in main() when --apply; None in dry-run
_MANIFEST_FH = None


def log(msg="", color=""):
    print(f"{color}{msg}{RESET}" if color else msg)


def manifest_record(rec: dict):
    if _MANIFEST_FH is not None:
        _MANIFEST_FH.write(json.dumps(rec) + "\n")
        _MANIFEST_FH.flush()


# --- git helpers ------------------------------------------------------------
def git(repo: Path, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )


def current_ref(repo: Path) -> str:
    """The branch name if on one, else the current commit sha (detached)."""
    b = git(repo, "branch", "--show-current").stdout.strip()
    if b:
        return b
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def worktree_dirty(repo: Path) -> bool:
    return bool(git(repo, "status", "--porcelain").stdout.strip())


def remote_branches(repo: Path) -> list[str]:
    """Short names of origin's branches, excluding origin/HEAD, sorted."""
    out = git(repo, "branch", "-r", "--format=%(refname:short)").stdout
    names = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln or "->" in ln or not ln.startswith("origin/"):
            continue
        name = ln[len("origin/"):]
        if name == "HEAD":
            continue
        names.append(name)
    return sorted(set(names))


# --- conf.py transforms (idempotent; each returns (new_text, [changes])) ----
def edit_confpy(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    # 1. html_theme -> 'geoscape'
    if re.search(r"""html_theme\s*=\s*['"]geoscape['"]""", text):
        pass  # already migrated
    else:
        new = re.sub(
            r"""html_theme\s*=\s*['"]alabaster['"]""",
            "html_theme = 'geoscape'",
            text,
        )
        if new != text:
            text = new
            changes.append("html_theme -> 'geoscape'")

    # 2. remove html_css_files / html_js_files lines (theme ships its own)
    for var in ("html_css_files", "html_js_files"):
        new = re.sub(rf"^\s*{var}\s*=.*\n", "", text, flags=re.MULTILINE)
        if new != text:
            text = new
            changes.append(f"removed {var}")

    # 3. remove the html_sidebars = {{ ... }} block (theme provides default).
    #    Matches a single top-level dict assignment ending at a line that is
    #    just `}`; conservative so it won't eat unrelated code.
    new = re.sub(
        r"^\s*html_sidebars\s*=\s*\{.*?^\}\n",
        "",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if new != text:
        text = new
        changes.append("removed html_sidebars block")

    # 4. dedupe the extra_nav_links the theme now handles itself:
    #      - the docs-home link (house icon, sidebar), which the theme renders
    #        and collapses exact-URL duplicates of via `docs_home_url`;
    #      - the old Geoscape *website* link — the theme no longer renders a
    #        website link at all (it now shows a "Go to Hub" topbar link
    #        instead), and stakeholders dropped the website link, so any stale
    #        entry here is removed outright rather than deduped;
    #      - a hand-added Hub link, so it doesn't duplicate the topbar one.
    #    NOTE: the theme's URL-dedup now compares against `hub_url`, not the
    #    website URL, so a stale website entry is ONLY removed here — hence we
    #    strip it at the source.
    #    Quotes may be single or double; label spelling varies across repos.
    for label_pattern, description in (
        (r"Geoscape Documentation", "docs-home"),
        (r"Geoscape Website|Geoscape", "website"),
        (r"Go to Hub|Geoscape Hub|Hub", "hub"),
    ):
        new = re.sub(
            rf"""^[ \t]*(['"])(?:{label_pattern})\1[ \t]*:[ \t]*"""
            r"""(['"])[^'"]*\2[ \t]*,?[ \t]*\n""",
            "",
            text,
            flags=re.MULTILINE,
        )
        if new != text:
            text = new
            changes.append(f"deduped {description} extra_nav_link")

    return text, changes


def _is_theme_line(line: str) -> bool:
    """True if this requirements line declares the geoscape theme package."""
    return line.strip().startswith(THEME_PKG)


def _pinned_tag(line: str) -> str | None:
    """Extract the git tag/ref a theme line is pinned to (the part after '@'
    in the git URL), or None if there is no '.git@<ref>' pin."""
    m = re.search(r"\.git@(?P<ref>\S+)", line)
    return m.group("ref") if m else None


def edit_requirements(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    lines = text.splitlines()

    # drop unused sphinx-rtd-theme
    kept = [ln for ln in lines if ln.strip() != "sphinx-rtd-theme"]
    if len(kept) != len(lines):
        changes.append("removed sphinx-rtd-theme")
    lines = kept

    theme_idxs = [i for i, ln in enumerate(lines) if _is_theme_line(ln)]

    if not theme_idxs:
        # not present at all -> append the pinned requirement
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(THEME_REQ_COMMENT)
        lines.append(THEME_REQ)
        changes.append(f"added {THEME_PKG} @ {THEME_TAG}")
    else:
        # present -> compare the ACTUAL pinned tag against THEME_TAG and
        # rewrite the line if it differs (covers v1 -> v1.0.2, v1.0.1 -> v1,
        # or an unpinned line getting a pin). Parsing the @<ref> avoids the
        # substring trap where "v1" spuriously matches "v1.0.1".
        for i in theme_idxs:
            current = _pinned_tag(lines[i])
            if current != THEME_TAG:
                old = current if current is not None else "(unpinned)"
                lines[i] = THEME_REQ
                changes.append(f"repinned {THEME_PKG}: {old} -> {THEME_TAG}")

    return "\n".join(lines) + "\n", changes


CONF_PATH = "docs/source/conf.py"
REQS_PATH = "docs/requirements.txt"
CSS_PATH = "docs/source/_static/geoscape.css"


def _show(repo: Path, ref: str, path: str) -> str | None:
    """Contents of `path` at `ref` (e.g. origin/master), or None if absent.
    Read-only — does NOT change the checkout."""
    r = git(repo, "show", f"{ref}:{path}", check=False)
    return r.stdout if r.returncode == 0 else None


def _exists_at(repo: Path, ref: str, path: str) -> bool:
    return git(repo, "cat-file", "-e", f"{ref}:{path}", check=False).returncode == 0


# --- per-branch edit planning + write --------------------------------------
def plan_branch_edits(repo: Path, ref: str):
    """Read the three files AT `ref` via `git show` (no checkout) and return
    (all_changes, conf_new, reqs_new, has_old_css) or None if `ref` is not a
    Sphinx docs tree (missing conf.py/requirements.txt)."""
    conf_text = _show(repo, ref, CONF_PATH)
    reqs_text = _show(repo, ref, REQS_PATH)
    if conf_text is None or reqs_text is None:
        return None

    conf_new, conf_changes = edit_confpy(conf_text)
    reqs_new, reqs_changes = edit_requirements(reqs_text)
    has_old_css = _exists_at(repo, ref, CSS_PATH)
    css_change = ["delete old _static/geoscape.css"] if has_old_css else []
    all_changes = conf_changes + reqs_changes + css_change
    return all_changes, conf_new, reqs_new, has_old_css


def write_branch_edits(repo: Path, conf_new: str, reqs_new: str, has_old_css: bool):
    (repo / CONF_PATH).write_text(conf_new)
    (repo / REQS_PATH).write_text(reqs_new)
    if has_old_css:
        git(repo, "rm", "--quiet", CSS_PATH, check=False)
        (repo / CSS_PATH).unlink(missing_ok=True)


# --- per-repo processing ----------------------------------------------------
def process_repo(repo: Path, apply: bool, branch_glob: str | None,
                 sleep: float = 0.0) -> dict[str, int]:
    """Process every (matching) remote branch of one repo.
    Returns a tally dict for this repo."""
    name = repo.name
    tally: dict[str, int] = {}

    def bump(k):
        tally[k] = tally.get(k, 0) + 1

    log(f"\n{CYAN}=== {name} ==={RESET}")

    if worktree_dirty(repo):
        log(f"  {RED}SKIP REPO{RESET} {name}: uncommitted changes — "
            f"commit/stash first", RED)
        bump("SKIPPED")
        return tally

    # read-only in dry-run and apply alike; needed to see all branches
    git(repo, "fetch", "--all", "--prune", check=False)

    branches = remote_branches(repo)
    if branch_glob:
        branches = [b for b in branches if fnmatch.fnmatch(b, branch_glob)]
    if not branches:
        log(f"  {YELLOW}no matching remote branches{RESET}")
        return tally

    original = current_ref(repo)
    prefix = "" if apply else "would "
    needs_restore = False
    try:
        for b in branches:
            ref = f"origin/{b}"
            # PLAN read-only via `git show` — no checkout, so dry-run never
            # moves HEAD or touches the worktree.
            planned = plan_branch_edits(repo, ref)
            if planned is None:
                log(f"  {DIM}SKIP {b}: no docs/source/conf.py + "
                    f"requirements.txt{RESET}")
                bump("SKIPPED")
                continue

            all_changes, conf_new, reqs_new, has_old_css = planned
            if not all_changes:
                log(f"  {GREEN}ALREADY{RESET} {b}")
                bump("ALREADY")
                continue

            # gate: edited conf.py must parse
            try:
                compile(conf_new, str(repo / CONF_PATH), "exec")
            except SyntaxError as e:
                log(f"  {RED}FAILED{RESET} {name}@{b}: edited conf.py won't "
                    f"parse ({e}); needs manual migration", RED)
                bump("FAILED")
                continue

            log(f"  {'APPLY' if apply else 'DRY '} {b}:")
            for c in all_changes:
                log(f"      - {c}", DIM)

            if not apply:
                log(f"      {DIM}{prefix}commit + push origin {b}{RESET}")
                bump("MIGRATED")
                continue

            # --- WRITE PATH (only reached with --apply) ---
            # detached checkout of the remote tip — never touches local branches
            co = git(repo, "checkout", "--detach", ref, check=False)
            if co.returncode != 0:
                log(f"  {RED}FAILED{RESET} {name}@{b}: cannot checkout "
                    f"{ref}: {co.stderr.strip()}", RED)
                bump("FAILED")
                continue
            needs_restore = True
            before_sha = git(repo, "rev-parse", "HEAD").stdout.strip()

            write_branch_edits(repo, conf_new, reqs_new, has_old_css)
            git(repo, "add", "-A")
            git(repo, "commit", "-m", COMMIT_MSG)
            after_sha = git(repo, "rev-parse", "HEAD").stdout.strip()
            push = git(repo, "push", "origin", f"HEAD:refs/heads/{b}", check=False)
            pushed = push.returncode == 0
            if pushed:
                log(f"      {GREEN}committed + pushed {b} "
                    f"({after_sha[:9]}){RESET}")
                bump("MIGRATED")
            else:
                log(f"      {RED}commit made but PUSH FAILED for {b}: "
                    f"{push.stderr.strip()}{RESET}", RED)
                bump("FAILED")
            manifest_record({
                "repo": name, "branch": b,
                "before_sha": before_sha, "after_sha": after_sha,
                "pushed": pushed,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            # throttle: space out pushes so RTD's shared build queue (org-wide
            # concurrency) doesn't spike. Only meaningful after a real push.
            if pushed and sleep > 0:
                log(f"      {DIM}sleeping {sleep:g}s before next push{RESET}")
                time.sleep(sleep)
    finally:
        # restore the repo to where we found it — only if we moved HEAD (apply)
        if needs_restore:
            git(repo, "checkout", original, check=False)

    return tally


# --- repo discovery + org completeness check --------------------------------
def discover_repos(root: Path, repo_filters: list[str]) -> list[Path]:
    if repo_filters:
        out = []
        for r in repo_filters:
            p = Path(r)
            out.append(p if p.is_absolute() else root / r)
        return out
    return sorted(d for d in root.iterdir()
                  if d.is_dir() and d.name.startswith("docs_")
                  and (d / ".git").exists())


def preflight_org_check(root: Path):
    """Warn/abort if the geoscape org has docs_* repos not cloned locally.
    Best-effort: needs `gh` authed; if gh is missing, we note it and continue."""
    gh = shutil.which("gh")
    if not gh:
        log(f"{YELLOW}pre-flight: `gh` not found — skipping org-completeness "
            f"check (cannot confirm every docs_* repo is cloned).{RESET}", YELLOW)
        return True
    r = subprocess.run([gh, "repo", "list", "geoscape", "--limit", "500",
                        "--json", "name", "-q", ".[].name"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log(f"{YELLOW}pre-flight: `gh repo list` failed ({r.stderr.strip()}) — "
            f"skipping org-completeness check.{RESET}", YELLOW)
        return True
    org = sorted(n for n in r.stdout.split() if n.startswith("docs_"))
    local = sorted(d.name for d in root.iterdir()
                   if d.is_dir() and d.name.startswith("docs_")
                   and (d / ".git").exists())
    missing = sorted(set(org) - set(local))
    if missing:
        log(f"{RED}pre-flight FAILED: {len(missing)} org docs_* repo(s) are not "
            f"cloned under {root}:{RESET}", RED)
        for m in missing:
            log(f"    - {m}", RED)
        log(f"{RED}Clone them first (so the rollout can't silently skip a "
            f"repo), or run with an explicit --repo/--repos.{RESET}", RED)
        return False
    log(f"{GREEN}pre-flight OK: all {len(org)} org docs_* repos are cloned "
        f"locally.{RESET}", GREEN)
    return True


def main():
    ap = argparse.ArgumentParser(
        description="Roll geoscape-sphinx-theme out to docs_* repos (all branches).")
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parents[2]),
                    help="folder to scan for docs_* repos (default: the geo-docs dir)")
    ap.add_argument("--repo", action="append", default=[],
                    help="process only this repo (name or path); repeatable")
    ap.add_argument("--repos", default="",
                    help="comma-separated list of repos to process")
    ap.add_argument("--branch", default=None,
                    help="glob to scope which remote branches are processed "
                         "(e.g. 'DEC-*', 'master'). Default: all branches.")
    ap.add_argument("--apply", action="store_true",
                    help="actually write, commit and push (default: dry-run)")
    ap.add_argument("--yes", action="store_true",
                    help="skip the interactive confirmation for --apply")
    ap.add_argument("--sleep", type=float, default=0.0, metavar="SECONDS",
                    help="pause this many seconds after each push, to keep "
                         "RTD's shared build queue from spiking on repos with "
                         "many active branches (e.g. 60 for the big _release "
                         "repos). Default: 0 (no pause). Ignored in dry-run.")
    args = ap.parse_args()

    root = Path(args.dir).resolve()
    repo_filters = list(args.repo)
    if args.repos:
        repo_filters += [r.strip() for r in args.repos.split(",") if r.strip()]
    repos = discover_repos(root, repo_filters)

    mode = "APPLY" if args.apply else "DRY-RUN (no changes written)"
    log(f"=== apply-theme [{mode}] — {len(repos)} repo(s) under {root} ===")
    log(f"    scope: {'all branches' if not args.branch else 'branches matching ' + args.branch!r}"
        + (f", repos filtered to {len(repos)}" if repo_filters else ""))

    # pre-flight completeness only matters for a full (unfiltered) run
    if not repo_filters:
        if not preflight_org_check(root):
            sys.exit(2)

    if args.apply and not args.yes:
        n = len(repos)
        scope = "all branches" if not args.branch else f"branches matching {args.branch!r}"
        log(f"{YELLOW}About to COMMIT + PUSH to {scope} across {n} repo(s). "
            f"This is irreversible except via rollback-theme.py.{RESET}", YELLOW)
        try:
            ans = input("Type YES to proceed: ").strip()
        except EOFError:
            ans = ""
        if ans != "YES":
            log("Aborted (no confirmation).", YELLOW)
            sys.exit(1)

    global _MANIFEST_FH
    if args.apply:
        logs_dir = Path(__file__).resolve().parent / "logs"
        logs_dir.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        _MANIFEST_FH = open(logs_dir / f"apply-theme-{stamp}.jsonl", "w")
        log(f"    manifest: scripts/logs/apply-theme-{stamp}.jsonl")

    total: dict[str, int] = {}
    try:
        for repo in repos:
            if not (repo / ".git").exists():
                log(f"\n{YELLOW}SKIP {repo.name}: not a git repo at {repo}{RESET}",
                    YELLOW)
                total["SKIPPED"] = total.get("SKIPPED", 0) + 1
                continue
            try:
                rt = process_repo(repo, args.apply, args.branch, args.sleep)
            except subprocess.CalledProcessError as e:
                log(f"  {RED}FAILED{RESET} {repo.name}: git error: "
                    f"{e.stderr.strip()}", RED)
                rt = {"FAILED": 1}
            for k, v in rt.items():
                total[k] = total.get(k, 0) + v
    finally:
        if _MANIFEST_FH:
            _MANIFEST_FH.close()

    log("\n=== summary ===")
    for k in ("MIGRATED", "ALREADY", "SKIPPED", "FAILED"):
        if total.get(k):
            log(f"  {k}: {total[k]}")
    if not args.apply:
        log(f"{YELLOW}\nDry-run only — nothing was changed. Re-run with "
            f"--apply --yes to commit + push.{RESET}", YELLOW)
    sys.exit(1 if total.get("FAILED") else 0)


if __name__ == "__main__":
    main()
