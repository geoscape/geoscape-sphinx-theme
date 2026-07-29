# geoscape-sphinx-theme

A shadcn-inspired Sphinx documentation theme for Geoscape docs. It inherits from
[alabaster](https://alabaster.readthedocs.io/) and adds:

- Geoscape design tokens (OKLCH), light **and** dark mode with a theme toggle
- A collapsible sidebar nav with active-branch highlighting and an
  "On this page" local table of contents
- Restyled code blocks, tables, admonitions, and quick search
- A mobile drawer and responsive layout

It is the single source of truth for the theme — fix here once and every
consuming repo picks it up on its next build.

## ⚠️ This is a public repository

This repo is intentionally **public** so consuming repos (and their Read the Docs
builds) can install the theme over `git+https` with no authentication or SSH
deploy-key setup.

**Only presentation assets belong here** — CSS, JS, HTML templates, and theme
config. **Never commit anything sensitive**, including:

- API keys, tokens, credentials, or connection strings
- Internal URLs, hostnames, or infrastructure details not already public
- Proprietary content, customer data, or unpublished product information
- `.env` files or anything from a secrets manager

Doc *content* lives in the individual documentation repos, not here. If a change
would require any of the above, it does not belong in this theme.

## Install

Add to your repo's `docs/requirements.txt`:

```
geoscape-sphinx-theme @ git+https://github.com/geoscape/geoscape-sphinx-theme.git@v1
```

`@v1` is a moving major tag: bug fixes and non-breaking changes propagate
automatically on the next Read the Docs build. Breaking changes ship as `v2`,
which you opt into by changing `@v1` → `@v2`.

## Use

In `docs/source/conf.py`:

```python
html_theme = "geoscape"
```

That's it. The theme registers itself (via a `sphinx.html_themes` entry point,
so it does **not** go in `extensions`), ships its own CSS/JS, and provides a
default `html_sidebars` and docs-home context.

Remove the now-redundant lines a repo previously used for the in-tree theme:

- `html_css_files = ["geoscape.css"]` — the theme ships its own CSS
- `html_js_files = [...]` — the theme injects its own JS
- `html_sidebars = {...}` — the theme provides a default (keep only to customise)

Keep `templates_path = ['_templates']` — it lets a repo override any theme
template locally (a repo `_templates/navigation.html` wins over the theme's).

### Customising

- **Docs-home link** (top of sidebar external links): override in `conf.py`
  ```python
  html_context = {
      "docs_home_url": "https://docs.geoscape.com.au",
      "docs_home_label": "Geoscape Documentation",
  }
  ```
- **Favicon**: keep your own `_static/favicon.png` + `html_favicon` (per-repo).
- **Extra links**: `html_theme_options = {"extra_nav_links": {...}}`.
- **Extra CSS**: `html_css_files = ["your-overrides.css"]` — loads after the
  theme CSS, so it wins.

## Releasing (propagating a theme change)

A change reaches the consuming docs sites only when a **new version** is
published and each site is rebuilt. There are three version references and they
must stay in sync — this is the part that's easy to get wrong:

| Reference | Example | Notes |
|-----------|---------|-------|
| `pyproject.toml` → `version` | `1.0.2` | **Exact**, no `v` prefix (PEP 440). Never `v1`. |
| `__init__.py` → `__version__` | `1.0.2` | Same value as pyproject. |
| Exact git tag | `v1.0.2` | `v` prefix; points at this commit. |
| Moving major tag | `v1` | `v` prefix; **moved** to the same commit. |

**One version number** (`1.0.2`) goes in the two Python files; **two git tags**
(`v1.0.2` and `v1`) point at the same commit. The moving `v1` tag is only a git
pointer — it never appears in `pyproject.toml`.

**Why the version bump is mandatory:** pip decides whether to reinstall by
comparing the *version string*. If you move the `v1` tag but leave the version
unchanged, consumers pinned to `@v1` may see "already installed" and keep serving
the **old** theme with no error. Bumping the version forces the re-fetch.

### Steps

```bash
# 1. Test the change first (no tag yet):
scripts/test-propagation.sh ../docs_buildings_guide

# 2. Bump BOTH files to the new exact version (e.g. 1.0.2):
#    - pyproject.toml     version = "1.0.2"
#    - __init__.py        __version__ = "1.0.2"
#    - add a CHANGELOG.md entry

# 3. Commit, tag exact + move the major tag, push:
git commit -am "Release 1.0.2: <what changed>"
git tag v1.0.2            # exact tag == pyproject version, with a leading v
git tag -f v1             # move the major alias onto the same commit
git push origin master v1.0.2
git push -f origin v1     # force-push applies ONLY to the moving v1 tag

# 4. Rebuild the consuming repos on Read the Docs (they re-run pip install and
#    pick up the new version). At scale, trigger this via the RTD Build API
#    rather than clicking each project.
```

Consuming repos pinned to `@v1` need no file change to adopt a release — just a
rebuild. Repos pinned to an exact tag (`@v1.0.2`) adopt it by re-pinning
(`scripts/migrate-repos.py` can do this in bulk).

## Compatibility

- Sphinx ≥ 4.0, alabaster ≥ 0.7.12 (pulled in automatically).
- Works with the `html` and `singlehtml` builders.
