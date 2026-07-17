/* SNHP arena — the archived-experiment banner. A one-line strip pinned to the
   top of pages kept only for the record. Self-contained (its own styles), floats
   above fullscreen canvas pages, and leaves the page's own content untouched.
   Include synchronously on each archived page: <script src="archived.js"></script> */
(function () {
  "use strict";
  function run() {
    if (!document.body || document.getElementById("snhp-arch-bar")) return;
    var css = document.createElement("style");
    css.textContent =
      "#snhp-arch-bar{position:fixed;top:0;left:0;right:0;z-index:2147483600;" +
      "box-sizing:border-box;display:flex;align-items:center;justify-content:center;gap:8px;" +
      "padding:6px 12px;background:rgba(11,9,22,.92);color:#b9b3cf;" +
      "-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);" +
      "border-bottom:1px solid rgba(167,139,250,.28);" +
      "font:12px/1.3 ui-monospace,'SF Mono',Menlo,monospace;letter-spacing:.03em;" +
      "box-shadow:0 4px 16px rgba(0,0,0,.4)}" +
      "#snhp-arch-bar b{color:#d8d3ea;font-weight:600}" +
      "#snhp-arch-bar a{color:#ffe08a;text-decoration:none;font-weight:700}" +
      "#snhp-arch-bar a:hover{text-decoration:underline}";
    document.head.appendChild(css);
    var bar = document.createElement("div");
    bar.id = "snhp-arch-bar";
    bar.innerHTML = "<b>archived experiment</b> — current site at <a href=\"/\">snhp arena ›</a>";
    document.body.insertBefore(bar, document.body.firstChild);
  }
  if (document.body) run();
  else document.addEventListener("DOMContentLoaded", run);
})();
