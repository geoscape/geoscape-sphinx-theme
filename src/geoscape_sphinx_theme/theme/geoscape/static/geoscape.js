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

  document.addEventListener('DOMContentLoaded', function () {
    var current = readState();
    apply(current);

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

    var navToggle = document.querySelector('.gs-nav-toggle');
    if (navToggle) {
      navToggle.addEventListener('click', function () {
        if (isOpen()) closeDrawer(); else openDrawer();
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
      if (window.innerWidth > BREAKPOINT && isOpen()) closeDrawer();
    });

    var mql = window.matchMedia('(prefers-color-scheme: dark)');
    var mqlHandler = function () {
      if (current === 'auto') apply(current);
    };
    if (mql.addEventListener) mql.addEventListener('change', mqlHandler);
    else if (mql.addListener) mql.addListener(mqlHandler);
  });
})();
