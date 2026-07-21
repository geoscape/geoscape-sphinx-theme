# Changelog

## v1.0.0

Initial release. Extracted from the `data_scripts` pilot as the single source of
truth for the Geoscape docs theme.

- Inheriting Sphinx theme (`inherit = alabaster`), registered via the
  `sphinx.html_themes` entry point.
- Geoscape design tokens with light/dark mode + theme toggle (FOUC-safe).
- Collapsible sidebar navigation, "On this page" local ToC, restyled search.
- Restyled code, tables, admonitions; responsive/mobile drawer.
