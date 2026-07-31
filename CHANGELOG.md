# Changelog

## v1.0.4

- Show the "On this page" sidebar panel only when the current document has a
  third heading level (e.g. a 1.1.1). Pages that go only two deep already have
  every subsection listed in the main nav (1.1 under 1), so the panel was pure
  duplication there; it now appears only when it adds something the nav doesn't.

## v1.0.3

Image-preview and sidebar/relbar polish.

- Image preview: pinch-to-zoom on touch devices, and wheel/pinch zoom now keeps
  the point under the cursor (or the pinch midpoint) fixed instead of zooming
  from the centre.
- Sidebar: moved search up under the site title; replaced the "SEARCH" heading
  with a "Search..." placeholder; removed the divider above it; anchored the
  "Hide Search Matches" link so the nav tree no longer jumps when it appears.
- Relbar: trimmed padding and removed the dead gap above the top relbar.
- Removed the dotted underline alabaster drew across the sidebar title.
- Bumping the moving `v1` tag propagates this to consuming repos on next build.

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
