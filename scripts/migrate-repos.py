#!/usr/bin/env python3
"""
migrate-repos.py — apply the geoscape-sphinx-theme to Geoscape docs repos.

Loops over `docs_*` repos in a folder, creates/uses the `docs-ux-improvement`
branch, and makes the edits needed to consume the shared theme package instead
of an in-repo copy. Idempotent: safe to re-run — it only changes what isn't
already migrated.

SAFETY MODEL
------------
* DRY-RUN BY DEFAULT. Prints what it would change and touches nothing.
  Pass --apply to actually write files and create/switch branches.
* NEVER touches `master`. All writes happen on `docs-ux-improvement`.
* Leaves changes UNCOMMITTED for you to review (see the commented-out
  commit/push section near the bottom to enable automation later).
* After editing, it compile-checks each conf.py; if the result won't parse,
  it reports the repo as FAILED so you can fix it by hand.

USAGE
-----
    scripts/migrate-repos.py                 # dry-run over ../ (the geo-docs dir)
    scripts/migrate-repos.py --apply         # actually make the changes
    scripts/migrate-repos.py --dir /path     # scan a different folder
    scripts/migrate-repos.py --repo docs_buildings_guide   # just one repo

The theme version pinned into requirements.txt:
"""
from __future__ import annotations
import argparse
import re
import subprocess
import sys
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
BRANCH = "docs-ux-improvement"
BASE_BRANCH = "master"

GREEN, RED, YELLOW, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
)


def log(msg="", color=""):
    print(f"{color}{msg}{RESET}" if color else msg)


# --- git helpers ------------------------------------------------------------
def git(repo: Path, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )


def current_branch(repo: Path) -> str:
    return git(repo, "branch", "--show-current").stdout.strip()


def branch_exists(repo: Path, name: str) -> bool:
    r = git(repo, "rev-parse", "--verify", name, check=False)
    return r.returncode == 0


def worktree_dirty(repo: Path) -> bool:
    return bool(git(repo, "status", "--porcelain").stdout.strip())


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


# --- per-repo migration -----------------------------------------------------
def migrate(repo: Path, apply: bool) -> str:
    """Returns one of: MIGRATED, ALREADY, SKIPPED, FAILED."""
    name = repo.name
    conf = repo / "docs/source/conf.py"
    reqs = repo / "docs/requirements.txt"
    old_css = repo / "docs/source/_static/geoscape.css"

    if not conf.exists() or not reqs.exists():
        log(f"  {YELLOW}SKIP{RESET} {name}: missing conf.py or requirements.txt")
        return "SKIPPED"

    # --- git-state assessment (runs in BOTH dry-run and apply, so the dry-run
    #     is a truthful preview of what apply will do). Only the actual writes
    #     later are gated on `apply`. ---
    branch = current_branch(repo)
    dirty = worktree_dirty(repo)
    has_branch = branch_exists(repo, BRANCH)
    prefix = "would " if not apply else ""

    # BLOCKER: a dirty worktree means we can't safely switch branches / write.
    # Report it identically in dry-run and apply, and skip either way.
    if dirty:
        log(f"  {RED}{'WOULD SKIP' if not apply else 'SKIP'}{RESET} {name}: "
            f"uncommitted changes on '{branch}' — commit/stash first")
        return "SKIPPED"

    # INFO (non-blocking) — surfaced so there are no apply-time surprises:
    notes = []
    if has_branch:
        notes.append(f"branch '{BRANCH}' already exists → {prefix}check it out and re-apply")
    if branch != BASE_BRANCH and not has_branch:
        notes.append(f"currently on '{branch}', not '{BASE_BRANCH}' → "
                     f"{prefix}branch '{BRANCH}' off '{BASE_BRANCH}'")

    # --- plan the edits (pure, no writes) ---
    conf_new, conf_changes = edit_confpy(conf.read_text())
    reqs_new, reqs_changes = edit_requirements(reqs.read_text())
    css_change = ["delete old _static/geoscape.css"] if old_css.exists() else []
    all_changes = conf_changes + reqs_changes + css_change

    if not all_changes:
        log(f"  {GREEN}ALREADY{RESET} {name}: nothing to do (fully migrated)")
        return "ALREADY"

    # --- validate the new conf.py parses BEFORE we commit to writing ---
    try:
        compile(conf_new, str(conf), "exec")
    except SyntaxError as e:
        log(f"  {RED}FAILED{RESET} {name}: edited conf.py won't parse ({e}); "
            "needs manual migration")
        return "FAILED"

    log(f"  {'APPLY' if apply else 'DRY '} {name}:")
    for c in all_changes:
        log(f"      - {c}", DIM)
    for n in notes:
        log(f"      {YELLOW}! {n}{RESET}")

    if not apply:
        return "MIGRATED"

    # --- WRITE PATH (only with --apply) ---
    # branch: create off master if missing, else switch to it
    if branch_exists(repo, BRANCH):
        git(repo, "checkout", BRANCH)
    else:
        git(repo, "checkout", "-b", BRANCH, BASE_BRANCH)

    conf.write_text(conf_new)
    reqs.write_text(reqs_new)
    if old_css.exists():
        git(repo, "rm", "--quiet", str(old_css.relative_to(repo)), check=False)
        old_css.unlink(missing_ok=True)

    log(f"      {GREEN}written on branch {BRANCH} (uncommitted){RESET}")

    # ------------------------------------------------------------------
    # AUTOMATED COMMIT + PUSH (disabled for now — review diffs first).
    # When you're ready to automate, uncomment. It commits ONLY on the
    # docs-ux-improvement branch and pushes that branch (never master).
    #
    # git(repo, "add", "-A")
    # git(repo, "commit", "-m",
    #     "Consume shared geoscape-sphinx-theme instead of in-repo theme")
    # git(repo, "push", "-u", "origin", BRANCH)
    # log(f"      {GREEN}committed + pushed {BRANCH}{RESET}")
    # ------------------------------------------------------------------

    return "MIGRATED"


def main():
    ap = argparse.ArgumentParser(description="Apply geoscape-sphinx-theme to docs_* repos.")
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parents[2]),
                    help="folder to scan for docs_* repos (default: the geo-docs dir)")
    ap.add_argument("--repo", help="migrate only this one repo (name or path)")
    ap.add_argument("--apply", action="store_true",
                    help="actually write changes (default: dry-run)")
    args = ap.parse_args()

    root = Path(args.dir).resolve()
    if args.repo:
        p = Path(args.repo)
        repos = [p if p.is_absolute() else root / args.repo]
    else:
        repos = sorted(d for d in root.iterdir()
                       if d.is_dir() and d.name.startswith("docs_")
                       and (d / ".git").exists())

    mode = "APPLY" if args.apply else "DRY-RUN (no changes written)"
    log(f"=== migrate-repos [{mode}] — {len(repos)} repo(s) under {root} ===")
    if not args.apply:
        log("    re-run with --apply to write changes on the "
            f"'{BRANCH}' branch (master is never touched).", YELLOW)

    tally: dict[str, int] = {}
    for repo in repos:
        try:
            result = migrate(repo, args.apply)
        except subprocess.CalledProcessError as e:
            log(f"  {RED}FAILED{RESET} {repo.name}: git error: "
                f"{e.stderr.strip()}")
            result = "FAILED"
        tally[result] = tally.get(result, 0) + 1

    log("\n=== summary ===")
    for k in ("MIGRATED", "ALREADY", "SKIPPED", "FAILED"):
        if tally.get(k):
            log(f"  {k}: {tally[k]}")
    # non-zero exit if anything failed, so CI/automation can catch it
    sys.exit(1 if tally.get("FAILED") else 0)


if __name__ == "__main__":
    main()
