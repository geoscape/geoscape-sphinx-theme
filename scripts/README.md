# Rollout scripts

Tooling to roll the shared **geoscape-sphinx-theme** out to Geoscape's docs
repos and, if ever needed, roll it back. Read this before running anything —
the apply step commits and pushes to real branches.

| Script | Purpose | Writes to git? |
| --- | --- | --- |
| [`apply-theme.py`](apply-theme.py) | Edit each `docs_*` repo to consume the shared theme, then commit + push — **every remote branch of every repo**. | Yes, on `--apply` |
| [`rollback-theme.py`](rollback-theme.py) | Undo a rollout by reverting the theme commit per repo+branch (inverse commit, no force-push). | Yes, on `--apply` |
| [`test-propagation.sh`](test-propagation.sh) | Local pre-flight render check: fresh venv → install a consumer's `requirements.txt` from the theme tag → Sphinx build → assert the theme rendered. | No (read-only) |

## What a rollout changes in each consumer repo

Purely the wiring to use the shared theme package — no doc content is touched:

- **`docs/source/conf.py`**: `html_theme` → `'geoscape'`; remove `html_css_files`
  / `html_js_files` (the theme ships its own); remove any `html_sidebars = {…}`
  block (the theme provides the sidebar); drop `extra_nav_links` entries the
  theme now renders itself (docs-home, old website link, Hub link).
- **`docs/requirements.txt`**: drop unused `sphinx-rtd-theme`; add/repin
  `geoscape-sphinx-theme @ git+https://github.com/geoscape/geoscape-sphinx-theme.git@v1`.
- **`docs/source/_static/geoscape.css`**: delete the old in-repo copy if present.

Consumers pin the moving `@v1` tag, so they pick up new theme releases on their
next RTD build without a repo change. The rollout itself does **not** bump the
theme package version — it only rewires consumers.

Each affected branch gets one commit:

```
Adopt shared geoscape-sphinx-theme (pinned @v1)

Consume the shared geoscape-sphinx-theme package. 
Automated rollout via scripts/apply-theme.py.
```

## Safety model

- **Dry-run is the default.** Without `--apply`, both Python scripts only *read*
  (a `git fetch`) and print the full per-repo/per-branch plan. No writes, no
  branch switches, no commits, no pushes.
- **`--apply` requires confirmation** (`--yes`, or type `YES` when prompted).
- **Detached checkouts only** — your local branches are never reset; the repo is
  restored to its original checkout after each run.
- **Dirty worktrees are skipped** (a repo with uncommitted changes is left alone).
- **conf.py is compile-checked** before any commit; a branch whose edited
  conf.py won't parse is reported `FAILED` and left untouched.
- **Idempotent** — a branch already on the theme reports `ALREADY`; re-running is
  safe and resumes where you left off.
- **Rollback never force-pushes** — it reverts with an inverse commit, so history
  is preserved and auditable.
- **Every `--apply` run writes a manifest** to `scripts/logs/` (git-ignored):
  `apply-theme-<UTC>.jsonl`, one record per pushed branch. It's the required
  input for `rollback-theme.py` — see [Rolling back](#rolling-back) for what it
  contains and how the undo works. For a plain-text transcript, pipe a run
  through `tee` (see below).

## Run outcomes

Every branch ends a run with one status. The decision is content-based: the
script re-applies the transform to the branch's *current* files and looks at
whether that produces any diff.

| Status | Meaning |
| --- | --- |
| `MIGRATED` | The transform produced a diff (something still needed changing) — so it committed + pushed the theme-adoption edit (or `would`, in dry-run). |
| `ALREADY` | The transform produced no diff — the branch already consumes the theme, so it's left untouched. |
| `SKIPPED` | Not a docs tree (no `docs/source/conf.py` + `requirements.txt`), or the whole repo has a dirty worktree. |
| `FAILED` | The edited `conf.py` wouldn't parse (compile-gate), or the commit/push errored. The branch is left untouched. |

`MIGRATED` and `ALREADY` both mean the branch is on the theme afterwards — the
only difference is whether *this run* had work to do. That's why re-running is
safe: a second pass over a `MIGRATED` branch produces no diff and flips it to
`ALREADY`.

## Prerequisites

- Run **locally** from anywhere; scripts default to scanning the parent
  `geo-docs` dir (override with `--dir`).
- Push rights to the `geoscape/docs_*` repos (`git push` over your normal auth).
- `gh` authenticated (for the full-run pre-flight that checks every org `docs_*`
  repo is cloned locally; if `gh` is missing the check is skipped with a warning).
- All target repos cloned locally — a full run aborts if the org has a `docs_*`
  repo you haven't cloned, so nothing is silently missed.

## Recommended run order

Apply a repo or batch at a time so you can review the freshly-built pages before
moving on — then run the next chunk. Re-running is safe (`ALREADY` branches are
skipped), so there's no need for an interactive pause.

```bash
# 1. Preview everything (no changes):
scripts/apply-theme.py

# 2. Do one repo, then review its built pages before continuing:
scripts/apply-theme.py --apply --yes --repo docs_cadastre_guide

# 3. A batch of small repos:
scripts/apply-theme.py --apply --yes --repos docs_lga_guide,docs_wards_guide

# 4. A big repo with many active branches — throttle pushes so RTD's shared
#    build queue doesn't spike (see below):
scripts/apply-theme.py --apply --yes --repo docs_cadastre_release --sleep 60
```

Scope flags: `--repo <name>` (repeatable), `--repos a,b,c`, `--branch '<glob>'`
(e.g. `--branch stable` or `--branch 'AUG-*'`). Ctrl-C stops cleanly — the
manifest is flushed per branch, so a re-run resumes where you left off.

**`--sleep <seconds>`** pauses after each push. RTD's build concurrency is a
single **org-wide** pool (shared across every `docs_*` project), and it builds
every push to an *active* version. A repo with many active branches (the big
`_release` repos have 30+ monthly-snapshot versions) therefore fires 30+ builds
in one burst, which queues behind the shared limit and starves other projects'
builds until it drains. `--sleep 60` spaces those pushes to roughly the rate
builds free up (~one slot per ~45s at 4 concurrent), keeping the queue shallow.
Use it only on the high-active-branch repos; it's pointless (and just slows you
down) on repos with only `latest`/`stable` active, and it's ignored in dry-run.

### Rolling back

**The manifest is the receipt of the apply run.** Every time `apply-theme.py`
pushes the theme commit to a branch, it appends one line to
`scripts/logs/apply-theme-<UTC>.jsonl` recording exactly what it did:

```json
{"repo":"docs_cadastre_guide","branch":"master","before_sha":"a1b2c3…","after_sha":"d4e5f6…","pushed":true,"ts":"…"}
```

- `before_sha` — where the branch tip was *before* our change.
- `after_sha` — the theme-adoption commit we created (the thing to undo).
- `pushed` — whether it actually reached `origin`.

**Rollback undoes each of those commits without rewriting history.** For every
manifest entry, `rollback-theme.py` creates an *inverse* commit with
`git revert` and pushes it (never a force-push, never a delete — so both the
"applied" and "reverted" commits stay visible in the log). Before touching a
branch it compares `origin/<branch>`'s current tip to `after_sha`:

| Branch state now | What rollback does |
| --- | --- |
| tip still == `after_sha` (nothing built on top) | reverts + pushes (`PLANNED` in dry-run) |
| tip moved past our commit (someone committed after) | leaves it alone, reports `MANUAL` — never guesses |
| our commit no longer on the branch | `ALREADY` (already undone) |
| manifest line had `pushed:false` | `SKIPPED` (nothing landed to undo) |

That check is why `--manifest` is required: it tells rollback *which* exact
commit to reverse and *whether it's still safe* to do so.

Re-applying after a rollback just works: the revert restores the pre-theme
files, so a fresh `apply-theme.py --apply` sees old-style config again and
re-migrates the branch (reported `MIGRATED`, not `ALREADY`) — idempotency is
decided from the branch's current content, not its commit history.

```bash
# 1. Dry-run — see what would be reverted, writes nothing:
scripts/rollback-theme.py --manifest scripts/logs/apply-theme-<UTC>.jsonl

# 2. Actually revert + push:
scripts/rollback-theme.py --manifest scripts/logs/apply-theme-<UTC>.jsonl --apply --yes
```

Scope it the same way as apply: `--repo <name>` and `--branch '<glob>'`.
