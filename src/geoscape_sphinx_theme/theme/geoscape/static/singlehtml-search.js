/* In-page search for singlehtml builds.
   ==========================================================================

   Kept out of geoscape.js deliberately (same reasoning as image-preview.js):
   that file is theme chrome every page needs, whereas this is one optional
   feature. Both files are only *linked* on singlehtml builds when the
   `singlehtml_search` theme option is on, so an html build never references
   them and a consumer who turns it off pays no parse or execution cost.

   The singlehtml builder produces no search index and no search.html, so
   Sphinx's real search can't run. But the whole corpus is already in the DOM,
   so the natural equivalent is find-in-page: type a term, highlight every match
   in the content, scroll to the first, and offer "Hide Search Matches" to
   clear — mirroring the state the html theme lands in after a search. Enter on
   the same term advances to the next match, which a single long page benefits
   from and which adds no visible chrome.

   Reuses the sidebar box rendered by searchbox.html (form.gs-inpage-search) and
   the `.highlighted` / `.highlight-link` styling already in geoscape.css, so it
   looks identical to the html search with no duplicated CSS.
   ========================================================================== */
(function () {
  'use strict';

  var MARK_CLASS = 'highlighted';

  var form = null;
  var input = null;
  var box = null;          /* the #searchbox <search> element, for the hide link */
  var content = null;      /* div.body — the region we search within */

  var marks = [];          /* current match <span>s, in document order */
  var current = -1;        /* index of the match Enter last scrolled to */
  var lastQuery = '';

  function escapeRegExp(text) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  /* Collect the text nodes inside the content region worth searching. Skips
     script/style and anything already inside a highlight span (there shouldn't
     be any — we clear first — but it keeps the walk defensive). */
  function textNodes() {
    var nodes = [];
    var walker = document.createTreeWalker(
      content,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode: function (node) {
          if (!node.nodeValue || !node.nodeValue.trim()) {
            return NodeFilter.FILTER_REJECT;
          }
          var parent = node.parentNode;
          while (parent && parent !== content) {
            var tag = parent.nodeName;
            if (tag === 'SCRIPT' || tag === 'STYLE') {
              return NodeFilter.FILTER_REJECT;
            }
            if (parent.classList && parent.classList.contains(MARK_CLASS)) {
              return NodeFilter.FILTER_REJECT;
            }
            parent = parent.parentNode;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      },
      false
    );
    var n;
    while ((n = walker.nextNode())) nodes.push(n);
    return nodes;
  }

  /* Wrap every case-insensitive occurrence of `query` in a text node with a
     <span class="highlighted">, returning the spans created. */
  function highlightNode(node, re) {
    var text = node.nodeValue;
    re.lastIndex = 0;
    if (!re.test(text)) return [];

    var frag = document.createDocumentFragment();
    var created = [];
    var lastIndex = 0;
    var match;
    re.lastIndex = 0;
    while ((match = re.exec(text))) {
      if (match.index > lastIndex) {
        frag.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
      }
      var span = document.createElement('span');
      span.className = MARK_CLASS;
      span.textContent = match[0];
      frag.appendChild(span);
      created.push(span);
      lastIndex = match.index + match[0].length;
      /* Guard against a zero-length match looping forever. */
      if (match[0].length === 0) re.lastIndex++;
    }
    if (lastIndex < text.length) {
      frag.appendChild(document.createTextNode(text.slice(lastIndex)));
    }
    node.parentNode.replaceChild(frag, node);
    return created;
  }

  /* Remove the "Hide Search Matches" link if present. */
  function removeHideLink() {
    if (!box) return;
    var link = box.querySelector('.highlight-link');
    if (link && link.parentNode) link.parentNode.removeChild(link);
  }

  /* Undo a previous search: unwrap every highlight span back to plain text and
     merge the split text nodes so the next search sees the original DOM. */
  function clear() {
    for (var i = 0; i < marks.length; i++) {
      var span = marks[i];
      var parent = span.parentNode;
      if (!parent) continue;
      parent.replaceChild(document.createTextNode(span.textContent), span);
      parent.normalize();
    }
    marks = [];
    current = -1;
    removeHideLink();
  }

  var CURRENT_CLASS = 'gs-search-current';

  function scrollToMark(i) {
    if (i < 0 || i >= marks.length) return;
    /* Emphasise the match Enter last landed on, so stepping through a long page
       is visible. Only one match carries the class at a time. */
    for (var j = 0; j < marks.length; j++) marks[j].classList.remove(CURRENT_CLASS);
    marks[i].classList.add(CURRENT_CLASS);
    marks[i].scrollIntoView({ block: 'center', inline: 'nearest' });
  }

  /* Build/refresh the status + hide-affordance line inside the search box,
     reusing the same `.highlight-link` markup Sphinx injects after an html
     search so it inherits the existing styling. */
  function showStatus(count, query) {
    removeHideLink();
    if (!box) return;
    var p = document.createElement('p');
    p.className = 'highlight-link';
    if (count === 0) {
      p.appendChild(document.createTextNode('No matches for “' + query + '”'));
    } else {
      p.appendChild(document.createTextNode(
        count + (count === 1 ? ' match. ' : ' matches. ')
      ));
      var a = document.createElement('a');
      a.href = '#';
      a.textContent = 'Hide Search Matches';
      a.addEventListener('click', function (e) {
        e.preventDefault();
        clear();
        if (input) input.focus();
      });
      p.appendChild(a);
    }
    box.appendChild(p);
  }

  function run(query) {
    clear();
    lastQuery = query;
    if (!query) return;

    var re = new RegExp(escapeRegExp(query), 'gi');
    var nodes = textNodes();
    for (var i = 0; i < nodes.length; i++) {
      var created = highlightNode(nodes[i], re);
      if (created.length) marks = marks.concat(created);
    }

    showStatus(marks.length, query);
    if (marks.length) {
      current = 0;
      scrollToMark(0);
    }
  }

  function onSubmit(e) {
    e.preventDefault();
    var query = (input.value || '').trim();

    /* Re-submitting the same non-empty term steps to the next match rather than
       redoing the whole highlight pass — cheap navigation on one long page. */
    if (query && query === lastQuery && marks.length) {
      current = (current + 1) % marks.length;
      scrollToMark(current);
      return;
    }
    run(query);
  }

  document.addEventListener('DOMContentLoaded', function () {
    form = document.querySelector('form.gs-inpage-search');
    if (!form) return;
    input = form.querySelector('input[name="q"]');
    box = document.getElementById('searchbox');
    content = document.querySelector('div.body') || document.querySelector('div.document');
    if (!input || !content) return;

    form.addEventListener('submit', onSubmit);
    /* Clearing the field (including via the native clear "x") wipes highlights. */
    input.addEventListener('input', function () {
      if (!input.value.trim()) clear();
    });
  });
})();
