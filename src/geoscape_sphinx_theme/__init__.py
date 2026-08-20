"""Geoscape Sphinx theme.

A shadcn-inspired documentation theme that inherits from alabaster and adds
Geoscape branding, a collapsible sidebar nav, dark mode, and a restyled search.

Registered automatically via the ``sphinx.html_themes`` entry point, so a
consuming ``conf.py`` only needs ``html_theme = "geoscape"``.
"""
from pathlib import Path

__version__ = "1.0.5"

_THEME_DIR = Path(__file__).parent / "theme"


def _set_defaults(config):
    """Provide the sidebar link defaults unless the consuming repo set its own.

    Covers the docs-home link (sidebar) and the Geoscape Hub link (topbar);
    supplying them here means a consuming ``conf.py`` needs no
    ``extra_nav_links`` entry for either.

    The sidebar layout is declared in the theme's ``theme.conf`` (``sidebars =``),
    which is evaluated at theme-load time and is stable across Sphinx versions —
    more reliable than setting ``html_sidebars`` from a runtime hook."""
    context = config.html_context
    context.setdefault("docs_home_url", "https://docs.geoscape.com.au")
    context.setdefault("docs_home_label", "Geoscape Documentation")
    context.setdefault("hub_url", "https://hub.geoscape.com.au/")
    context.setdefault("hub_label", "Go to Hub")
    # Resolve the `docs_home` theme option to a real bool for templates, so they
    # can write `{% if is_docs_home %}` without repeating the string-form dance
    # (`theme.conf` values arrive as strings — see `_is_enabled`). True only for
    # the docs-home landing repo, where the sidebar title and docs-home
    # self-link are redundant with the topbar wordmark and the page's own H1.
    context["is_docs_home"] = _is_enabled(config, "docs_home", default=False)


def _is_enabled(config, option, default=True):
    """Read a boolean theme option, tolerating the string forms Sphinx passes.

    Values from ``theme.conf [options]`` arrive as STRINGS, so a plain
    ``if config.html_theme_options.get(option)`` is truthy even for ``"false"``.
    A consumer may also set a real bool from ``conf.py``, so handle both."""
    value = (config.html_theme_options or {}).get(option)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("false", "0", "none", "no", "")


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
    # The image preview is one optional feature, so it lives in its own pair of
    # files, linked only when enabled — a consumer who turns it off pays no
    # parse cost (the files are still copied, as Sphinx copies all of a theme's
    # static/ directory, but nothing references them). Registered here at
    # `builder-inited` (see above), which is late enough that
    # html_theme_options has been read.
    if _is_enabled(app.config, "show_image_preview"):
        app.add_css_file("image-preview.css")
        app.add_js_file("image-preview.js")
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
