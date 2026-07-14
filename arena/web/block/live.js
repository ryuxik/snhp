/* The LIVE layer. The pixel street stays the canned verified-week replay (the
   visual); this file adds the long-running SERVER experiment on top: it
   connects to /block/live (WebSocket; /block/live.json on connect) and renders
   the cumulative honest scoreboard — consumer surplus BIG, merchant margin,
   walk-aways, waste, per-venue up/down INCLUDING the losers — plus a
   "LIVE · day N · seed S · vX" badge with the rerun-it-yourself pointer.

   Honesty bar: every figure in the panel is read off the stream (a fold of
   the server's logged day-records); nothing is computed or invented here.
   Fallback: if the stream is absent (file://, flag off, server down) the
   panel never shows and the canned "replay of a verified week" badge stands. */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  var panel = document.getElementById("live-panel");
  var badge = document.getElementById("badge");
  if (!panel || !badge) return;
  if (location.protocol === "file:") return;          // canned fallback

  var S = { snap: null, ws: null, retryMs: 2000, min: false, userSet: false };
  var mq = window.matchMedia ? window.matchMedia("(max-width: 680px)") : null;
  function minimized() { return S.userSet ? S.min : !!(mq && mq.matches); }
  if (mq && mq.addEventListener)
    mq.addEventListener("change", function () { if (!S.userSet) render(); });
  // ONE delegated listener survives the per-day re-renders
  panel.addEventListener("click", function (e) {
    if (e.target && e.target.closest && e.target.closest(".lv-toggle")) {
      S.min = !minimized(); S.userSet = true; render();
    }
  });

  // ── formatting (display only — the numbers come off the stream) ──────────
  function money(x, sign) {
    var neg = x < 0, v = Math.abs(Math.round(x));
    var s = "$" + v.toLocaleString("en-US");
    return (neg ? "−" : (sign ? "+" : "")) + s;
  }
  function count(x) { return Math.round(x).toLocaleString("en-US"); }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // ── render ────────────────────────────────────────────────────────────────
  function render() {
    var snap = S.snap;
    if (!snap || !snap.live) return;
    var min = minimized();
    var tot = snap.totals.season, life = snap.totals.lifetime;
    var eng = snap.engine || {};
    var ver = "v" + eng.block_version + "·" + (eng.git || "?");
    var rerun = "python3 -m block.live --seed " + snap.seed +
                " --season " + snap.season + " --day D";

    // the badge flips to the live stamp (title keeps the full provenance)
    badge.classList.add("live");
    badge.innerHTML = '<span class="live-dot" aria-hidden="true"></span>' +
      "LIVE · day " + count(snap.day) +
      (snap.season > 0 ? " · season " + snap.season : "") +
      " · seed " + snap.seed + " · " + esc(ver) +
      " · street replay of a verified week";
    badge.title = "The pixel street is the canned verified-week replay (see " +
      "canned-week.json meta.provenance). The LIVE panel numbers are the " +
      "long-running server twin: one sim-day every " +
      (snap.secs_per_day ? Math.round(snap.secs_per_day) + "s" : "interval") +
      ", every day-record logged and reproducible — rerun any day: " +
      rerun;

    // per-venue cumulative margin delta, sorted best→worst — losers included
    var rows = Object.keys(tot.per_venue).map(function (v) {
      return { id: v, dm: tot.per_venue[v].d_margin };
    }).sort(function (a, b) { return b.dm - a.dm; });
    var venueHtml = rows.map(function (r) {
      var up = r.dm >= 0;
      return '<li class="lv-venue ' + (up ? "up" : "down") + '">' +
        '<span class="lv-vname">' + esc(r.id) + "</span>" +
        '<span class="lv-varrow" aria-hidden="true">' + (up ? "▲" : "▼") + "</span>" +
        '<span class="lv-vamt">' + money(r.dm, true) + "</span></li>";
    }).join("");

    var lifeLine = (life.days > tot.days)
      ? '<div class="lv-life">lifetime ' + count(life.days) + " days · " +
        "shoppers " + money(life.d_cs, true) + " · merchants " +
        money(life.d_margin, true) + "</div>"
      : "";

    panel.innerHTML =
      '<div class="lv-head">' +
        '<span class="live-dot" aria-hidden="true"></span>' +
        '<span class="lv-title">LIVE EXPERIMENT</span>' +
        '<span class="lv-day" aria-live="polite">day ' + count(snap.day) +
          (snap.season > 0 ? " · s" + snap.season : "") + "</span>" +
        '<button class="lv-toggle" aria-expanded="' + !min +
          '" aria-controls="lv-body" title="collapse / expand">' +
          (min ? "+" : "−") + "</button>" +
      "</div>" +
      '<div class="lv-body" id="lv-body"' + (min ? " hidden" : "") + ">" +
        '<div class="lv-note">running on the server now — the street ' +
          "below is a replay; these numbers are the live twin</div>" +
        '<div class="lv-big teal"><span class="lv-lab">consumer surplus kept' +
          "</span><b>" + money(tot.d_cs, true) + "</b></div>" +
        '<div class="lv-big warm"><span class="lv-lab">merchants earned' +
          "</span><b>" + money(tot.d_margin, true) + "</b></div>" +
        '<div class="lv-pair"><span class="lv-lab">walk-aways</span>' +
          "<span>sticker <b>" + count(tot.walkaways.sticker) +
          "</b> · snhp <b>" + count(tot.walkaways.snhp) + "</b></span></div>" +
        '<div class="lv-pair"><span class="lv-lab">waste</span>' +
          "<span>sticker <b>" + money(tot.waste.sticker) +
          "</b> · snhp <b>" + money(tot.waste.snhp) + "</b></span></div>" +
        '<ul class="lv-venues" aria-label="per-venue cumulative margin delta, ' +
          'snhp minus sticker">' + venueHtml + "</ul>" +
        lifeLine +
        '<div class="lv-foot" title="' + esc(snap.reproduce || rerun) + '">' +
          "seed " + snap.seed + " · " + esc(ver) +
          " · rerun: <code>" + esc(rerun) + "</code></div>" +
      "</div>";
    panel.classList.remove("hidden");
  }

  function pulse() {
    panel.classList.remove("pulse");
    void panel.offsetWidth;                    // restart the animation
    panel.classList.add("pulse");
  }

  // ── the stream ────────────────────────────────────────────────────────────
  function refetch() {
    fetch("/block/live.json").then(function (r) {
      if (!r.ok) throw new Error("http " + r.status);
      return r.json();
    }).then(function (snap) {
      if (snap && snap.schema === "block.live.v1") { S.snap = snap; render(); }
    }).catch(function () { /* keep the last snapshot */ });
  }

  function connect() {
    var proto = location.protocol === "https:" ? "wss://" : "ws://";
    var ws;
    try { ws = new WebSocket(proto + location.host + "/block/live"); }
    catch (e) { return; }
    S.ws = ws;
    ws.onmessage = function (m) {
      var ev;
      try { ev = JSON.parse(m.data); } catch (e) { return; }
      if (ev.type === "block.snapshot" && ev.schema === "block.live.v1") {
        S.snap = ev; S.retryMs = 2000; render();
      } else if (ev.type === "block.day") {
        // the server swaps its snapshot before publishing the day-record, so
        // a refetch is the fold — no client-side arithmetic on the numbers
        pulse(); refetch();
      }
    };
    ws.onclose = function () {
      S.ws = null;
      setTimeout(connect, S.retryMs);
      S.retryMs = Math.min(S.retryMs * 2, 30000);
    };
  }

  // go live only if the endpoint exists (flag on); otherwise stay canned
  fetch("/block/live.json").then(function (r) {
    if (!r.ok) throw new Error("http " + r.status);
    return r.json();
  }).then(function (snap) {
    if (!snap || snap.schema !== "block.live.v1") return;
    S.snap = snap;                             // phones start collapsed (mq)
    render();
    connect();
  }).catch(function () { /* canned fallback: badge already says replay */ });
})();
