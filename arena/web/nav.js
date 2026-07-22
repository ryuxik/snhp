/* SNHP arena — the one shared chrome. arena.snhp.dev is the DEMO HOST: the
   product site is snhp.dev, so the bar is deliberately minimal (SNHP → the
   product site, Demos → this host's index) plus a small footer. Fires one
   fire-and-forget analytics beacon.

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

    // 2) the demos index is the only in-host destination, so it is the only
    //    entry that can be "active" (gold).
    var file = (location.pathname.replace(/\/$/, "/index.html").split("/").pop() || "index.html");
    var onIndex = file === "index.html" && !/\/(company|workshop)\//.test(location.pathname);

    // The wordmark IS the link back to the product site (see below), so the
    // list holds only this host's own destination — no duplicate "SNHP".
    var DOORS = [
      { key: "demos", label: "Demos", href: "index.html", active: onIndex }
    ];

    // 3) header
    var nav = document.createElement("nav");
    nav.className = "snhp-nav";
    if (body.getAttribute("data-snhp-nav") === "overlay") nav.className += " snhp-nav--overlay";
    nav.setAttribute("aria-label", "SNHP sections");
    var html = '<a class="snhp-nav__logo" href="https://snhp.dev" rel="noopener"'
      + ' aria-label="SNHP — the product site">SNHP</a>'
      + '<ul class="snhp-nav__list">';
    DOORS.forEach(function (d) {
      html += '<li><a href="' + (d.ext ? d.href : U(d.href)) + '"'
        + (d.ext ? ' rel="noopener"' : "")
        + (d.active ? ' class="is-active" aria-current="page"' : "")
        + '>' + d.label + '</a></li>';
    });
    html += "</ul>";
    nav.innerHTML = html;
    body.insertBefore(nav, body.firstChild);

    // 4) footer — the honesty frame lives here, on every demo. Skipped on
    // fullscreen canvas pages (overlay), where a document-flow footer has
    // nowhere to sit.
    var overlay = body.getAttribute("data-snhp-nav") === "overlay";
    var foot = document.createElement("footer");
    foot.className = "snhp-foot";
    foot.innerHTML =
      '<span class="snhp-foot__arch">Research artifacts. Not products.</span>'
      + '<span class="snhp-foot__links">'
      + '<a href="' + U("index.html") + '">demos</a>'
      + '<a href="https://github.com/ryuxik/snhp" rel="noopener">github</a>'
      + '<a href="https://snhp.dev" rel="noopener">snhp.dev</a>'
      + "</span>";
    if (!overlay) body.appendChild(foot);

    // 5) auto-hide the bar — let it slide away as the reader scrolls into the
    // page and return on scroll-up, scroll-to-top, a hover at the top edge, or
    // keyboard focus. Overlay pages keep a persistent reserved strip, so they
    // (and any page setting data-snhp-nav-autohide="off") opt out.
    if (!overlay && body.getAttribute("data-snhp-nav-autohide") !== "off") {
      setupAutoHide(nav, body);
    }

    // 6) one fire-and-forget pageview beacon (no cookies, no identity)
    try {
      var blob = new Blob([JSON.stringify({ page: location.pathname })],
        { type: "application/json" });
      navigator.sendBeacon("/api/hit", blob);
    } catch (e) { /* static host / no beacon — analytics must never break a page */ }
  }

  // Auto-hide the shared bar. `nav` is the injected .snhp-nav; `body` is
  // document.body. Never called for overlay / opted-out pages (see run()).
  function setupAutoHide(nav, body) {
    var THRESH = 80;        // px scrolled before the bar is allowed to hide
    var EDGE = 16;          // top-edge band (px) that a pointer reveals from
    var LEAVE_DELAY = 400;  // ms grace after the pointer leaves the band
    var scrollShow = true;  // scroll-direction intent: up reveals, down hides
    var overReveal = false; // pointer is resting in the top band / over the bar
    var focusIn = false;    // keyboard focus lives inside the bar
    var lastY = getY(), leaveTimer = null, ticking = false;
    var navH = nav.offsetHeight || 40;

    function getY() {
      return window.pageYOffset || document.documentElement.scrollTop || 0;
    }
    function render() {
      var show = getY() <= THRESH || scrollShow || overReveal || focusIn;
      nav.classList.toggle("is-hidden", !show);
    }
    function clearLeave() { if (leaveTimer) { clearTimeout(leaveTimer); leaveTimer = null; } }
    function reveal() { clearLeave(); if (!overReveal) { overReveal = true; render(); } }
    function scheduleHide() {
      if (!overReveal || leaveTimer) return;
      leaveTimer = setTimeout(function () {
        leaveTimer = null; overReveal = false; render();
      }, LEAVE_DELAY);
    }

    // switch the bar to fixed positioning (see nav.css) and reserve the flow
    // space it vacates with a same-height spacer, so content doesn't jump up.
    nav.classList.add("snhp-nav--autohide");
    var spacer = document.createElement("div");
    spacer.className = "snhp-nav__spacer";
    spacer.setAttribute("aria-hidden", "true");
    body.insertBefore(spacer, nav.nextSibling);

    // keep the spacer matched to the bar's real height. The shared stylesheet
    // loads async, so this first read can be the unstyled (taller) bar — a
    // ResizeObserver re-syncs before paint once CSS/fonts/wrapping settle.
    function syncSpacer() {
      navH = nav.offsetHeight || navH;
      spacer.style.height = navH + "px";
    }
    syncSpacer();
    if (window.ResizeObserver) new ResizeObserver(syncSpacer).observe(nav);
    else { window.addEventListener("load", syncSpacer); setTimeout(syncSpacer, 250); }

    // the literal thin invisible strip at the very top of the viewport
    var zone = document.createElement("div");
    zone.className = "snhp-nav__revealzone";
    zone.setAttribute("aria-hidden", "true");
    body.appendChild(zone);

    // scroll: track direction (rAF-throttled); up reveals, down past the
    // threshold hides, and the top strip (<=THRESH) always pins it visible.
    window.addEventListener("scroll", function () {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(function () {
        var y = getY();
        if (y < lastY - 2) scrollShow = true;                      // up   → reveal
        else if (y > lastY + 2 && y > THRESH) scrollShow = false;  // down → hide
        lastY = y; render(); ticking = false;
      });
    }, { passive: true });

    // pointer at the top edge reveals; leaving the band hides after the grace.
    // Mouse only — touch/pen have no hover, matching native expectations. The
    // band grows to the bar's height once shown so skimming across it holds it.
    window.addEventListener("pointermove", function (e) {
      if (e.pointerType && e.pointerType !== "mouse") return;
      var band = nav.classList.contains("is-hidden") ? EDGE : Math.max(EDGE, navH);
      if (e.clientY >= 0 && e.clientY <= band) reveal();
      else scheduleHide();
    }, { passive: true });

    // the invisible strip's mouseenter is an immediate trigger the instant the
    // cursor crosses the top edge — backs up (and documents) the pointermove.
    zone.addEventListener("mouseenter", reveal);

    // keyboard focus entering the bar reveals it — no pointer required (Tab)
    nav.addEventListener("focusin", function () { focusIn = true; clearLeave(); render(); });
    nav.addEventListener("focusout", function () { focusIn = false; render(); });

    window.addEventListener("resize", syncSpacer, { passive: true });

    render();
  }

  if (document.body) run();
  else document.addEventListener("DOMContentLoaded", run);
})();
