/* Collapsible content sections.
   ==========================================================================

   Kept out of geoscape.js deliberately (same reasoning as image-preview.js):
   that file is theme chrome every page needs, whereas this is one optional
   feature. Both files are only *linked* when the `collapsible_sections` theme
   option is on, so a consumer who turns it off pays no parse or execution cost.
   (Sphinx copies every file in a theme's static/ directory regardless, so
   they're still present but inert.)

   "Automatic" (Route 1): the theme makes each top-level subsection collapsible
   itself, so authors write nothing. Only h2 sections get a toggle — the h1 page
   title and deeper h3+ subsections are left alone; collapsing an h2 hides all of
   its body, including any nested h3 content. Everything starts expanded.

   Accessibility: the h2 stays an <h2> (heading semantics preserved for screen
   reader navigation); the interactive control is a real <button> nested inside
   it, which brings keyboard (Enter/Space) and focus for free. The heading's ¶
   permalink is left outside the button so it still navigates.
   ========================================================================== */
(function () {
  'use strict';

  var TOGGLE_CLASS = 'gs-section-toggle';
  var SECTION_CLASS = 'gs-collapsible-section';
  var COLLAPSED_CLASS = 'gs-collapsed';

  function makeCollapsible(heading) {
    var section = heading.parentElement;
    if (!section) return;
    /* Idempotent: if we (or a re-run) already wrapped this heading, skip. */
    if (heading.querySelector('.' + TOGGLE_CLASS)) return;

    var button = document.createElement('button');
    button.type = 'button';
    button.className = TOGGLE_CLASS;
    button.setAttribute('aria-expanded', 'true');

    /* Move the heading's content into the button, but leave a trailing
       `a.headerlink` (the ¶ permalink) in the heading after the button so it
       still links to the section instead of toggling it. */
    var nodes = [];
    for (var i = 0; i < heading.childNodes.length; i++) {
      var node = heading.childNodes[i];
      if (
        node.nodeType === 1 &&
        node.tagName === 'A' &&
        node.classList.contains('headerlink')
      ) {
        continue;
      }
      nodes.push(node);
    }
    for (var j = 0; j < nodes.length; j++) {
      button.appendChild(nodes[j]);
    }
    heading.insertBefore(button, heading.firstChild);

    section.classList.add(SECTION_CLASS);

    button.addEventListener('click', function () {
      var collapsed = section.classList.toggle(COLLAPSED_CLASS);
      button.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    });
  }

  function init() {
    var content = document.querySelector('div.body');
    if (!content) return;
    /* A top-level subsection is a <section> whose first element child is an h2.
       (Docutils always emits the title as the section's first child.) */
    var headings = content.querySelectorAll('section > h2:first-child');
    for (var i = 0; i < headings.length; i++) {
      makeCollapsible(headings[i]);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
