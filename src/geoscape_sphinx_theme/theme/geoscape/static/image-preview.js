/* Image preview (lightbox) for content images.
   ==========================================================================

   Kept out of geoscape.js deliberately: that file is theme chrome every page
   needs (theme toggle, sidebar drawer, table wrapping), whereas this is one
   optional feature. Both files are only *linked* when the
   `show_image_preview` theme option is on, so a consumer who turns it off pays
   no parse or execution cost. (Sphinx copies every file in a theme's static/
   directory regardless, so they're still present but inert.)

   Handles the three markup shapes Sphinx emits for an image:
     - `<a class="image-reference"><img></a>` — a scaled image, where docutils
       links to the full-size file. The anchor's navigation is suppressed so
       the click opens the overlay instead of leaving the page.
     - a bare `<img>` (raw HTML blocks, e.g. appendix D's extent map).
     - `<div class="graphviz"><img></div>` — rendered diagrams, which benefit
       most from zooming.
   ========================================================================== */
(function () {
  'use strict';

  var MIN_ZOOM = 0.25;
  var MAX_ZOOM = 8;
  var ZOOM_STEP = 1.25;

  /* Built on first use rather than at load: most pages have no images, and an
     unused overlay in every document is a needless node + focus trap risk. */
  var overlay = null;
  var els = {};
  var state = { zoom: 1, x: 0, y: 0, src: '', name: '' };
  var lastFocus = null;

  var ICONS = {
    /* lucide: zoom-in, zoom-out, rotate-ccw, download, x */
    zoomIn: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M11 8v6"/><path d="M8 11h6"/>',
    zoomOut: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M8 11h6"/>',
    reset: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
    close: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>'
  };

  /* `alt` is not always prose. The graphviz extension puts the whole DOT source
     in it, so an unfiltered caption read as a wall of code ("strict digraph {
     graph [fontname = ...").  Detect that rather than trusting alt blindly. */
  function looksLikeCode(text) {
    return (
      /[{};]|=&quot;|\bdigraph\b|\bgraph\s*\[/.test(text) ||
      text.indexOf('\n') !== -1
    );
  }

  /* Best available human title, in descending order of trustworthiness:
       1. a real caption — <figcaption>, or docutils' `p.caption`
       2. `alt`, when it reads as prose
       3. the nearest preceding heading, which is what a reader would call the
          diagram anyway ("8.2. Maintenance process")
       4. the filename — useless for graphviz (a content hash), so last. */
  function titleFor(img) {
    var figure = img.closest('figure, div.figure');
    if (figure) {
      var cap = figure.querySelector('figcaption, p.caption');
      if (cap && cap.textContent.trim()) return cap.textContent.trim();
    }

    var alt = (img.getAttribute('alt') || '').trim();
    if (alt && !looksLikeCode(alt)) return alt;

    /* Walk backwards through the flattened document order to the last heading
       above this image. `previousElementSibling` alone isn't enough: the image
       is usually nested a level or two deeper than the heading. */
    var node = img.closest('section, div.section') || img.parentElement;
    while (node) {
      var heading = node.querySelector('h1, h2, h3, h4, h5, h6');
      if (heading) {
        /* Strip the trailing ¶ that Sphinx's headerlink contributes. */
        var text = heading.textContent.replace(/¶/g, '').trim();
        if (text) return text;
      }
      node = node.parentElement && node.parentElement.closest('section, div.section');
    }

    return '';
  }

  function icon(name) {
    return '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" ' +
      'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      ICONS[name] + '</svg>';
  }

  function button(action, label, iconName) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'gs-lightbox__btn';
    b.setAttribute('data-action', action);
    b.setAttribute('aria-label', label);
    b.setAttribute('title', label);
    b.innerHTML = icon(iconName);
    return b;
  }

  function build() {
    overlay = document.createElement('div');
    overlay.className = 'gs-lightbox';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Image preview');
    overlay.hidden = true;

    var bar = document.createElement('div');
    bar.className = 'gs-lightbox__toolbar';

    els.caption = document.createElement('p');
    els.caption.className = 'gs-lightbox__caption';
    bar.appendChild(els.caption);

    var actions = document.createElement('div');
    actions.className = 'gs-lightbox__actions';
    els.zoomOut = button('zoom-out', 'Zoom out', 'zoomOut');
    els.zoomIn = button('zoom-in', 'Zoom in', 'zoomIn');
    els.level = document.createElement('span');
    els.level.className = 'gs-lightbox__level';
    /* Announced politely so the zoom percentage isn't silent to screen
       readers, but doesn't interrupt on every wheel tick. */
    els.level.setAttribute('aria-live', 'polite');
    actions.appendChild(els.zoomOut);
    actions.appendChild(els.level);
    actions.appendChild(els.zoomIn);
    actions.appendChild(button('reset', 'Reset zoom', 'reset'));
    actions.appendChild(button('download', 'Download image', 'download'));
    actions.appendChild(button('close', 'Close preview (Esc)', 'close'));
    bar.appendChild(actions);

    els.stage = document.createElement('div');
    els.stage.className = 'gs-lightbox__stage';
    els.img = document.createElement('img');
    els.img.className = 'gs-lightbox__img';
    els.img.alt = '';
    els.stage.appendChild(els.img);

    overlay.appendChild(bar);
    overlay.appendChild(els.stage);
    document.body.appendChild(overlay);

    overlay.addEventListener('click', onOverlayClick);
    els.stage.addEventListener('wheel', onWheel, { passive: false });
    els.stage.addEventListener('pointerdown', onPointerDown);
    els.img.addEventListener('dblclick', function () {
      /* Double-click toggles between fit and 2x — the conventional shortcut,
         and quicker than hunting for the toolbar on a large diagram. */
      setZoom(state.zoom > 1 ? 1 : 2);
    });
  }

  function render() {
    var z = state.zoom;
    els.img.style.transform =
      'translate(' + state.x + 'px, ' + state.y + 'px) scale(' + z + ')';
    els.level.textContent = Math.round(z * 100) + '%';
    /* Panning only means anything once the image overflows the stage. */
    els.stage.setAttribute('data-pannable', z > 1 ? 'true' : 'false');
    els.zoomIn.disabled = z >= MAX_ZOOM;
    els.zoomOut.disabled = z <= MIN_ZOOM;
  }

  function setZoom(z) {
    state.zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
    if (state.zoom === 1) {
      /* Drop any pan when returning to fit, otherwise the image can sit
         off-centre with no visual cue that it's been dragged. */
      state.x = 0;
      state.y = 0;
    }
    render();
  }

  function open(img, trigger) {
    if (!overlay) build();
    /* Fall back to the trigger when nothing was focused: a mouse click leaves
       activeElement as <body>, and `body.focus()` is a no-op — so on close,
       focus would be stranded on a button inside the now-hidden overlay. */
    var active = document.activeElement;
    lastFocus = active && active !== document.body ? active : trigger || img;
    /* currentSrc resolves srcset/density variants; src is the fallback. Prefer
       the anchor's href when present — for a scaled image that's the
       full-resolution original, which is the whole point of zooming. */
    var link = img.closest('a.image-reference, a.reference.internal');
    state.src = (link && link.getAttribute('href')) || img.currentSrc || img.src;
    state.name = state.src.split('/').pop().split('?')[0] || 'image';
    els.img.src = state.src;
    var title = titleFor(img);
    els.img.alt = title;
    els.caption.textContent = title || state.name;
    state.zoom = 1;
    state.x = 0;
    state.y = 0;
    overlay.hidden = false;
    document.body.setAttribute('data-lightbox-open', '');
    render();
    /* Focus the close button: it's the escape hatch, and it anchors the
       keyboard trap below. */
    overlay.querySelector('[data-action="close"]').focus();
  }

  function close() {
    if (!overlay || overlay.hidden) return;
    overlay.hidden = true;
    document.body.removeAttribute('data-lightbox-open');
    /* Release the decoded bitmap — appendix diagrams are large. */
    els.img.removeAttribute('src');
    /* Guard isConnected: the trigger could have been removed while open. */
    if (lastFocus && lastFocus.isConnected && lastFocus.focus) lastFocus.focus();
    lastFocus = null;
  }

  function download() {
    var a = document.createElement('a');
    a.href = state.src;
    /* Same-origin (Sphinx copies images into _images/), so `download` is
       honoured and the file saves under its own name rather than navigating. */
    a.download = state.name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function onOverlayClick(e) {
    var btn = e.target.closest('[data-action]');
    if (btn) {
      var action = btn.getAttribute('data-action');
      if (action === 'zoom-in') setZoom(state.zoom * ZOOM_STEP);
      else if (action === 'zoom-out') setZoom(state.zoom / ZOOM_STEP);
      else if (action === 'reset') setZoom(1);
      else if (action === 'download') download();
      else if (action === 'close') close();
      return;
    }
    /* Backdrop dismiss: the stage itself, but not the image on it — otherwise
       every click while panning would close the preview. */
    if (e.target === els.stage || e.target === overlay) {
      close();
      return;
    }
    /* Click on the image zooms in, the conventional lightbox action. Skipped
       once zoomed, where a click is the start of a pan (and where the image
       already fills the stage, so a stray zoom would be disorienting). */
    if (e.target === els.img && state.zoom <= 1) setZoom(state.zoom * ZOOM_STEP);
  }

  function onWheel(e) {
    e.preventDefault();
    setZoom(state.zoom * (e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP));
  }

  function onPointerDown(e) {
    if (state.zoom <= 1 || e.button !== 0) return;
    e.preventDefault();
    var startX = e.clientX - state.x;
    var startY = e.clientY - state.y;
    els.stage.setAttribute('data-panning', '');

    function move(ev) {
      state.x = ev.clientX - startX;
      state.y = ev.clientY - startY;
      render();
    }

    function up() {
      els.stage.removeAttribute('data-panning');
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    }

    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  }

  function isOpen() {
    return overlay && !overlay.hidden;
  }

  document.addEventListener('keydown', function (e) {
    if (!isOpen()) return;
    if (e.key === 'Escape') {
      close();
    } else if (e.key === '+' || e.key === '=') {
      setZoom(state.zoom * ZOOM_STEP);
    } else if (e.key === '-' || e.key === '_') {
      setZoom(state.zoom / ZOOM_STEP);
    } else if (e.key === '0') {
      setZoom(1);
    } else if (e.key === 'Tab') {
      /* Minimal focus trap. The overlay's only focusable children are its
         toolbar buttons, so cycling within them is enough — no need for a
         general tabbable-node query. */
      var items = Array.prototype.filter.call(
        overlay.querySelectorAll('.gs-lightbox__btn'),
        function (b) { return !b.disabled; }
      );
      if (!items.length) return;
      var i = items.indexOf(document.activeElement);
      e.preventDefault();
      var nextIndex = e.shiftKey ? i - 1 : i + 1;
      items[(nextIndex + items.length) % items.length].focus();
    }
  });

  document.addEventListener('DOMContentLoaded', function () {
    var images = document.querySelectorAll(
      'div.body img:not(.gs-lightbox__img):not(.no-lightbox)'
    );
    if (!images.length) return;

    Array.prototype.forEach.call(images, function (img) {
      img.classList.add('gs-zoomable');
      /* The <img> itself isn't focusable, so expose the affordance on the
         wrapping anchor where there is one; otherwise make the image a button
         in its own right so it's reachable without a pointer. */
      var link = img.closest('a.image-reference, a.reference.internal');
      var trigger = link || img;
      if (!link) {
        trigger.setAttribute('tabindex', '0');
        trigger.setAttribute('role', 'button');
      }
      /* titleFor(), not img.alt — otherwise a screen reader announces a whole
         graphviz source dump before the words "open image preview". */
      var title = titleFor(img);
      trigger.setAttribute(
        'aria-label',
        (title ? title + ' — ' : '') + 'open image preview'
      );
      trigger.addEventListener('click', function (e) {
        /* Suppress the anchor's navigation to the raw _images/ file. */
        e.preventDefault();
        open(img, trigger);
      });
      trigger.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          open(img, trigger);
        }
      });
    });
  });
})();
