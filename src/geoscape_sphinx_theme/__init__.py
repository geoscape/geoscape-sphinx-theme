"""Geoscape Sphinx theme.

A shadcn-inspired documentation theme that inherits from alabaster and adds
Geoscape branding, a collapsible sidebar nav, dark mode, and a restyled search.

Registered automatically via the ``sphinx.html_themes`` entry point, so a
consuming ``conf.py`` only needs ``html_theme = "geoscape"``.
"""
from pathlib import Path

__version__ = "1.0.1"

_THEME_DIR = Path(__file__).parent / "theme"


def _set_defaults(config):
    """Provide the sidebar link defaults unless the consuming repo set its own.

    Covers the docs-home link and the Geoscape website link. Both are rendered
    by ``navigation.html``; supplying them here means a consuming ``conf.py``
    needs no ``extra_nav_links`` entry for either.

    The sidebar layout is declared in the theme's ``theme.conf`` (``sidebars =``),
    which is evaluated at theme-load time and is stable across Sphinx versions —
    more reliable than setting ``html_sidebars`` from a runtime hook."""
    context = config.html_context
    context.setdefault("docs_home_url", "https://docs.geoscape.com.au")
    context.setdefault("docs_home_label", "Geoscape Documentation")
    context.setdefault("website_url", "https://geoscape.com.au/")
    context.setdefault("website_label", "Geoscape Website")


def setup(app):
    app.add_html_theme("geoscape", str(_THEME_DIR / "geoscape"))
    # Apply the html_context defaults immediately rather than from a
    # `config-inited` handler. When the theme is loaded via the
    # `sphinx.html_themes` entry point (the normal case — consumers only set
    # `html_theme`), this `setup()` runs during theme resolution at
    # `builder-inited`, which is AFTER `config-inited` has already fired, so a
    # handler connected here would never be called and the sidebar's
    # docs-home link would silently disappear.
    _set_defaults(app.config)
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
