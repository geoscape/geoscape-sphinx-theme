(function () {
  'use strict';

  var STORAGE_KEY = 'gs-theme';
  var STATES = ['light', 'dark', 'auto'];
  var LABELS = { light: 'Light', dark: 'Dark', auto: 'Auto' };

  function readState() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      return STATES.indexOf(v) !== -1 ? v : 'auto';
    } catch (e) {
      return 'auto';
    }
  }

  function writeState(state) {
    try { localStorage.setItem(STORAGE_KEY, state); } catch (e) {}
  }

  function resolve(state) {
    if (state === 'auto') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return state;
  }

  function apply(state) {
    var resolved = resolve(state);
    document.documentElement.setAttribute('data-theme', state);
    document.documentElement.classList.remove('dark-mode-pre');
    if (resolved === 'dark') {
      document.body.classList.add('dark-mode');
    } else {
      document.body.classList.remove('dark-mode');
    }
    var btn = document.querySelector('.gs-theme-toggle');
    if (btn) {
      btn.setAttribute('data-theme-state', state);
      btn.setAttribute('aria-label', 'Theme: ' + state);
      var label = btn.querySelector('.gs-theme-toggle__label');
      if (label) label.textContent = LABELS[state];
    }
  }

  function next(state) {
    var i = STATES.indexOf(state);
    return STATES[(i + 1) % STATES.length];
  }

  /* Wrap every content table in a horizontally scrollable container.
     Sphinx emits `<table class="docutils">` as a bare sibling of the
     surrounding paragraphs, so there is no element for CSS `overflow-x` to
     act on — wide reference tables (e.g. 8-column data dictionaries) simply
     overflow the content column and force the whole page to scroll
     sideways, dragging the sidebar and topbar off screen. Mirrors the hub
     front-end's `<Table>`, which wraps its `<table>` in
     `<div class="relative w-full overflow-x-auto">`. */
  function wrapTables() {
    var tables = document.querySelectorAll('div.body table.docutils');
    Array.prototype.forEach.call(tables, function (table) {
      var parent = table.parentNode;
      if (parent && parent.classList.contains('gs-table-wrap')) return;
      var wrap = document.createElement('div');
      wrap.className = 'gs-table-wrap';
      /* Only focusable when actually scrollable, so keyboard users don't
         tab through every table on the page. Set in syncScrollability(). */
      wrap.setAttribute('role', 'region');
      wrap.setAttribute('aria-label', 'Table');
      parent.insertBefore(wrap, table);
      wrap.appendChild(table);
    });
    syncScrollability();
  }

  /* A wrapper is only a scroll container — and so only needs to be keyboard
     focusable and announced — when its table genuinely overflows. Re-checked
     on resize because the breakpoint-driven font sizes change table width. */
  function syncScrollability() {
    var wraps = document.querySelectorAll('.gs-table-wrap');
    Array.prototype.forEach.call(wraps, function (wrap) {
      var scrollable = wrap.scrollWidth > wrap.clientWidth + 1;
      if (scrollable) {
        wrap.setAttribute('tabindex', '0');
        wrap.setAttribute('data-scrollable', '');
      } else {
        wrap.removeAttribute('tabindex');
        wrap.removeAttribute('data-scrollable');
      }
      /* The caption is `position: sticky; left: 0` (see geoscape.css) so it
         tracks the container's left edge, but its centring still needs a
         width, and `width: 100%` on a <caption> resolves against the table —
         which may be far wider than the container. Only the container's
         clientWidth centres the title over what's actually on screen. */
      var caption = wrap.querySelector(':scope > table > caption');
      if (caption) {
        /* Only when the table is wider than the container. A table narrower
           than the container centres its caption over itself correctly, and
           forcing the container width there would push the title off to the
           right of its own table. */
        caption.style.width = scrollable ? wrap.clientWidth + 'px' : '';
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var current = readState();
    apply(current);

    wrapTables();
    window.addEventListener('resize', syncScrollability);

    var btn = document.querySelector('.gs-theme-toggle');
    if (btn) {
      btn.addEventListener('click', function () {
        current = next(current);
        writeState(current);
        apply(current);
      });
    }

    var BREAKPOINT = 940;

    function openDrawer() {
      document.body.setAttribute('data-nav-open', '');
      var t = document.querySelector('.gs-nav-toggle');
      if (t) t.setAttribute('aria-expanded', 'true');
      var firstLink = document.querySelector('div.sphinxsidebar a');
      if (firstLink) firstLink.focus();
    }

    function closeDrawer() {
      document.body.removeAttribute('data-nav-open');
      var t = document.querySelector('.gs-nav-toggle');
      if (t) t.setAttribute('aria-expanded', 'false');
    }

    function isOpen() {
      return document.body.hasAttribute('data-nav-open');
    }

    /* Above the breakpoint the same button collapses the desktop sidebar
       rather than opening the drawer — useful on table-heavy pages that want
       the full window. Persisted like the hub's `sidebar_state` cookie so it
       survives navigation between pages. */
    var COLLAPSE_KEY = 'gs-sidebar-collapsed';

    function isCollapsed() {
      return document.body.hasAttribute('data-sidebar-collapsed');
    }

    function setCollapsed(collapsed) {
      if (collapsed) {
        document.body.setAttribute('data-sidebar-collapsed', '');
      } else {
        document.body.removeAttribute('data-sidebar-collapsed');
      }
      var t = document.querySelector('.gs-nav-toggle');
      if (t) {
        /* aria-expanded describes the sidebar, so on desktop it tracks the
           collapse state and on mobile the drawer state. */
        t.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      }
      try { localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0'); } catch (e) {}
      /* Table wrappers just changed width, so re-measure scrollability and
         re-centre the sticky captions. */
      syncScrollability();
    }

    /* Read on demand rather than caching once: setCollapsed() writes this key,
       so a stale copy captured at init would be re-applied by the resize
       handler and clobber the user's actual preference. */
    function storedCollapsed() {
      try { return localStorage.getItem(COLLAPSE_KEY) === '1'; } catch (e) { return false; }
    }

    if (window.innerWidth > BREAKPOINT) {
      /* Sets aria-expanded either way: the markup ships "false" for the mobile
         drawer, but on desktop the sidebar starts visible. */
      setCollapsed(storedCollapsed());
    }

    var navToggle = document.querySelector('.gs-nav-toggle');
    if (navToggle) {
      navToggle.addEventListener('click', function () {
        if (window.innerWidth > BREAKPOINT) {
          setCollapsed(!isCollapsed());
        } else if (isOpen()) {
          closeDrawer();
        } else {
          openDrawer();
        }
      });
    }

    var backdrop = document.querySelector('.gs-backdrop');
    if (backdrop) {
      backdrop.addEventListener('click', closeDrawer);
    }

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) closeDrawer();
    });

    var sidebar = document.querySelector('div.sphinxsidebar');
    if (sidebar) {
      sidebar.addEventListener('click', function (e) {
        var link = e.target.closest && e.target.closest('a');
        if (link && isOpen()) closeDrawer();
      });
    }

    window.addEventListener('resize', function () {
      if (window.innerWidth > BREAKPOINT) {
        if (isOpen()) closeDrawer();
        /* Re-apply the stored collapse when coming back up from mobile. Guarded
           so an ordinary desktop resize isn't a redundant write + reflow. */
        if (isCollapsed() !== storedCollapsed()) setCollapsed(storedCollapsed());
      } else if (isCollapsed()) {
        /* The collapse rules are desktop-only, but the attribute would linger
           and `aria-expanded` would misreport the drawer. Drop it without
           touching the stored preference — hence not setCollapsed(false). */
        document.body.removeAttribute('data-sidebar-collapsed');
        var t = document.querySelector('.gs-nav-toggle');
        if (t) t.setAttribute('aria-expanded', isOpen() ? 'true' : 'false');
      }
    });

    var mql = window.matchMedia('(prefers-color-scheme: dark)');
    var mqlHandler = function () {
      if (current === 'auto') apply(current);
    };
    if (mql.addEventListener) mql.addEventListener('change', mqlHandler);
    else if (mql.addListener) mql.addListener(mqlHandler);
  });
})();
