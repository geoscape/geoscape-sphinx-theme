"""Geoscape Sphinx theme.

A shadcn-inspired documentation theme that inherits from alabaster and adds
Geoscape branding, a collapsible sidebar nav, dark mode, and a restyled search.

Registered automatically via the ``sphinx.html_themes`` entry point, so a
consuming ``conf.py`` only needs ``html_theme = "geoscape"``.
"""
from pathlib import Path

__version__ = "1.0.0"

_THEME_DIR = Path(__file__).parent / "theme"


def _set_defaults(app, config):
    """Fill in the sidebar layout and docs-home context unless the consuming
    repo has already set its own. Runs at config-inited so repo conf.py wins."""
    if not config.html_sidebars:
        config.html_sidebars = {
            "**": [
                "about.html",
                "navigation.html",
                "relations.html",
                "searchbox.html",
            ]
        }
    config.html_context.setdefault("docs_home_url", "https://docs.geoscape.com.au")
    config.html_context.setdefault("docs_home_label", "Geoscape Documentation")


def setup(app):
    app.add_html_theme("geoscape", str(_THEME_DIR / "geoscape"))
    app.connect("config-inited", _set_defaults)
    # Inject CSS/JS here rather than via `theme.conf [theme] stylesheets=/scripts=`:
    # when inheriting from alabaster, the parent theme's layout controls stylesheet
    # emission and does not reliably pick up the child theme's `stylesheets` entry,
    # so add_css_file guarantees geoscape.css is linked. Also more version-robust.
    app.add_css_file("geoscape.css")
    app.add_js_file("geoscape.js")
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
