/* Irreconcilable Agents — cinematic trace player.
 *
 * This file renders NOTHING it invented. Every number, count, band, draft,
 * verdict and hash on screen is read from the loaded trace JSON (real engine
 * output — a bundled preset, or a live filing from the divorce API). The
 * clerk speaks only fixed templates keyed to real event types; template
 * VARIANTS rotate deterministically (question index, settle count, draft
 * index), so the same trace produces the same lines on every replay.
 * No Math.random. No fabricated fallbacks: a missing field is a plain error.
 */
'use strict';

(() => {

  /* ------------------------------------------------------------------ *
   *  constants & tiny utils
   * ------------------------------------------------------------------ */

  const PRESETS = {
    bloodbath:    { file: 'trace-bloodbath.json',    label: 'The Bloodbath',        sub: 'Two people, one dog, no brakes.' },
    spreadsheets: { file: 'trace-spreadsheets.json', label: 'The Two Spreadsheets', sub: 'A divorce with itemized receipts.' },
    nodecree:     { file: 'trace-nodecree.json',     label: 'NO DECREE',            sub: 'Some filings never clear.' },
  };

  const ASSET_ORDER = ['dog', 'lake_weeks', 'wallet', 'vinyl', 'espresso', 'wildcard'];
  const BAND_ASSETS = ['dog', 'lake_weeks', 'vinyl', 'espresso', 'wildcard'];
  const FIXED_NAMES = {
    dog: 'the dog \u{1F415}',
    lake_weeks: 'the lake-house weeks',
    wallet: 'the joint wallet',
    vinyl: 'the vinyl collection',
    espresso: 'the espresso machine',
  };
  const HILL_RATIO = 2.5;           // HILL? chip: p50 > 2.5x its own step-0 p50

  // Act I pacing (ms at 1x). ~4.5 exchanges/sec, with real holds at milestones.
  const TICK_MS = 220;              // one exchange line
  const TICK_SETTLE_MS = 420;       // the ✓ settled line
  const TICK_QUIP_MS = 1200;        // clerk quip after a settle (the 1.2s hold)
  const TICK_STALL_MS = 650;        // a repeated-offer line (broken record)
  const TICK_NOTE_MS = 1400;        // clerk note on the third identical offer

  // Live mode. Same-origin deploys set this to '' (the API mounts /v1/divorce/*).
  const API_BASE = 'http://localhost:8203';

  // Playback speed multiplier: 0.5x / 1x / 2x. Scales every beat duration.
  let speedVal = 1;
  const speed = () => speedVal;

  const REDUCED = window.matchMedia
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const $ = (sel) => document.querySelector(sel);

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function fmtMoney(n) { return '$' + Math.round(n).toLocaleString('en-US'); }

  function fmtPrice(n) {
    // Display rounding only — the trace stays the source of truth; a clerk
    // asking about "$536,685.31" is noise, not honesty.
    return fmtMoney(n);
  }

  function fmtCompact(n) {
    if (n >= 1e6) return '$' + (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e4) return '$' + Math.round(n / 1e3) + 'k';
    return fmtMoney(n);
  }

  function pct(x) { return Math.round(x * 100); }

  function shortSeal(s) { return String(s).replace(/^sha256:/, '').slice(0, 10); }

  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  function titleCaseLabel(s) {
    return s.split(' ').map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w)).join(' ');
  }

  /* ------------------------------------------------------------------ *
   *  the clerk's voice — fixed template variants, rotated
   *  DETERMINISTICALLY (by question index, settle count, draft index…).
   *  Same trace, same lines, every replay. No line carries a number that
   *  didn't come from the trace.
   * ------------------------------------------------------------------ */

  const pick = (arr, i) => arr[((i % arr.length) + arr.length) % arr.length];

  const WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six',
    'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve'];
  const word = (n) => (n >= 0 && n < WORDS.length ? WORDS[n] : String(n));

  const EPITHETS = {
    scorched_earth: 'Would rather burn it than split it.',
    sentimental_hoarder: 'Every object is a memory. Every memory is priceless.',
    spreadsheet: 'Everything at market price. Including the dog.',
    ledger: 'Keeps receipts. Emotional and otherwise.',
    already_healed: 'Just here to sign. Wishing you well. Mostly.',
  };

  const VOICE = {
    // Act II — garnish AFTER the registered trade-offer skeletons (never replacing them)
    probeWalletTail: ['', ' One of these is just money.', '', ' Take your time — I bill either way.'],
    probeBuyoutTail: ['', ' That is a real offer.', '', ' People have taken less.'],
    pairTail: ['', ' You cannot cry over both.', '', ' Pick the one you would carry out of a fire.'],
    ack: ['Noted.', 'Mm.', 'Filed.', 'Of course.'],
    hill: ['There it is.', 'There’s the hill.', 'Ah. There it is.'],
    // Act I — clerk interjections at REAL milestones only
    stallNote: [
      '“They’ve made this exact offer three times now. It isn’t working.”',
      '“Same numbers again. The record is broken.”',
    ],
    freezeCap: [
      '“For the record: nobody moved.”',
      '“Both sides call this leverage.”',
      '“This is where the money went.”',
    ],
    act1Rest: ['“The rest is why I have a job.”', '“The remainder proceeds to shouting.”'],
    act1AllSettled: '“All of it, settled. I’m as surprised as you.”',
    // Act III
    signed: ['Signed.', 'So signed.', 'Signed, dated.'],
    refuse: [
      '“Refused. Bold, considering.”',
      '“Refused. Noted. Filed under predictable.”',
      '“Refused. The paperwork holds no grudge. I might.”',
    ],
    bothRefuse: '“Both refused. Finally, something in common.”',
    ratify: ['“Ratified. Don’t look so surprised.”', '“Ratified. Witnessed. Done.”'],
    flipPre: '“We’re done here. Show your cards. Both of you.”',
    flipPreNoDecree: '“Out of drafts. Out of patience. Cards on the table.”',
    flipPost: '“Nobody peeked. Go ahead — check the math. Everyone does.”',
  };

  /** "One down. Five to grieve." — counts straight from the trace. */
  function settleQuip(c, left) {
    if (left === 0) return '“All ' + word(c) + ' of them, settled. Look at that.”';
    const v = [
      cap(word(c)) + ' down. ' + cap(word(left)) + ' to grieve.',
      cap(word(c)) + ' settled. ' + cap(word(left)) + ' to go.',
      'That leaves ' + word(left) + '.',
    ];
    return '“' + pick(v, c - 1) + '”';
  }

  /** 'a' vs 'an' for a formatted dollar figure (an $8,426 dog; a $153,293 opinion). */
  function aOrAn(moneyStr) {
    return /^\$(8|11,|18,)/.test(moneyStr) ? 'an' : 'a';
  }

  /** Read a required field; a missing field is a plain error, never a fallback. */
  function req(obj, path) {
    let cur = obj;
    for (const k of path.split('.')) {
      if (cur == null || !(k in cur)) throw new Error('trace is missing required field "' + path + '"');
      cur = cur[k];
    }
    if (cur == null) throw new Error('trace field "' + path + '" is null');
    return cur;
  }

  async function sha256Hex(str) {
    if (!(window.crypto && crypto.subtle)) {
      throw new Error('WebCrypto unavailable — serve this page from localhost or HTTPS to verify seals');
    }
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str));
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
  }

  /* ------------------------------------------------------------------ *
   *  model — everything derived from the trace, up front
   * ------------------------------------------------------------------ */

  function deriveModel(trace) {
    const m = { trace };

    m.meta = req(trace, 'meta');
    m.wildcardLabel = req(trace, 'meta.wildcard_label');
    m.engineNote = req(trace, 'meta.engine');

    m.cast = { A: req(trace, 'cast.a'), B: req(trace, 'cast.b') };
    m.names = { A: req(trace, 'cast.a.name'), B: req(trace, 'cast.b.name') };

    m.exchanges = req(trace, 'act1.exchange_log');
    m.perItem = req(trace, 'act1.per_item_exchanges');
    m.unsettled = req(trace, 'act1.unsettled');
    m.assetCount = Object.keys(m.perItem).length;

    m.traceQ = { A: req(trace, 'act2.trace_a'), B: req(trace, 'act2.trace_b') };
    m.nQuestions = req(trace, 'act2.n_questions');
    m.totalInterview = m.traceQ.A.length + m.traceQ.B.length;

    // interleave A/B question turns
    m.turns = [];
    const maxLen = Math.max(m.traceQ.A.length, m.traceQ.B.length);
    for (let i = 0; i < maxLen; i++) {
      if (i < m.traceQ.A.length) m.turns.push({ side: 'A', q: m.traceQ.A[i] });
      if (i < m.traceQ.B.length) m.turns.push({ side: 'B', q: m.traceQ.B[i] });
    }

    // eager validation: playback templates must never meet a missing field
    for (const t of m.turns) {
      const q = t.q;
      req(q, 'step'); req(q, 'bands');
      if (q.kind === 'probe') { req(q, 'asset'); req(q, 'price'); req(q, 'answer'); }
      else if (q.kind === 'pair') { req(q, 'A'); req(q, 'B'); req(q, 'answer'); }
      else throw new Error('unknown question kind "' + q.kind + '" in trace');
    }

    // per-side, per-asset log-scale domains + step-0 medians (HILL baseline)
    m.bandDomains = {}; m.base50 = {};
    for (const side of ['A', 'B']) {
      const doms = {}; const base = {};
      for (const a of BAND_ASSETS) doms[a] = { lo: Infinity, hi: -Infinity };
      m.traceQ[side].forEach((q, i) => {
        const bands = req(q, 'bands');
        for (const a of BAND_ASSETS) {
          const b = bands[a];
          if (!Array.isArray(b) || b.length !== 5) throw new Error('trace bands malformed for "' + a + '"');
          doms[a].lo = Math.min(doms[a].lo, b[0]);
          doms[a].hi = Math.max(doms[a].hi, b[4]);
          if (i === 0) base[a] = b[2];
        }
      });
      m.bandDomains[side] = doms; m.base50[side] = base;
    }

    m.drafts = req(trace, 'act3.drafts');
    m.decree = req(trace, 'decree');
    m.noDecree = !!m.decree.no_decree;

    m.flip = { A: req(trace, 'flip.a'), B: req(trace, 'flip.b') };
    try {
      m.payload = { A: JSON.parse(m.flip.A.payload), B: JSON.parse(m.flip.B.payload) };
    } catch (e) {
      throw new Error('flip payload is not valid JSON: ' + e.message);
    }
    m.walletTotal = req(m.payload.A, 'values.wallet'); // $24,000 in every trace — read, not assumed

    if (!m.noDecree) {
      m.sharesA = req(trace, 'decree.shares_a');
      m.receipt = req(trace, 'decree.receipt');
      m.scorecard = req(trace, 'scorecard');
    }
    return m;
  }

  function assetDisp(m, key) {
    if (key === 'wildcard') return m.wildcardLabel;
    const n = FIXED_NAMES[key];
    if (!n) throw new Error('unknown asset "' + key + '" in trace');
    return n;
  }

  /** "the dog 🐕" -> "Dog", "the IKEA futon" -> "IKEA Futon" (for "… Hill"). */
  function hillTitle(m, key) {
    let s = assetDisp(m, key).replace(/\s*\u{1F415}\s*/gu, ' ').trim();
    s = s.replace(/^the\s+/i, '');
    return titleCaseLabel(s);
  }

  /** Display name without the emoji ("the dog", "the espresso machine", …). */
  function cleanDisp(m, key) {
    return assetDisp(m, key).replace(/\s*\u{1F415}\s*/gu, ' ').replace(/\s+/g, ' ').trim();
  }

  /** Bare noun for the share line ("dog", "espresso machine", "karaoke machine"). */
  function hillNoun(m, key) {
    return cleanDisp(m, key).replace(/^the\s+/i, '');
  }

  /* The share line — ONE italic sentence under the tax subline, built ONLY
   * from trace fields (scorecard taxes, hill autopsy, act1/act3 counts).
   * Deterministic; this is the tweet. */
  function shareLineText(m) {
    if (m.noDecree) {
      const anyBoth = m.drafts.some((d) => d.ok_a === true && d.ok_b === true);
      return m.exchanges.length + ' exchanges. ' + m.drafts.length + ' drafts. '
        + (anyBoth ? 'No decree. ' : 'Never both signatures on the same page. ')
        + 'The lawyers send their regards.';
    }
    const s = m.scorecard;
    const taxA = req(s, 'pettiness_tax_a'), taxB = req(s, 'pettiness_tax_b');
    const total = taxA + taxB;
    const loser = taxA >= taxB ? 'a' : 'b';
    const autopsy = req(s, 'hill_autopsy.' + loser);
    const hillKey = req(autopsy, 'hill');
    if (total < 1000) {
      const share = req(m.sharesA, hillKey);
      const dest = share === 1 ? m.names.A : share === 0 ? m.names.B : 'both of them';
      return 'They fought over ' + fmtMoney(total) + '. '
        + cap(cleanDisp(m, hillKey)) + ' goes to ' + dest + '. Nobody grew.';
    }
    const tax = fmtMoney(Math.max(taxA, taxB));
    const retail = fmtMoney(req(autopsy, 'retail'));
    if (hillKey === 'wildcard') {
      // wildcard labels arrive as written ("his mother's painting") — keep them whole
      return 'That’s ' + aOrAn(tax) + ' ' + tax + ' opinion about '
        + cleanDisp(m, hillKey) + '. Retail: ' + retail + '.';
    }
    return 'That’s ' + aOrAn(tax) + ' ' + tax + ' opinion about '
      + aOrAn(retail) + ' ' + retail + ' ' + hillNoun(m, hillKey) + '.';
  }

  /* ------------------------------------------------------------------ *
   *  sentence builders (fixed templates over trace events)
   * ------------------------------------------------------------------ */

  function exchangeLine(m, ex) {
    const proposer = req(ex, 'proposer');
    const name = m.names[proposer];
    const asset = assetDisp(m, req(ex, 'asset'));
    const shareA = req(ex, 'share_a');
    const keep = proposer === 'A' ? shareA : 1 - shareA;

    let alloc;
    if (keep === 1) alloc = 'I keep ' + asset;
    else if (keep === 0) alloc = 'you keep ' + asset;
    else if (keep === 0.5) alloc = ex.asset === 'dog' ? 'we alternate custody of ' + asset : 'we split ' + asset + ' 50/50';
    else alloc = 'I take ' + pct(keep) + '% of ' + asset;

    const t = req(ex, 'transfer');
    let money = '';
    if (t > 0) money = ' — ' + fmtMoney(t) + ' to you';
    else if (t < 0) money = ' — ' + fmtMoney(-t) + ' to me';

    return name + ': ' + alloc + money;
  }

  /* ------------------------------------------------------------------ *
   *  player: autoplay through timed beats. Click/space PAUSES into step
   *  mode; each further click advances exactly one beat; ▶ resumes.
   *  Skip fast-forwards to the decree. Speed scales every duration.
   * ------------------------------------------------------------------ */

  function makePlayer(steps, onError, onState) {
    let i = 0, timer = null, anim = null, finished = false, paused = false;

    const completeAnim = () => { if (anim && anim.finish) anim.finish(); anim = null; };
    const state = () => { if (onState) onState(); };

    function runNext(fast) {
      const s = steps[i++];
      try {
        anim = s.run(fast) || null;
      } catch (e) {
        clearTimeout(timer);
        i = steps.length; finished = true; anim = null;
        onError(e);
      }
      return s;
    }

    function schedule() {
      if (i >= steps.length) { finished = true; state(); return; }
      const s = runNext(false);
      if (s.dur === Infinity) { finished = true; state(); return; }
      const d = (REDUCED ? Math.min(600, s.dur) : s.dur) / speed();
      timer = setTimeout(() => { completeAnim(); schedule(); }, d);
    }

    return {
      start() { paused = false; schedule(); state(); },
      isPaused() { return paused; },
      isFinished() { return finished; },
      pause() {
        if (finished || paused) return;
        paused = true; clearTimeout(timer); completeAnim(); state();
      },
      resume() {
        if (finished || !paused) return;
        paused = false; completeAnim(); schedule(); state();
      },
      stepOnce() {
        if (finished || !paused) return;
        completeAnim();
        if (i >= steps.length) { finished = true; state(); return; }
        const s = runNext(false);          // one beat, with its own animation
        if (s.dur === Infinity) finished = true;
        state();
      },
      skipToEnd() {
        clearTimeout(timer); completeAnim();
        while (i < steps.length) { runNext(true); completeAnim(); }
        finished = true; state();
      },
      destroy() { clearTimeout(timer); completeAnim(); i = steps.length; finished = true; },
    };
  }

  /** Run parts [[offsetMs, fn], …]; fast mode runs them all now. */
  function seq(fast, parts) {
    const ran = parts.map(() => false);
    const fire = (k) => { if (!ran[k]) { ran[k] = true; parts[k][1](); } };
    if (fast || REDUCED) { parts.forEach((_, k) => fire(k)); return null; }
    const timers = parts.map((p, k) => setTimeout(() => fire(k), p[0] / speed()));
    return { finish() { timers.forEach(clearTimeout); parts.forEach((_, k) => fire(k)); } };
  }

  /** Suppress CSS transitions/animations while fast-forwarding. */
  function instant(fn) {
    document.body.classList.add('instant');
    fn();
    requestAnimationFrame(() => requestAnimationFrame(() => document.body.classList.remove('instant')));
  }

  const SCENES = ['build', 'cold', 'act1', 'turn', 'act2', 'act3', 'decree'];
  function showScene(key) {
    for (const s of SCENES) {
      $('#scene-' + s).classList.toggle('active', s === key);
    }
  }

  /* ------------------------------------------------------------------ *
   *  scene builders — each fills its <section> and pushes steps
   * ------------------------------------------------------------------ */

  function portraitHTML(m, side, cls) {
    const c = m.cast[side];
    const sliders = req(c, 'sliders');
    const meters = ['pettiness', 'spite', 'patience'].map((k) => {
      const v = req(sliders, k);
      return '<div class="meter"><div class="m-label"><span>' + k + '</span><span>' + v.toFixed(2) + '</span></div>'
        + '<div class="m-track"><div class="m-fill" style="width:' + (v * 100) + '%"></div></div></div>';
    }).join('');
    const epithet = EPITHETS[String(c.archetype)];
    return '<div class="portrait ' + cls + '">'
      + '<div class="monogram">' + esc(c.name.charAt(0).toUpperCase()) + '</div>'
      + '<div class="p-name">' + esc(c.name) + '</div>'
      + '<span class="chip">' + esc(String(c.archetype).replace(/_/g, ' ')) + '</span>'
      + (epithet ? '<div class="p-epithet">' + esc(epithet) + '</div>' : '')
      + meters
      + '<div class="p-fight">declared fight cost · ' + fmtMoney(req(c, 'fight_cost')) + '</div>'
      + '</div>';
  }

  function buildColdOpen(m, steps) {
    // Subtitle: the preset's card line, or — for a live filing — the case number
    // straight from the trace (meta.preset_seed is the server-drawn seed).
    const p = PRESETS[currentPreset];
    const subline = p
      ? '“' + p.label + '” — ' + p.sub
      : 'Case #' + esc(String(req(m.meta, 'preset_seed'))) + ', filed at this window.';

    $('#scene-cold').innerHTML =
      '<div class="corner-stamp">valuations sealed · ' + shortSeal(req(m.cast.A, 'seal'))
        + ' · ' + shortSeal(req(m.cast.B, 'seal')) + '</div>'
      + '<div class="cold-head"><h1>IRRECONCILABLE AGENTS</h1>'
      + '<p class="tagline">The divorce is fake. The math is real.</p>'
      + '<p class="preset-sub">' + subline + '</p></div>'
      + '<div class="versus">' + portraitHTML(m, 'A', 'p-a')
      + '<div class="vs">vs</div>' + portraitHTML(m, 'B', 'p-b') + '</div>'
      + '<p class="hint">click / space pauses, then steps one beat at a time · ▶ resumes · the decree is inevitable</p>';

    steps.push({ scene: 'cold', dur: 8000, run() { showScene('cold'); } });
  }

  function buildAct1(m, steps) {
    $('#scene-act1').innerHTML =
      '<p class="kicker">ACT I · “your lawyers’ way” — billed hourly</p>'
      + '<div id="ticker-wrap"><span id="x-counter"></span>'
      + '<div id="ticker-scroll"><ul id="ticker"></ul></div></div>'
      + '<div id="freeze" hidden></div>'
      + '<p id="act1-summary" hidden></p>';

    // Ticker lines: one per real exchange. Milestones come FROM the log:
    //  - an accepted offer gets a ✓ line plus a clerk quip (counts from trace)
    //  - the 3rd occurrence of an identical offer (proposer+asset+share+transfer)
    //    starts the broken-record stretch: repeats slow down, pile up, and the
    //    clerk notes it once. Detection is pure data; no line is invented.
    const lines = [];
    let n = 0, settledSoFar = 0, stallNotes = 0;
    const offerCount = new Map();
    for (const ex of m.exchanges) {
      n += 1;
      const key = [req(ex, 'proposer'), req(ex, 'asset'), req(ex, 'share_a'), req(ex, 'transfer')].join('|');
      const c = (offerCount.get(key) || 0) + 1;
      offerCount.set(key, c);
      const stall = c >= 3;
      lines.push({ text: exchangeLine(m, ex), cls: stall ? 'stall' : '', n, ms: stall ? TICK_STALL_MS : TICK_MS });
      if (c === 3) {
        lines.push({ text: pick(VOICE.stallNote, stallNotes), cls: 'clerk-note', n, ms: TICK_NOTE_MS });
        stallNotes += 1;
      }
      if (req(ex, 'accepted') === true) {
        settledSoFar += 1;
        lines.push({ text: '✓ ' + assetDisp(m, ex.asset) + ' settled', cls: 'ok', n, ms: TICK_SETTLE_MS });
        lines.push({ text: settleQuip(settledSoFar, m.assetCount - settledSoFar), cls: 'clerk-note', n, ms: TICK_QUIP_MS });
      }
    }
    let cum = 0;
    for (const L of lines) { L.at = cum; cum += L.ms; }
    const tickerTotal = cum;
    const totalX = m.exchanges.length;

    steps.push({
      scene: 'act1',
      dur: tickerTotal + 500,
      run(fast) {
        showScene('act1');
        const ul = $('#ticker'), wrap = $('#ticker-scroll'), counter = $('#x-counter');
        ul.innerHTML = '';
        let shown = 0;
        const push = () => {
          const L = lines[shown];
          const li = document.createElement('li');
          li.className = L.cls;
          li.textContent = L.text;
          ul.appendChild(li);
          counter.textContent = L.n + ' / ' + totalX + ' exchanges';
          shown += 1;
        };
        const settle = () => { wrap.scrollTop = wrap.scrollHeight; };
        if (fast || REDUCED) { while (shown < lines.length) push(); settle(); return null; }
        // virtual clock so the speed toggle applies mid-ticker
        let raf, vt = 0, last = performance.now();
        const loop = (t) => {
          vt += (t - last) * speed(); last = t;
          while (shown < lines.length && lines[shown].at <= vt) push();
          settle();
          if (shown < lines.length) raf = requestAnimationFrame(loop);
        };
        raf = requestAnimationFrame(loop);
        return { finish() { cancelAnimationFrame(raf); while (shown < lines.length) push(); settle(); } };
      },
    });

    // freeze frame: the most-fought unsettled asset (only if something is unsettled)
    if (m.unsettled.length > 0) {
      let worst = m.unsettled[0];
      for (const a of m.unsettled) {
        if (req(m.perItem, a) > req(m.perItem, worst)) worst = a;
      }
      const count = req(m.perItem, worst);
      steps.push({
        scene: 'act1',
        dur: 3000,
        run() {
          const f = $('#freeze');
          f.hidden = false;
          f.innerHTML = '<div class="f-asset">' + esc(assetDisp(m, worst)) + '</div>'
            + '<div class="f-stat">' + count + ' EXCHANGES · 0 PROGRESS</div>'
            + '<div class="f-cap">' + esc(pick(VOICE.freezeCap, count)) + '</div>';
        },
      });
    }

    const settledCount = m.assetCount - m.unsettled.length;
    steps.push({
      scene: 'act1',
      dur: 3200,
      run() {
        const el = $('#act1-summary');
        el.hidden = false;
        const garnish = m.unsettled.length > 0
          ? pick(VOICE.act1Rest, m.exchanges.length)
          : VOICE.act1AllSettled;
        el.innerHTML = esc(settledCount + ' of ' + m.assetCount + ' assets settled after '
          + m.exchanges.length + ' exchanges.')
          + '<br><span class="s-clerk">' + esc(garnish) + '</span>';
      },
    });
  }

  function buildTurn(m, steps) {
    $('#scene-turn').innerHTML =
      '<span class="clerk-plate">MEDIATOR — window 4 · no appointments</span>'
      + '<p id="turn-line">“I have some questions.”</p>'
      + '<p id="turn-line2">“Both of you. Separately.”</p>';
    steps.push({
      scene: 'turn',
      dur: 4400,
      run(fast) {
        showScene('turn');
        return seq(fast, [
          [900, () => { $('#turn-line').classList.add('shown'); }],
          [2400, () => { $('#turn-line2').classList.add('shown'); }],
        ]);
      },
    });
  }

  function bandPanelHTML(m, side) {
    const rows = BAND_ASSETS.map((a) =>
      '<div class="band-row" data-asset="' + a + '">'
      + '<div class="b-head"><span>' + esc(assetDisp(m, a))
      + ' <span class="hill-chip" hidden>HILL?</span></span>'
      + '<span class="b-med"></span></div>'
      + '<div class="b-track" hidden><div class="b-outer"></div><div class="b-inner"></div><div class="b-tick"></div></div>'
      + '</div>').join('');
    return '<div class="band-panel" data-side="' + side + '">'
      + '<h3>' + esc(m.names[side]) + ' — implied value bands</h3>'
      + '<div class="band-note">log scale · p10–p90 outer · p25–p75 inner · median tick</div>'
      + rows + '</div>';
  }

  function buildAct2(m, steps) {
    $('#scene-act2').innerHTML =
      '<p class="kicker">ACT II · the interview — one of you at a time</p>'
      + '<div id="act2-grid"><div id="dialogue"></div>'
      + '<div id="bands">' + bandPanelHTML(m, 'A') + bandPanelHTML(m, 'B') + '</div></div>';

    const dlg = () => $('#dialogue');
    const hillAnnounced = { A: {}, B: {} };
    let hillSeen = 0;
    function say(cls, text) {
      const div = document.createElement('div');
      div.className = 'line ' + cls;
      div.textContent = text;
      dlg().appendChild(div);
      dlg().scrollTop = dlg().scrollHeight;
    }

    function xPos(side, asset, v) {
      const d = m.bandDomains[side][asset];
      if (!(d.hi > d.lo)) return 50;
      return ((Math.log(v) - Math.log(d.lo)) / (Math.log(d.hi) - Math.log(d.lo))) * 100;
    }

    function updateBands(side, bands, stepIdx) {
      const panel = document.querySelector('.band-panel[data-side="' + side + '"]');
      for (const a of BAND_ASSETS) {
        const b = bands[a];
        const row = panel.querySelector('.band-row[data-asset="' + a + '"]');
        const track = row.querySelector('.b-track');
        track.hidden = false;
        const p10 = xPos(side, a, b[0]), p25 = xPos(side, a, b[1]), p50 = xPos(side, a, b[2]),
          p75 = xPos(side, a, b[3]), p90 = xPos(side, a, b[4]);
        const outer = row.querySelector('.b-outer');
        outer.style.left = p10 + '%'; outer.style.width = Math.max(0.5, p90 - p10) + '%';
        const inner = row.querySelector('.b-inner');
        inner.style.left = p25 + '%'; inner.style.width = Math.max(0.5, p75 - p25) + '%';
        row.querySelector('.b-tick').style.left = p50 + '%';
        row.querySelector('.b-med').textContent = fmtCompact(b[2]);
      }
      // HILL? chip — the mechanic is ONE hill per persona, so flag only the
      // side's strongest outlier: the max p50-growth asset, and only once it
      // exceeds HILL_RATIO x its own step-0 p50 (still purely data-derived).
      // Returns the asset key the first time a side's chip lights up, so the
      // clerk can mark the moment ("There it is.") — a real detection event.
      let revealed = null;
      let hillAsset = null, hillGrowth = 0;
      for (const a of BAND_ASSETS) {
        const growth = bands[a][2] / m.base50[side][a];
        if (growth > hillGrowth) { hillGrowth = growth; hillAsset = a; }
      }
      for (const a of BAND_ASSETS) {
        const chip = panel.querySelector('.band-row[data-asset="' + a + '"] .hill-chip');
        const isHill = stepIdx > 0 && a === hillAsset && hillGrowth > HILL_RATIO;
        if (isHill && chip.hidden) {
          chip.hidden = false;
          chip.classList.remove('flash'); void chip.offsetWidth; chip.classList.add('flash');
          if (!hillAnnounced[side][a]) { hillAnnounced[side][a] = true; revealed = a; }
        } else if (!isHill) {
          chip.hidden = true;
        }
      }
      return revealed;
    }

    function activate(side) {
      document.querySelectorAll('.band-panel').forEach((p) => {
        p.classList.toggle('active', p.dataset.side === side);
      });
    }

    m.turns.forEach((turn, k) => {
      const { side, q } = turn;
      const qNum = k + 1;
      const who = m.names[side];
      steps.push({
        scene: 'act2',
        dur: 2600,
        run(fast) {
          showScene('act2');
          activate(side);
          const parts = [];
          parts.push([0, () => {
            const lead = qNum === 1
              ? 'Question 1 of ' + m.totalInterview + '. '
              : 'Question ' + qNum + '. ';
            if (q.kind === 'probe') {
              // A probe is a TRADE OFFER, never a valuation question — humans
              // can answer "would you take this deal", not "what is it worth"
              // (the engine's update is the same inequality either way).
              // The registered skeletons stay verbatim; only the tail rotates.
              const price = req(q, 'price');
              const disp = assetDisp(m, req(q, 'asset'));
              const offer = price <= 24000
                ? cap(disp) + ', or ' + fmtPrice(price) + ' more of the wallet?'
                  + pick(VOICE.probeWalletTail, qNum)
                : 'If the settlement paid you ' + fmtPrice(price)
                  + ' to give up ' + disp + ' — take it?'
                  + pick(VOICE.probeBuyoutTail, qNum);
              say('clerk', lead + offer);
            } else if (q.kind === 'pair') {
              say('clerk', lead + cap(assetDisp(m, req(q, 'A')))
                + ', or ' + assetDisp(m, req(q, 'B')) + '?'
                + pick(VOICE.pairTail, qNum));
            } else {
              throw new Error('unknown question kind "' + q.kind + '" in trace');
            }
          }]);
          parts.push([1500, () => {
            let ans;
            if (q.kind === 'probe') {
              ans = q.answer === true ? 'Yes.' : 'No.';
            } else if (q.answer === 'A') ans = cap(assetDisp(m, q.A)) + '.';
            else if (q.answer === 'B') ans = cap(assetDisp(m, q.B)) + '.';
            else ans = 'Neither.'; // pair answer "walk" (never invented; schema event type)
            say('reply', who + ': “' + ans + '”');
            const revealedHill = updateBands(side, req(q, 'bands'), req(q, 'step'));
            // deterministic clerk punctuation, keyed only to real events:
            // a hill detection, a refusal, an answer landing on the cadence.
            if (revealedHill) say('aside', pick(VOICE.hill, hillSeen++));
            else if (q.kind === 'probe' && q.answer === false && k % 7 === 5) say('aside', 'That’s what they all say.');
            else if (q.kind === 'pair' && ans === 'Neither.') say('aside', 'Neither. Bold.');
            else if (k % 5 === 4) say('aside', pick(VOICE.ack, Math.floor(k / 5)));
          }]);
          return seq(fast, parts);
        },
      });
    });
  }

  function sigMarkSVG() {
    return '<svg width="80" height="24" viewBox="0 0 80 24" aria-hidden="true">'
      + '<path d="M4 18 C 10 4, 15 24, 21 11 S 32 19, 38 9 S 50 21, 56 11 S 66 17, 76 8"/></svg>';
  }

  function draftLines(m, proposal) {
    const keepsA = [], keepsB = [], extra = [];
    for (const a of ASSET_ORDER) {
      if (!(a in proposal)) throw new Error('draft proposal missing asset "' + a + '"');
      const s = proposal[a];
      const disp = assetDisp(m, a);
      if (a === 'wallet' && s > 0 && s < 1) {
        extra.push(disp + ': ' + fmtMoney(s * m.walletTotal) + ' ' + m.names.A
          + ' / ' + fmtMoney((1 - s) * m.walletTotal) + ' ' + m.names.B);
      } else if (a === 'dog' && s === 0.5) {
        extra.push(disp + ': alternating custody');
      } else if (s === 1) keepsA.push(disp);
      else if (s === 0) keepsB.push(disp);
      else extra.push(disp + ': ' + pct(s) + '% ' + m.names.A + ' / ' + pct(1 - s) + '% ' + m.names.B);
    }
    const out = [];
    if (keepsA.length) out.push(m.names.A + ' keeps: ' + keepsA.join(', '));
    if (keepsB.length) out.push(m.names.B + ' keeps: ' + keepsB.join(', '));
    return out.concat(extra);
  }

  function flipCardHTML(m, side) {
    const f = m.flip[side];
    const p = m.payload[side];
    const rows = ASSET_ORDER.map((a) =>
      '<div class="fv-row"><span>' + esc(assetDisp(m, a)) + '</span>'
      + '<span class="fv-val">' + fmtMoney(req(p, 'values.' + a)) + '</span></div>').join('');
    return '<div class="flipwrap"><div class="flipcard" data-side="' + side + '">'
      + '<div class="flip-face flip-front">'
      + '<div class="fd-label">SEALED</div>'
      + '<div class="fd-hash">' + esc(shortSeal(req(f, 'seal'))) + '…</div>'
      + '<div class="fd-label" style="letter-spacing:.1em;font-size:.6rem">' + esc(m.names[side]) + '</div>'
      + '</div>'
      + '<div class="flip-face flip-back">'
      + '<h4>' + esc(m.names[side]) + ' — true valuations</h4>'
      + rows
      + '<div class="fv-row fv-strong"><span>walk-away</span><span class="fv-val">'
      + fmtMoney(req(f, 'walk_away')) + '</span></div>'
      + '<div class="fv-row"><span>spite λ</span><span class="fv-val">' + req(p, 'lam') + '</span></div>'
      + '<div class="fv-seal">' + esc(req(f, 'seal')) + '</div>'
      + '<div class="verify-result" data-side="' + side + '"></div>'
      + '</div></div></div>';
  }

  function buildAct3(m, steps) {
    $('#scene-act3').innerHTML =
      '<p class="kicker">ACT III · paperwork, then the flip</p>'
      + '<div id="act3-grid"><div id="drafts"></div><div id="act3-clerk"></div>'
      + '<div id="flip-area" hidden>'
      + '<div id="flip-cards">' + flipCardHTML(m, 'A') + flipCardHTML(m, 'B') + '</div>'
      + '<div id="verify-row"><button id="verify-btn">verify seals</button>'
      + '<div id="verify-note">sha-256 of each revealed payload, recomputed in your browser, vs the seal stamped at t0</div>'
      + '</div></div>';

    const clerkLine = (t) => { $('#act3-clerk').textContent = t; };

    m.drafts.forEach((d, i) => {
      const okA = req(d, 'ok_a') === true;
      const okB = req(d, 'ok_b') === true;
      const lines = draftLines(m, req(d, 'proposal'));

      steps.push({
        scene: 'act3',
        dur: 2500,
        run() {
          showScene('act3');
          document.querySelectorAll('#drafts .draft').forEach((el) => el.classList.add('past'));
          const div = document.createElement('div');
          div.className = 'draft';
          div.innerHTML = '<div class="d-head">DRAFT #' + (i + 1) + '</div>'
            + lines.map((l) => '<div class="d-line">' + esc(l) + '</div>').join('')
            + '<div class="sig-row">'
            + '<div class="sig" data-side="A"><div class="s-name">' + esc(m.names.A) + '</div><div class="s-mark"></div><div class="s-verdict"></div></div>'
            + '<div class="sig" data-side="B"><div class="s-name">' + esc(m.names.B) + '</div><div class="s-mark"></div><div class="s-verdict"></div></div>'
            + '</div>';
          $('#drafts').appendChild(div);
          div.scrollIntoView({ block: 'nearest', behavior: REDUCED ? 'auto' : 'smooth' });
        },
      });

      steps.push({
        scene: 'act3',
        dur: 3200,
        run(fast) {
          const div = $('#drafts').lastElementChild;
          const sign = (side, ok, v) => () => {
            const slot = div.querySelector('.sig[data-side="' + side + '"]');
            if (ok) {
              slot.querySelector('.s-mark').innerHTML = sigMarkSVG();
              slot.querySelector('.s-verdict').textContent = pick(VOICE.signed, v);
            } else {
              slot.querySelector('.s-verdict').innerHTML = '<span class="refused">REFUSED.</span>';
            }
          };
          const parts = [[400, sign('A', okA, i)], [1500, sign('B', okB, i + 1)]];
          if (!okA && !okB) parts.push([2300, () => clerkLine(VOICE.bothRefuse)]);
          else if (!okA || !okB) parts.push([2300, () => clerkLine(pick(VOICE.refuse, i))]);
          else parts.push([2300, () => clerkLine(pick(VOICE.ratify, i))]);
          return seq(fast, parts);
        },
      });
    });

    // the flip — sealed cards turn over; runs on every path (NO DECREE included)
    steps.push({
      scene: 'act3',
      dur: 1800,
      run() {
        clerkLine(m.noDecree ? VOICE.flipPreNoDecree : VOICE.flipPre);
        $('#flip-area').hidden = false;
      },
    });
    steps.push({
      scene: 'act3',
      dur: 4000,
      run(fast) {
        return seq(fast, [[500, () => {
          document.querySelectorAll('.flipcard').forEach((c) => c.classList.add('flipped'));
        }]]);
      },
    });
    steps.push({
      scene: 'act3',
      dur: 4500,
      run() { clerkLine(VOICE.flipPost); },
    });
  }

  async function verifySeals(m) {
    const btn = $('#verify-btn');
    btn.disabled = true;
    for (const side of ['A', 'B']) {
      const out = document.querySelector('.verify-result[data-side="' + side + '"]');
      try {
        const hex = await sha256Hex(m.flip[side].payload); // hash the exact payload string
        const ok = ('sha256:' + hex) === m.flip[side].seal;
        out.textContent = ok ? '✓ VERIFIED' : '✗ MISMATCH';
        out.className = 'verify-result ' + (ok ? 'v-ok' : 'v-bad');
      } catch (e) {
        out.textContent = '✗ ' + e.message;
        out.className = 'verify-result v-bad';
      }
    }
    btn.disabled = false;
    btn.textContent = 're-verify seals';
  }

  /* ------------------------------------------------------------------ *
   *  the decree
   * ------------------------------------------------------------------ */

  function dogSVG() {
    // courtroom-etching seated dog, simple ink line art
    // (ear and tail carry classes for a CSS-only 2-frame idle twitch)
    const p = (d, cls) => '<path' + (cls ? ' class="' + cls + '"' : '') + ' d="' + d + '"/>';
    return '<svg width="86" height="94" viewBox="0 0 140 150" fill="none" stroke="#1b1a17" '
      + 'stroke-width="2.2" stroke-linecap="round" aria-hidden="true">'
      + p('M30 34 C 32 21, 45 15, 56 20')          // skull
      + p('M53 17 C 62 12, 69 21, 62 32 C 59 36, 55 36, 54 31', 'dog-ear') // ear
      + p('M30 34 C 25 38, 19 40, 14 42')          // brow to muzzle
      + p('M14 42 C 11 44, 11 46, 15 48')          // nose tip
      + p('M15 48 C 22 52, 30 52, 35 50')          // jaw
      + '<circle cx="40" cy="32" r="1.8" fill="#1b1a17" stroke="none"/>' // eye
      + p('M35 50 C 38 62, 41 72, 44 84')          // throat
      + p('M36 53 C 42 57, 50 57, 55 54')          // collar
      + p('M44 84 C 44 100, 43 116, 43 128')       // front leg
      + p('M43 128 C 43 132, 50 134, 55 132')      // front paw
      + p('M53 92 C 53 105, 52 118, 52 128')       // second leg
      + p('M52 128 C 52 131, 58 133, 62 131')      // second paw
      + p('M56 20 C 69 26, 75 40, 79 52')          // back of neck
      + p('M79 52 C 95 60, 105 74, 107 93')        // back
      + p('M107 93 C 109 112, 97 128, 79 131')     // haunch
      + p('M79 131 C 71 132, 64 132, 59 130')      // rear paw forward
      + p('M105 108 C 117 106, 123 96, 119 86 C 117 80, 111 78, 107 83', 'dog-tail') // tail
      + p('M86 100 L 96 112') + p('M80 106 L 90 118') + p('M92 92 L 102 104') // haunch hatching
      + p('M28 138 L 112 138')                     // ground line
      + p('M34 143 L 44 143') + p('M96 143 L 106 143') // ground ticks
      + '</svg>';
  }

  function stampHTML() {
    return '<div class="stamp"><span class="st-top">NOBODY PEEKED</span>'
      + '<span class="st-sub">verified · snhp</span></div>';
  }

  function ledgerRowsHTML(m) {
    const rows = [];
    for (const a of ASSET_ORDER) {
      const s = req(m.sharesA, a);
      const disp = assetDisp(m, a);
      let val;
      if (a === 'wallet') {
        val = fmtMoney(s * m.walletTotal) + ' her · ' + fmtMoney((1 - s) * m.walletTotal) + ' him';
      } else if (a === 'dog' && s === 0.5) {
        val = 'alternating custody.';
      } else if (s === 1) val = 'hers.';
      else if (s === 0) val = 'his.';
      else val = pct(s) + '% her, ' + pct(1 - s) + '% him.';
      rows.push('<div class="lg-row"><span class="lg-asset">' + esc(disp) + '</span> — ' + esc(val) + '</div>');
    }
    return rows.join('');
  }

  function buildDecree(m, steps) {
    const sc = $('#scene-decree');
    const inre = 'IN RE: THE MARRIAGE OF ' + esc(m.names.A.charAt(0).toUpperCase()) + '. &amp; '
      + esc(m.names.B.charAt(0).toUpperCase()) + '.';

    let cardHTML, belowHTML;
    const shareRow = '<div class="dc-share"><span class="share-text" id="share-line">'
      + esc(shareLineText(m)) + '</span>'
      + '<button id="share-copy" title="copy the line">copy</button></div>';

    if (m.noDecree) {
      const verdict = m.decree.no_zopa
        ? 'No overlap exists. Some marriages even math can’t save.'
        : 'The mediator declined to certify a deal.';
      cardHTML =
        '<div id="decree-card" class="nodecree">'
        + '<div class="dc-head"><div class="dc-title">FINAL DECREE</div>'
        + '<div class="dc-inre">' + inre + '</div></div>'
        + '<div class="dc-nodecree">NO DECREE.</div>'
        + '<div class="dc-lines">'
        + '<p>' + m.assetCount + ' assets. ' + m.exchanges.length + ' exchanges. ' + m.nQuestions + ' questions.</p>'
        + '<p>' + esc(verdict) + '</p>'
        + '</div>'
        + '<hr class="dc-rule">'
        + '<div class="dc-tax" style="text-align:center">PETTINESS TAX: everything.</div>'
        + shareRow
        + '<div class="dc-bottom"><div class="dc-dog">' + dogSVG() + '</div>' + stampHTML() + '</div>'
        + '<div class="dc-fine">valuations sealed · ' + shortSeal(m.flip.A.seal) + ' · '
        + shortSeal(m.flip.B.seal) + ' · no decree issued</div>'
        + '</div>';
      belowHTML = '';
    } else {
      const s = m.scorecard;
      const taxA = req(s, 'pettiness_tax_a'), taxB = req(s, 'pettiness_tax_b');
      const loser = taxA >= taxB ? 'a' : 'b';
      const tax = Math.max(taxA, taxB);
      const loserName = loser === 'a' ? m.names.A : m.names.B;
      const autopsy = req(s, 'hill_autopsy.' + loser);
      const rc = m.receipt;
      const checks = req(rc, 'checks');
      const ratifiedLine = (checks.ratified_a === true && checks.ratified_b === true)
        ? ' · both parties ratified' : '';
      const fine = 'engine ' + esc(req(rc, 'engine_version'))
        + ' · ' + shortSeal(req(rc, 'inputs.digest_a'))
        + ' · ' + shortSeal(req(rc, 'inputs.digest_b')) + ratifiedLine;

      cardHTML =
        '<div id="decree-card">'
        + '<div class="dc-head"><div class="dc-title">FINAL DECREE</div>'
        + '<div class="dc-inre">' + inre + '</div></div>'
        + '<div class="ledger">' + ledgerRowsHTML(m) + '</div>'
        + '<hr class="dc-rule">'
        + '<div class="dc-tax">PETTINESS TAX: ' + fmtMoney(tax) + '</div>'
        + '<div class="dc-tax-sub">(' + esc(loserName) + ', dying on ' + esc(hillTitle(m, req(autopsy, 'hill')))
        + ' Hill — retail ' + fmtMoney(req(autopsy, 'retail')) + ')</div>'
        + shareRow
        + '<div class="dc-bottom"><div class="dc-dog">' + dogSVG() + '</div>' + stampHTML() + '</div>'
        + '<div class="dc-fine">' + fine + '</div>'
        + '</div>';

      const delta = req(s, 'joint_surplus') - req(s, 'arm_i_joint_surplus');
      const lawyersBit = delta > 0
        ? 'lawyers’ way left ' + fmtMoney(delta) + ' on the table'
        : 'the lawyers’ way came out ' + fmtMoney(-delta) + ' ahead here';
      const scoreboard = 'surplus split ' + req(s, 'split_a_pct') + '/' + (100 - req(s, 'split_a_pct'))
        + ' (' + esc(m.names.A) + '/' + esc(m.names.B) + ')'
        + ' · settled in ' + m.nQuestions + ' questions, ' + m.drafts.length + ' drafts'
        + ' · ' + lawyersBit;
      const closing = (taxA + taxB) < 1000
        ? 'Nothing much set on fire. Was it ever love?'
        : 'Both above walk-away. Nobody peeked.';

      belowHTML =
        '<div id="scoreboard">' + scoreboard + '</div>'
        + '<p id="closing-line">' + esc(closing) + '</p>'
        + '<div id="receipt-row"><button id="rc-toggle">view receipt</button>'
        + '<pre id="rc-json"></pre></div>';
    }

    sc.innerHTML = '<p class="kicker">' + (m.noDecree ? 'no decree' : 'the decree') + '</p>'
      + cardHTML + belowHTML;

    if (!m.noDecree) {
      $('#rc-json').textContent = JSON.stringify(m.receipt, null, 2);
      $('#rc-toggle').addEventListener('click', () => {
        const el = $('#rc-json');
        el.classList.toggle('open');
        $('#rc-toggle').textContent = el.classList.contains('open') ? 'hide receipt' : 'view receipt';
      });
    }

    // the share line's copy affordance — clipboard if available, else select it
    const copyBtn = $('#share-copy');
    const selectShare = () => {
      const rng = document.createRange();
      rng.selectNodeContents($('#share-line'));
      const sel = window.getSelection();
      sel.removeAllRanges(); sel.addRange(rng);
    };
    copyBtn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const text = $('#share-line').textContent;
      const done = () => {
        copyBtn.textContent = 'copied';
        setTimeout(() => { copyBtn.textContent = 'copy'; }, 1200);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, selectShare);
      } else {
        selectShare();
      }
    });

    steps.push({ scene: 'decree', dur: Infinity, run() { showScene('decree'); } });
  }

  /* ------------------------------------------------------------------ *
   *  boot
   * ------------------------------------------------------------------ */

  let player = null;
  let currentPreset = null;   // preset key, or null for a live filing
  let currentTrace = null;    // last successfully played trace (for replay)
  let archetypeInfo = null;   // cached GET /v1/divorce/archetypes

  function refreshPP() {
    const b = $('#pp');
    if (!b) return;
    if (!player || player.isFinished()) {
      b.disabled = true;
      b.textContent = '⏸ pause';
      return;
    }
    b.disabled = false;
    b.textContent = player.isPaused() ? '▶ play' : '⏸ pause';
  }

  function showError(msg) {
    for (const s of SCENES) $('#scene-' + s).classList.remove('active');
    const el = $('#error');
    el.hidden = false;
    el.textContent = msg;
  }

  function buildFilm(trace) {
    const m = deriveModel(trace);
    $('#engine-note').textContent = m.engineNote;
    const steps = [];
    buildColdOpen(m, steps);
    buildAct1(m, steps);
    buildTurn(m, steps);
    buildAct2(m, steps);
    buildAct3(m, steps);
    buildDecree(m, steps);
    return { m, steps };
  }

  /** Play a validated trace: presets and live filings share this one path. */
  function playTrace(trace, presetKey) {
    currentPreset = presetKey;
    currentTrace = trace;
    document.querySelectorAll('#presets button').forEach((b) => {
      b.classList.toggle('active', b.dataset.preset === presetKey);
    });
    $('#build-btn').classList.remove('active');
    if (player) { player.destroy(); player = null; }
    $('#error').hidden = true;

    let film;
    try {
      film = buildFilm(trace);
    } catch (e) {
      showError('Trace failed validation — ' + e.message
        + '\n\nNothing is rendered from a broken trace: no fallbacks, no invented numbers.');
      refreshPP();
      return;
    }

    // CASE # — meta.preset_seed straight from the trace; same number, same divorce
    const chip = $('#case-chip');
    chip.textContent = 'CASE #' + req(trace, 'meta.preset_seed');
    chip.hidden = false;

    const btn = $('#verify-btn');
    if (btn) btn.addEventListener('click', (ev) => { ev.stopPropagation(); verifySeals(film.m); });

    player = makePlayer(film.steps, (e) => {
      showError('Playback halted — ' + e.message
        + '\n\nNothing is rendered from a broken trace: no fallbacks, no invented numbers.');
      refreshPP();
    }, refreshPP);
    player.start();
  }

  async function loadPreset(key) {
    const preset = PRESETS[key];
    if (!preset) throw new Error('unknown preset "' + key + '"');
    if (player) { player.destroy(); player = null; }
    refreshPP();
    $('#error').hidden = true;

    let trace;
    try {
      const res = await fetch(preset.file);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      trace = await res.json();
    } catch (e) {
      showError('Failed to load ' + preset.file + ' — ' + e.message
        + '\n\nThis page is a player of pre-generated engine traces; without the trace there is nothing honest to show.');
      return;
    }
    playTrace(trace, key);
  }

  /* ------------------------------------------------------------------ *
   *  BUILD YOUR EXES — the live mode. The form posts to the divorce API
   *  and plays back whatever trace the engine actually produced. If the
   *  office is closed, it says so; it never invents a trace and never
   *  quietly substitutes a preset.
   * ------------------------------------------------------------------ */

  const FRONTABLE = ['dog', 'vinyl', 'wildcard']; // per the API contract
  const SLIDER_KEYS = ['pettiness', 'spite', 'patience'];

  function hillOptionLabel(key, wildcardText) {
    if (key === 'wildcard') return wildcardText || 'the wildcard item';
    const n = FIXED_NAMES[key];
    return n ? n.replace(/\s*\u{1F415}\s*/gu, ' ').trim() : key;
  }

  function personaColHTML(side, title, ph) {
    const cards = Object.keys(archetypeInfo.archetypes).map((k) =>
      '<label class="arch-card">'
      + '<input type="radio" name="arch-' + esc(side) + '" value="' + esc(k) + '">'
      + '<span class="ac-name">' + esc(k.replace(/_/g, ' ')) + '</span>'
      + (EPITHETS[k] ? '<span class="ac-epi">' + esc(EPITHETS[k]) + '</span>' : '')
      + '</label>').join('');
    const sliders = SLIDER_KEYS.map((s) =>
      '<label class="bslider"><span class="bs-label"><span>' + s + '</span>'
      + '<span class="bs-val" data-out="' + s + '">0.50</span></span>'
      + '<input type="range" min="0" max="1" step="0.05" value="0.5" data-slider="' + s + '"></label>').join('');
    const hills = archetypeInfo.hillable.map((h) =>
      '<option value="' + esc(h) + '">' + esc(hillOptionLabel(h, '')) + '</option>').join('');
    return '<div class="bp-col" data-side="' + side + '">'
      + '<h3>' + title + '</h3>'
      + '<label class="bfield"><span>name</span>'
      + '<input type="text" maxlength="24" class="b-name" placeholder="' + ph + '"></label>'
      + '<div class="arch-cards">' + cards + '</div>'
      + sliders
      + '<label class="bfield"><span>the hill they’ll die on — sealed until the flip</span>'
      + '<select class="b-hill">' + hills + '</select></label>'
      + '</div>';
  }

  function renderBuilder() {
    const sc = $('#scene-build');
    const fronts = FRONTABLE.map((k) =>
      '<label class="bfront"><input type="checkbox" value="' + k + '"><span>'
      + esc(hillOptionLabel(k, 'the wildcard item')) + '</span></label>').join('');
    sc.innerHTML =
      '<p class="kicker">intake · build your exes</p>'
      + '<p class="build-lede">Two parties, one engine, no script. The county sees everything and tells no one.</p>'
      + '<div id="build-grid">'
      + personaColHTML('a', 'Party A', 'Dana')
      + personaColHTML('b', 'Party B', 'Morgan')
      + '</div>'
      + '<div class="b-shared">'
      + '<fieldset class="bfronts"><legend>what you both loved — pick up to two</legend>' + fronts + '</fieldset>'
      + '<label class="bfield"><span>the thing neither of you actually wants</span>'
      + '<input type="text" id="b-wildcard" maxlength="40" placeholder="the karaoke machine"></label>'
      + '<label class="bfield"><span>case number — optional; same number, same divorce</span>'
      + '<input type="text" id="b-seed" inputmode="numeric" placeholder="e.g. 29"></label>'
      + '</div>'
      + '<div class="b-actions"><button id="b-file">File for divorce →</button>'
      + '<p id="b-status"></p></div>';

    // an archetype card presets the three sliders from the server listing;
    // the sliders stay adjustable afterwards
    sc.querySelectorAll('.bp-col').forEach((col) => {
      col.querySelectorAll('input[type="radio"]').forEach((r) => {
        r.addEventListener('change', () => {
          const a = archetypeInfo.archetypes[r.value];
          if (!a) return;
          for (const s of SLIDER_KEYS) {
            const el = col.querySelector('[data-slider="' + s + '"]');
            if (typeof a[s] === 'number') el.value = a[s];
            col.querySelector('[data-out="' + s + '"]').textContent = Number(el.value).toFixed(2);
          }
        });
      });
      col.querySelectorAll('input[type="range"]').forEach((el) => {
        el.addEventListener('input', () => {
          col.querySelector('[data-out="' + el.dataset.slider + '"]').textContent = Number(el.value).toFixed(2);
        });
      });
    });

    // fronts: at most two
    const boxes = Array.from(sc.querySelectorAll('.bfront input'));
    boxes.forEach((b) => b.addEventListener('change', () => {
      const n = boxes.filter((x) => x.checked).length;
      boxes.forEach((x) => { x.disabled = !x.checked && n >= 2; });
    }));

    // the wildcard's name flows into the hill dropdowns live
    $('#b-wildcard').addEventListener('input', () => {
      const v = $('#b-wildcard').value.trim();
      sc.querySelectorAll('.b-hill option[value="wildcard"]').forEach((o) => {
        o.textContent = v || 'the wildcard item';
      });
    });

    $('#b-file').addEventListener('click', fileDivorce);
  }

  async function openBuilder() {
    if (player) { player.destroy(); player = null; }
    refreshPP();
    $('#error').hidden = true;
    $('#case-chip').hidden = true;
    document.querySelectorAll('#presets button').forEach((b) => b.classList.remove('active'));
    $('#build-btn').classList.add('active');
    showScene('build');
    if (!archetypeInfo) {
      $('#scene-build').innerHTML = '<p class="kicker">intake</p>'
        + '<p id="b-status">Pulling the intake forms…</p>';
      try {
        const res = await fetch(API_BASE + '/v1/divorce/archetypes');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const info = await res.json();
        if (!info || typeof info.archetypes !== 'object' || info.archetypes === null
            || !Array.isArray(info.hillable) || info.hillable.length === 0) {
          throw new Error('malformed archetype listing');
        }
        archetypeInfo = info;
      } catch (e) {
        $('#scene-build').innerHTML = '<p class="kicker">intake</p>'
          + '<p id="b-status" class="bad">The clerk’s office is closed — start the divorce-api server. ('
          + esc(e.message) + ')</p>'
          + '<div class="b-actions"><button id="b-retry">knock again</button></div>';
        $('#b-retry').addEventListener('click', openBuilder);
        return;
      }
    }
    renderBuilder();
  }

  async function fileDivorce() {
    const status = $('#b-status');
    const readPersona = (side) => {
      const col = document.querySelector('.bp-col[data-side="' + side + '"]');
      const arch = col.querySelector('input[type="radio"]:checked');
      const p = { name: col.querySelector('.b-name').value.trim() };
      if (arch) p.archetype = arch.value;
      for (const s of SLIDER_KEYS) p[s] = parseFloat(col.querySelector('[data-slider="' + s + '"]').value);
      p.hill = col.querySelector('.b-hill').value;
      return p;
    };
    const a = readPersona('a'), b = readPersona('b');
    const wildcard = $('#b-wildcard').value.trim();
    const seedRaw = $('#b-seed').value.trim();

    const complain = (t) => { status.classList.add('bad'); status.textContent = t; };
    status.classList.remove('bad');
    if (!a.name || !b.name) return complain('The county requires a name for both parties.');
    if (!a.archetype || !b.archetype) return complain('Pick an archetype for each of them. Everyone is one of these.');
    if (!wildcard) return complain('Name the wildcard item. It matters more than you think.');
    let seed;
    if (seedRaw !== '') {
      if (!/^-?\d+$/.test(seedRaw)) return complain('Case numbers are integers.');
      seed = parseInt(seedRaw, 10);
    }
    const fronts = Array.from(document.querySelectorAll('.bfront input:checked')).map((x) => x.value);

    const body = { a, b, wildcard_label: wildcard, fronts };
    if (seed !== undefined) body.seed = seed;

    const btn = $('#b-file');
    btn.disabled = true;
    status.textContent = 'Filing. The county appreciates your patience.';

    let trace;
    try {
      const res = await fetch(API_BASE + '/v1/divorce/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      trace = await res.json();
    } catch (e) {
      btn.disabled = false;
      return complain('The clerk’s office is closed — start the divorce-api server. (' + e.message + ')');
    }
    btn.disabled = false;
    status.textContent = '';
    // If the returned trace fails validation, playTrace shows the plain error —
    // never a fake trace, never a preset in disguise.
    playTrace(trace, null);
  }

  // click/space: first press pauses into step mode; each further press
  // advances exactly one beat. The ▶ button resumes autoplay.
  function userAdvance() {
    if (!player || player.isFinished()) return;
    if (player.isPaused()) player.stepOnce();
    else player.pause();
  }

  function wireControls() {
    document.querySelectorAll('#presets button').forEach((b) => {
      b.addEventListener('click', () => loadPreset(b.dataset.preset));
    });
    $('#build-btn').addEventListener('click', openBuilder);
    $('#pp').addEventListener('click', () => {
      if (!player || player.isFinished()) return;
      if (player.isPaused()) player.resume();
      else player.pause();
    });
    $('#speed').addEventListener('click', () => {
      speedVal = speedVal === 1 ? 2 : speedVal === 2 ? 0.5 : 1;
      $('#speed').textContent = (speedVal === 0.5 ? '0.5' : String(speedVal)) + '×';
    });
    $('#skip').addEventListener('click', () => {
      if (player) instant(() => player.skipToEnd());
    });
    $('#replay').addEventListener('click', () => {
      if (currentTrace) playTrace(currentTrace, currentPreset);
    });
    $('#stage').addEventListener('click', (e) => {
      if (e.target.closest('button, a, pre, input, textarea, select, label')) return;
      userAdvance();
    });
    document.addEventListener('keydown', (e) => {
      if (e.code !== 'Space' || e.repeat) return;
      if (e.target.closest && e.target.closest('button, a, input, textarea, select, [contenteditable]')) return;
      e.preventDefault();
      userAdvance();
    });
  }

  wireControls();
  const params = new URLSearchParams(location.search);
  const initial = params.get('preset');
  loadPreset(PRESETS[initial] ? initial : 'bloodbath');

})();
