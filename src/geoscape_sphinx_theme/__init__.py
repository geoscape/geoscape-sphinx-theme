"""Geoscape Sphinx theme.

A shadcn-inspired documentation theme that inherits from alabaster and adds
Geoscape branding, a collapsible sidebar nav, dark mode, and a restyled search.

Registered automatically via the ``sphinx.html_themes`` entry point, so a
consuming ``conf.py`` only needs ``html_theme = "geoscape"``.
"""
from pathlib import Path

__version__ = "1.0.8"

_THEME_DIR = Path(__file__).parent / "theme"

# Geoscape's shared PostHog project (US cloud). This is a client-side, write-only
# *project* key: it can only ingest events, never read data, and it already ships
# in the browser JS of every published page — so it is safe to hardcode here even
# though this repo is public. Hardcoding (rather than a per-repo conf.py setting)
# is deliberate: every consuming site reports to one project on its next build
# with no per-repo change. A repo can still override `posthog_key` in
# html_theme_options — set it to "" to opt out, or to another phc_ key to
# redirect its analytics elsewhere.
_POSTHOG_KEY = "phc_vb5q8MQ3RazE6ownA9Gpdxb8GiETgbF9pHNTH6BWnmVe"
# api_host is Geoscape's managed PostHog reverse proxy (not us.i.posthog.com):
# ingestion + the snippet's static assets are served from this domain, which is
# what lets the analytics survive ad-blockers. The proxy also serves /static/,
# so the loader in layout.html fetches array.js from here too. ui_host (set in
# the template) still points at the real PostHog app so in-app links resolve.
_POSTHOG_HOST = "https://ph.geoscape.com.au"


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
    # Resolve `singlehtml_search` to a real bool so `searchbox.html` can branch on
    # it directly. Only meaningful on singlehtml builds (see setup()), but the
    # template guard is harmless elsewhere. Defaults on.
    context["singlehtml_search"] = _is_enabled(config, "singlehtml_search", default=True)
    # PostHog analytics. These are string values, not bools, so read them off
    # html_theme_options directly. Default ON with Geoscape's shared project key
    # (see _POSTHOG_KEY above): if a repo did not set `posthog_key` at all
    # (get() -> None) we fall back to it. A repo that sets it explicitly wins,
    # INCLUDING setting it to "" to opt out — hence the None check rather than a
    # plain `or`, which couldn't tell "unset" from "deliberately blank". The
    # snippet in layout.html only renders when the resolved key is truthy.
    options = config.html_theme_options or {}
    raw_key = options.get("posthog_key")
    context["posthog_key"] = (_POSTHOG_KEY if raw_key is None else str(raw_key)).strip()
    raw_host = options.get("posthog_host")
    context["posthog_host"] = (str(raw_host).strip() if raw_host else _POSTHOG_HOST)


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
    # In-page search is only useful on singlehtml builds — the multi-page html
    # builder has Sphinx's real search — so link its file pair only there, and
    # only when enabled. Gating on the builder keeps every html build's asset
    # list byte-identical. `app.builder` is set by the time this runs (theme
    # resolution at builder-inited, same point that reads html_theme_options).
    builder_name = getattr(getattr(app, "builder", None), "name", None)
    if builder_name == "singlehtml" and _is_enabled(app.config, "singlehtml_search", default=True):
        app.add_css_file("singlehtml-search.css")
        app.add_js_file("singlehtml-search.js")
    # Collapsible sections is another optional feature (own file pair, linked
    # only when on). Unlike singlehtml-search it is not builder-gated — it
    # applies to both html and singlehtml.
    if _is_enabled(app.config, "collapsible_sections", default=True):
        app.add_css_file("collapsible-sections.css")
        app.add_js_file("collapsible-sections.js")
    return {
        "version": __version__,
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
