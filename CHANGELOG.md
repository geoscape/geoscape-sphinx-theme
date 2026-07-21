# Changelog

## v1.0.1

Fix the sidebar search box rendering as the default alabaster "Search/Go" box
(wrong style and position) on newer Sphinx/alabaster (e.g. Sphinx 9 +
alabaster 1.0 on Read the Docs).

- Declare the sidebar layout via `sidebars =` in `theme.conf` (evaluated at
  theme-load time) instead of setting `html_sidebars` from a `config-inited`
  hook, which newer Sphinx did not honour — so the custom `searchbox.html`
  now resolves reliably across Sphinx versions.
- Bumping the moving `v1` tag propagates this to consuming repos on next build.

## v1.0.0

Initial release. Extracted from the `data_scripts` pilot as the single source of
truth for the Geoscape docs theme.

- Inheriting Sphinx theme (`inherit = alabaster`), registered via the
  `sphinx.html_themes` entry point.
- Geoscape design tokens with light/dark mode + theme toggle (FOUC-safe).
- Collapsible sidebar navigation, "On this page" local ToC, restyled search.
- Restyled code, tables, admonitions; responsive/mobile drawer.
