/* SNHP arena — the one shared chrome. Injects a consistent header (wordmark +
   Watch / Read / Build) and footer (Archive · science · github · snhp.dev) into
   every non-archive page, and fires one fire-and-forget analytics beacon.

   Dependency-free. Include ONCE per page, synchronously (no defer/async), so
   document.currentScript resolves — that lets a subdir page (company/, workshop/)
   include ../nav.js and still get correct links: every target is resolved
   relative to THIS file's URL (always arena/web/nav.js), so paths work at any depth.

   Fullscreen canvas pages (workshop) set <body data-snhp-nav="overlay"> to float
   the header above their fixed stage instead of taking layout space. */
(function () {
  "use strict";
  var ME = document.currentScript;
  if (!ME) return;                                  // needs sync execution
  var U = function (p) { return new URL(p, ME.src).href; };   // relative to nav.js

  function run() {
    // never inject chrome (or count a view) inside an embed — e.g. the home
    // page's hero iframe of swarm.html — so the frame stays clean and honest.
    try { if (window.self !== window.top) return; } catch (e) { return; }
    var body = document.body;
    if (!body || body.querySelector(".snhp-nav")) return;     // idempotent

    // 1) ensure the shared stylesheet is present (resolved next to nav.js)
    var cssHref = U("nav.css");
    var haveCss = Array.prototype.some.call(
      document.styleSheets, function (s) { return s.href === cssHref; });
    if (!haveCss && !document.querySelector('link[data-snhp-nav-css]')) {
      var link = document.createElement("link");
      link.rel = "stylesheet"; link.href = cssHref;
      link.setAttribute("data-snhp-nav-css", "");
      document.head.appendChild(link);
    }

    // 2) which door is the current page under? (for the gold active state)
    var file = (location.pathname.replace(/\/$/, "/index.html").split("/").pop() || "index.html");
    var path = location.pathname;
    var door =
      /company|workshop|swarm|watch/.test(file + path) ? "watch" :
      /science|read/.test(file) ? "read" :
      /benchmark|submit|build/.test(file) ? "build" : "";

    var DOORS = [
      { key: "watch", label: "Watch", href: "watch.html" },
      { key: "read",  label: "Read",  href: "read.html" },
      { key: "build", label: "Build", href: "build.html" }
    ];

    // 3) header
    var nav = document.createElement("nav");
    nav.className = "snhp-nav";
    if (body.getAttribute("data-snhp-nav") === "overlay") nav.className += " snhp-nav--overlay";
    nav.setAttribute("aria-label", "SNHP sections");
    var html = '<a class="snhp-nav__logo" href="' + U("index.html") + '" aria-label="SNHP — home">SNHP</a>'
      + '<ul class="snhp-nav__list">';
    DOORS.forEach(function (d) {
      html += '<li><a href="' + U(d.href) + '"' + (door === d.key
        ? ' class="is-active" aria-current="page"' : "") + '>' + d.label + '</a></li>';
    });
    html += "</ul>";
    nav.innerHTML = html;
    body.insertBefore(nav, body.firstChild);

    // 4) footer — Archive is muted and lives here only. Skipped on fullscreen
    // canvas pages (overlay), where a document-flow footer has nowhere to sit.
    var overlay = body.getAttribute("data-snhp-nav") === "overlay";
    var foot = document.createElement("footer");
    foot.className = "snhp-foot";
    foot.innerHTML =
      '<a class="snhp-foot__arch" href="' + U("archive.html") + '">Archive — earlier experiments</a>'
      + '<span class="snhp-foot__links">'
      + '<a href="' + U("science.html") + '">science</a>'
      + '<a href="https://github.com/ryuxik/snhp" rel="noopener">github</a>'
      + '<a href="https://snhp.dev" rel="noopener">snhp.dev</a>'
      + "</span>";
    if (!overlay) body.appendChild(foot);

    // 5) one fire-and-forget pageview beacon (no cookies, no identity)
    try {
      var blob = new Blob([JSON.stringify({ page: location.pathname })],
        { type: "application/json" });
      navigator.sendBeacon("/api/hit", blob);
    } catch (e) { /* static host / no beacon — analytics must never break a page */ }
  }

  if (document.body) run();
  else document.addEventListener("DOMContentLoaded", run);
})();
