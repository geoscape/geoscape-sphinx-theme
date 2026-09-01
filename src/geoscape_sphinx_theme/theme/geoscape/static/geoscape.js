(function () {
  'use strict';

  var STORAGE_KEY = 'gs-theme';
  var STATES = ['light', 'dark', 'auto'];

  /* Captured at script-eval time, before sphinx_highlight.js's DOMContentLoaded
     handler strips `?highlight=` from the URL and clears sphinx_highlight_terms
     from localStorage. Used to pre-fill the sidebar search input so the term a
     reader searched for stays visible in the box (see fillSearchTerm below).
     `highlight` is set when landing on a doc page from a result; `q` is the
     query on the search results page itself. */
  var searchTerm = '';
  try {
    var _params = new URLSearchParams(window.location.search);
    searchTerm = _params.get('highlight') ||
                 _params.get('q') ||
                 localStorage.getItem('sphinx_highlight_terms') || '';
  } catch (e) {}

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
    var root = document.querySelector('.gs-theme');
    if (root) {
      /* Trigger shows only the selected mode's icon. These are SVG elements,
         which don't support the HTML `hidden` attribute (it's an HTMLElement
         property and doesn't reflect on SVG), so toggle a class instead. */
      var icons = root.querySelectorAll('.gs-theme__icon');
      Array.prototype.forEach.call(icons, function (ic) {
        var active = ic.getAttribute('data-theme-icon') === state;
        ic.classList.toggle('gs-theme__icon--hidden', !active);
      });
      /* Keep the trigger's label/title in sync with the current mode so the
         click-to-cycle control is discoverable (announces mode + next action). */
      var trigger = root.querySelector('.gs-theme__trigger');
      if (trigger) {
        var LABELS = { light: 'Light', dark: 'Dark', auto: 'System' };
        var next = STATES[(STATES.indexOf(state) + 1) % STATES.length];
        var msg = 'Colour theme: ' + LABELS[state] + ' (click for ' + LABELS[next] + ')';
        trigger.setAttribute('aria-label', msg);
        trigger.setAttribute('title', msg);
      }
    }
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

  /* Multi-doc singlehtml stitches chapters onto one page and emits local-ToC
     section links as `#document-<chapter>#<section>` — a double fragment the
     browser can't resolve. The section keeps its own id on the merged page, so
     collapse `#a#b` -> `#b`. Single-hash hrefs (html builds, top-level entries)
     are untouched. */
  function fixLocalTocAnchors() {
    var links = document.querySelectorAll('.gs-nav__local a[href]');
    Array.prototype.forEach.call(links, function (a) {
      var href = a.getAttribute('href');
      if (href.indexOf('#') === -1) return;
      var last = href.lastIndexOf('#');
      if (last > 0) a.setAttribute('href', href.slice(last));
    });
  }

  /* In multi-doc singlehtml the local ToC's top level is the whole chapter
     list (already in the sidebar) with every chapter's sections at once. Scope
     it to the chapter currently at the top of the viewport (scrollspy) so it
     reads as a per-page contents list. Gated on all top-level entries being
     `#document-<chapter>` anchors, so html/single-doc builds are a no-op; the
     `gs-local-scoped` class means a no-JS build keeps the full list. */
  function scopeLocalToc() {
    var local = document.querySelector('.gs-nav__local');
    if (!local) return;
    var topList = local.querySelector(':scope > ul');
    if (!topList) return;

    var chapters = Array.prototype.slice.call(topList.children)
      .filter(function (li) { return li.tagName === 'LI'; })
      .map(function (li) {
        var a = li.querySelector(':scope > a');
        var m = a && /^#(document-[^#]+)$/.exec(a.getAttribute('href') || '');
        return m ? { li: li, target: document.getElementById(m[1]) } : null;
      });
    /* Not the multi-doc form unless every top-level entry is a chapter. */
    if (!chapters.length || chapters.indexOf(null) !== -1) return;

    local.classList.add('gs-local-scoped');
    var nav = local.closest('.gs-nav');

    /* Chapter whose heading has scrolled up past the line below the sticky
       topbar; null while still above the first chapter (e.g. the page top /
       master-doc landing), so no chapter's sections show there. */
    function currentByScroll() {
      var offset = 120;
      var active = null;
      chapters.forEach(function (c) {
        if (c.target && c.target.getBoundingClientRect().top - offset <= 0) active = c;
      });
      return active;
    }

    function chapterContaining(el) {
      for (var i = 0; i < chapters.length; i++) {
        if (chapters[i].target && chapters[i].target.contains(el)) return chapters[i];
      }
      return null;
    }

    function render(active) {
      chapters.forEach(function (c) {
        c.li.classList.toggle('gs-toc-active', c === active);
      });
      /* No active chapter, or one with no sections: hide the panel rather than
         show a bare heading. */
      if (nav) nav.classList.toggle('gs-local-empty', !active || !active.li.querySelector(':scope > ul'));
    }

    /* While a click/hash jump animates (smooth scroll), pin the panel to its
       destination chapter so intermediate chapters don't flash past. */
    var locked = null;
    var lockTimer = null;
    function update() { render(locked || currentByScroll()); }
    function lockTo(chapter) {
      locked = chapter;
      render(chapter);
      if (lockTimer) clearTimeout(lockTimer);
      lockTimer = setTimeout(function () { locked = null; update(); }, 700);
    }

    document.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('a[href^="#"]');
      if (!a) return;
      var id = a.getAttribute('href').slice(1);
      lockTo(id ? chapterContaining(document.getElementById(id)) : null);
    });

    update();
    /* Called directly (not via rAF): a backgrounded tab pauses rAF, which could
       wedge a throttle lock; the few rect reads here are cheap enough. */
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    window.addEventListener('hashchange', update);
  }

  /* Keep the searched term in the sidebar box after a search, and clear it only
     when the reader clicks "Hide Search Matches" (which Sphinx injects as
     `<p class="highlight-link">` inside #searchbox and which also unhighlights
     the page via SphinxHighlight.hideSearchWords). */
  function fillSearchTerm() {
    var input = document.querySelector('#searchbox input[name="q"]');
    if (input && searchTerm && !input.value) {
      input.value = searchTerm;
    }
    /* Delegated: the link is added dynamically after the highlight pass. The
       javascript: href still runs hideSearchWords; this just also empties the
       input so the box returns to its resting placeholder state. */
    document.addEventListener('click', function (e) {
      var link = e.target.closest && e.target.closest('.highlight-link a');
      if (!link) return;
      var box = document.querySelector('#searchbox input[name="q"]');
      if (box) box.value = '';
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var current = readState();
    apply(current);

    fillSearchTerm();
    fixLocalTocAnchors();
    scopeLocalToc();
    wrapTables();
    window.addEventListener('resize', syncScrollability);

    var themeRoot = document.querySelector('.gs-theme');
    if (themeRoot) {
      var trigger = themeRoot.querySelector('.gs-theme__trigger');
      /* Click cycles Light -> Dark -> System -> Light. */
      trigger.addEventListener('click', function () {
        current = STATES[(STATES.indexOf(current) + 1) % STATES.length];
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
