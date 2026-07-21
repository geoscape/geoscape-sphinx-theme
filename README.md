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

## Compatibility

- Sphinx ≥ 4.0, alabaster ≥ 0.7.12 (pulled in automatically).
- Works with the `html` and `singlehtml` builders.
