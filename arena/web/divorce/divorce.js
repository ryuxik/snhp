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

  // Relationship skins (intake option): pure DISPLAY label-maps over the same
  // six mechanical assets — exactly the mechanism wildcard_label already uses.
  // The engine sees none of this; the decree fine print says so.
  const RELATIONSHIPS = {
    marriage:      { name: 'MARRIAGE',      inre: 'THE MARRIAGE OF',      labels: null },
    roommates:     { name: 'ROOMMATES',     inre: 'THE ROOMMATES OF',
      labels: { dog: 'the couch', lake_weeks: 'the parking spot', wallet: 'the security deposit',
                vinyl: 'the good pan', espresso: 'custody of the group-chat name' } },
    cofounders:    { name: 'CO-FOUNDERS',   inre: 'THE PARTNERSHIP OF',
      labels: { dog: 'the domain name', lake_weeks: 'the office lease', wallet: 'the joint account',
                vinyl: 'the @handle', espresso: 'the espresso machine' } },
    situationship: { name: 'SITUATIONSHIP', inre: 'THE SITUATIONSHIP OF',
      labels: { dog: 'the hoodie', lake_weeks: 'the Sunday gym slot', wallet: 'the shared tab',
                vinyl: 'the playlist', espresso: 'the toothbrush drawer' } },
  };

  const HILL_RATIO = 2.5;           // HILL? chip: p50 > 2.5x its own step-0 p50

  // Act I pacing (ms at 1x). Clerk ANCHOR lines (quips, stall notes) hold 2x
  // the old durations — they were at half reading speed (usability finding).
  const TICK_MS = 220;              // one exchange line
  const TICK_SETTLE_MS = 420;       // the ✓ settled line
  const TICK_QUIP_MS = 2400;        // clerk quip after a settle
  const TICK_STALL_MS = 650;        // a repeated-offer line (broken record)
  const TICK_NOTE_MS = 2800;        // clerk note on the third identical offer
  const TICK_FASTCUT_MS = 70;       // NO DECREE: post-"record is broken" compression

  // Act II pacing: first ~3 + last ~2 questions per side at full beat
  // (+500ms vs the old cut), the middle at ~3x behind the montage card.
  const Q_FULL_MS = 3100;
  const Q_FULL_ANSWER_AT = 1600;
  const Q_FAST_MS = 950;
  const Q_FAST_ANSWER_AT = 480;

  // Live mode. Same-origin deploys set this to '' (the API mounts /v1/divorce/*).
  // Local dev: the standalone engine on :8203. Deployed: same-origin — the
  // divorce router is mounted inside the arena app (SPEC.md §11.3).
  const API_BASE = /^(localhost|127\.0\.0\.1)$/.test(location.hostname)
    ? 'http://localhost:8203' : '';

  // Playback speed multiplier: 1x / 2x. (0.5x removed — if the pacing needs a
  // slow knob, the pacing is wrong.) Scales every beat duration.
  let speedVal = 1;
  const speed = () => speedVal;

  // Reduced-motion clamps DECORATIVE animation only (CSS side). Reading beats
  // keep their full durations — capping them dumped whole acts in one frame,
  // an accessibility inversion. Here it only switches scrolling to 'auto'.
  const REDUCED = window.matchMedia
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SCROLL_BEHAVIOR = REDUCED ? 'auto' : 'smooth';

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

  function plural(n, noun) { return n + ' ' + noun + (n === 1 ? '' : 's'); }

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
    // "nobody peeked" belongs to the stamp on the decree screen — the clerk
    // doesn't pre-spend the line here.
    flipPost: '“Go ahead — check the math. Everyone does.”',
    montageQuip: '“Same church, same pew.”',
    rareLawyers: '“Item-by-item would have done fine here. Rare.”',
    whyNoZopa: '“Their floors never overlapped. Nobody would take any deal.”',
    whyAbstain: '“I couldn’t certify a deal I was sure of.”',
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
   *  receipt signature — REAL Ed25519 verification in this browser.
   *  We reconstruct the notary's canonical payload (Python json.dumps with
   *  sort_keys, no whitespace, ensure_ascii, floats keeping ".0") and check
   *  notary_sig against the receipt's embedded public key via WebCrypto.
   *  A reconstruction mismatch can only produce a false NEGATIVE — the page
   *  never claims VERIFIED without crypto.subtle.verify returning true.
   * ------------------------------------------------------------------ */

  // Python json.dumps default ensure_ascii=True: non-ASCII -> \uXXXX (lowercase)
  function pyStr(s) {
    return JSON.stringify(s).replace(/[\u0080-\uffff]/g,
      (c) => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
  }

  // Paths (of the PARENT object) whose numeric values are Python floats —
  // integral ones must render "1.0", not "1". In settlement-1 receipts that
  // is exactly settlement.shares_a.
  const FLOAT_PARENTS = new Set(['$.settlement.shares_a']);

  function canonJSON(v, path) {
    if (v === null) return 'null';
    if (typeof v === 'number') {
      if (Number.isInteger(v) && FLOAT_PARENTS.has(path.slice(0, path.lastIndexOf('.')))) {
        return v.toFixed(1);
      }
      return String(v);
    }
    if (typeof v === 'boolean') return v ? 'true' : 'false';
    if (typeof v === 'string') return pyStr(v);
    if (Array.isArray(v)) {
      return '[' + v.map((x, i) => canonJSON(x, path + '.' + i)).join(',') + ']';
    }
    const keys = Object.keys(v).sort();
    return '{' + keys.map((k) => pyStr(k) + ':' + canonJSON(v[k], path + '.' + k)).join(',') + '}';
  }

  function b64urlToBytes(s) {
    const std = s.replace(/-/g, '+').replace(/_/g, '/');
    const pad = std + '='.repeat((4 - (std.length % 4)) % 4);
    return Uint8Array.from(atob(pad), (c) => c.charCodeAt(0));
  }

  function pemToBytes(pem) {
    const b64 = pem.replace(/-----[^-]+-----/g, '').replace(/\s+/g, '');
    return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  }

  /** true / false, or throws when this browser can't do Ed25519. */
  async function verifyReceiptSig(rc) {
    if (!(window.crypto && crypto.subtle)) throw new Error('WebCrypto unavailable');
    const payload = {};
    for (const k of Object.keys(rc)) { if (k !== 'notary_sig') payload[k] = rc[k]; }
    const bytes = new TextEncoder().encode(canonJSON(payload, '$'));
    const key = await crypto.subtle.importKey(
      'spki', pemToBytes(req(rc, 'notary.pubkey_pem')), { name: 'Ed25519' }, false, ['verify']);
    return crypto.subtle.verify({ name: 'Ed25519' }, key, b64urlToBytes(req(rc, 'notary_sig')), bytes);
  }

  /* ------------------------------------------------------------------ *
   *  model — everything derived from the trace, up front
   * ------------------------------------------------------------------ */

  function deriveModel(trace, opts) {
    const m = { trace };

    m.meta = req(trace, 'meta');
    m.wildcardLabel = req(trace, 'meta.wildcard_label');
    m.engineNote = req(trace, 'meta.engine');
    m.caseNo = (m.meta.case_no != null) ? m.meta.case_no : null;   // live filings only
    // The skin is DISPLAY-only, but it must survive a case replay: a case
    // filed as ROOMMATES has to come back with the couch, not the dog, or
    // "same number, same divorce" visibly breaks for anyone who types the
    // number off a screenshot. Live opts win; otherwise the ledger's record.
    const relOpt = opts && opts.rel;
    const relMeta = m.meta.rel;
    m.rel = RELATIONSHIPS[relOpt] ? relOpt
      : (RELATIONSHIPS[relMeta] ? relMeta : 'marriage');
    m.relLabels = RELATIONSHIPS[m.rel].labels;

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
      else if (q.kind === 'linear') { req(q, 'weights'); req(q, 'sweetener'); req(q, 'answer'); }
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
    if (m.relLabels && key in m.relLabels) return m.relLabels[key];
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

  /* The share line — ONE italic sentence under the tax band, built ONLY
   * from trace fields (scorecard taxes, hill autopsy, act1/act3 counts).
   * Deterministic; this is the tweet. */
  function shareLineText(m) {
    if (m.noDecree) {
      const anyBoth = m.drafts.some((d) => d.ok_a === true && d.ok_b === true);
      return plural(m.exchanges.length, 'exchange') + '. ' + plural(m.drafts.length, 'draft') + '. '
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
    // "a $340 <noun>" only parses when the label IS a bare noun phrase — i.e.
    // it arrived as "the X". User wildcards ("his mother's painting") and skin
    // labels that aren't ("custody of the group-chat name") take the whole-label
    // form instead; the alternative renders "a $340 custody of the group-chat
    // name" in the biggest type on the card.
    const raw = cleanDisp(m, hillKey);
    if (hillKey === 'wildcard' || !/^the\s+/i.test(raw)) {
      return 'That’s ' + aOrAn(tax) + ' ' + tax + ' opinion about '
        + raw + '. Retail: ' + retail + '.';
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
   *  A step with hold:true stops autoplay until its own control calls
   *  release() — the flip's gasp beat. Skip fast-forwards to the decree.
   * ------------------------------------------------------------------ */

  function makePlayer(steps, onError, onState) {
    let i = 0, timer = null, anim = null, finished = false, paused = false;
    let holding = false, heldMs = 0;

    const completeAnim = () => { if (anim && anim.finish) anim.finish(); anim = null; };
    const state = () => { if (onState) onState(); };

    function release() {
      if (!holding) return;
      holding = false;
      if (paused) { state(); return; }           // stay in step mode
      timer = setTimeout(() => { completeAnim(); schedule(); }, heldMs / speed());
      state();
    }

    function runNext(fast) {
      const s = steps[i++];
      try {
        anim = s.run(fast, release) || null;
      } catch (e) {
        clearTimeout(timer);
        i = steps.length; finished = true; holding = false; anim = null;
        onError(e);
      }
      return s;
    }

    function schedule() {
      if (i >= steps.length) { finished = true; state(); return; }
      const s = runNext(false);
      if (s.dur === Infinity) { finished = true; state(); return; }
      if (s.hold) { holding = true; heldMs = s.dur; state(); return; }
      timer = setTimeout(() => { completeAnim(); schedule(); }, s.dur / speed());
    }

    return {
      start() { paused = false; schedule(); state(); },
      isPaused() { return paused; },
      isHolding() { return holding; },
      isFinished() { return finished; },
      release,
      pause() {
        if (finished || paused || holding) return;
        paused = true; clearTimeout(timer); completeAnim(); state();
      },
      resume() {
        if (finished || !paused) return;
        paused = false; completeAnim();
        if (!holding) schedule();
        state();
      },
      stepOnce() {
        if (finished || !paused || holding) return;
        completeAnim();
        if (i >= steps.length) { finished = true; state(); return; }
        const s = runNext(false);          // one beat, with its own animation
        if (s.dur === Infinity) finished = true;
        if (s.hold) { holding = true; heldMs = s.dur; }
        state();
      },
      skipToEnd() {
        clearTimeout(timer); completeAnim(); holding = false;
        while (i < steps.length) { runNext(true); completeAnim(); }
        finished = true; state();
      },
      destroy() { clearTimeout(timer); completeAnim(); holding = false; i = steps.length; finished = true; },
    };
  }

  /** Run parts [[offsetMs, fn], …]; fast mode runs them all now. Reading
   *  beats keep their timing under prefers-reduced-motion — only decorative
   *  CSS motion is clamped. */
  function seq(fast, parts) {
    const ran = parts.map(() => false);
    const fire = (k) => { if (!ran[k]) { ran[k] = true; parts[k][1](); } };
    if (fast) { parts.forEach((_, k) => fire(k)); return null; }
    const timers = parts.map((p, k) => setTimeout(() => fire(k), p[0] / speed()));
    return { finish() { timers.forEach(clearTimeout); parts.forEach((_, k) => fire(k)); } };
  }

  /** Suppress CSS transitions/animations while fast-forwarding. */
  function instant(fn) {
    document.body.classList.add('instant');
    fn();
    requestAnimationFrame(() => requestAnimationFrame(() => document.body.classList.remove('instant')));
  }

  /* ------------------------------------------------------------------ *
   *  scenes + the case rail. The film OWNS THE SCROLL: every scene change
   *  scrolls itself into view; reveals (flip, decree, receipt) scroll too.
   * ------------------------------------------------------------------ */

  const SCENES = ['build', 'cold', 'act1', 'turn', 'act2', 'act3', 'decree'];
  const RAIL_SEG = { act1: 'act1', turn: 'act2', act2: 'act2', act3: 'act3', decree: 'decree' };
  const RAIL_ORDER = ['act1', 'act2', 'act3', 'decree'];
  let lastScene = null;
  let posterSeen = false;      // first cold-open holds longer (premise read time)

  function showScene(key) {
    for (const s of SCENES) {
      $('#scene-' + s).classList.toggle('active', s === key);
    }
    const seg = RAIL_SEG[key] || null;
    const segIdx = seg ? RAIL_ORDER.indexOf(seg) : -1;
    document.querySelectorAll('#cr-acts i').forEach((el) => {
      const k = RAIL_ORDER.indexOf(el.dataset.seg);
      el.classList.toggle('on', seg !== null && k === segIdx);
      el.classList.toggle('done', seg !== null && k < segIdx);
    });
    if (key !== lastScene) {
      lastScene = key;
      $('#scene-' + key).scrollIntoView({ block: 'start', behavior: SCROLL_BEHAVIOR });
    }
  }

  function ownScroll(el, block) {
    if (el) el.scrollIntoView({ block: block || 'center', behavior: SCROLL_BEHAVIOR });
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
      + '<div class="p-fight">believes the judge will side with them · ' + esc(String(req(c, 'court_confidence_pct'))) + '%</div>'
      + '</div>';
  }

  function confNote(m) {
    // Data-derived, template-bound: renders ONLY when the recorded declared
    // confidences genuinely overflow — mutual optimism (M&K impediment #4)
    // is now a stated input, and the arithmetic is the joke.
    const sum = req(m.cast.A, 'court_confidence_pct') + req(m.cast.B, 'court_confidence_pct');
    if (sum <= 110) return '';
    return '<p class="conf-note">Combined confidence in victory: ' + sum
      + '%. The county notes this exceeds the available victory.</p>';
  }

  function buildColdOpen(m, steps, opts) {
    // A case the visitor JUST filed skips the tutorial: they wrote the cast
    // themselves, and 8+ seconds of static poster after pressing FILE read
    // as "nothing happened" (founder finding). Short hold, no premise.
    const justFiled = !!(opts && opts.justFiled);
    // Subtitle: the preset's card line, or — for a live filing — the case number
    // straight from the trace (meta.case_no is the county ledger's number).
    const p = PRESETS[currentPreset];
    const subline = justFiled
      ? 'FILED · CASE #' + esc(String(m.caseNo != null ? m.caseNo : req(m.meta, 'preset_seed'))) + ' — the proceedings begin.'
      : 'NOW SHOWING · ' + (p
        ? '“' + p.label + '” — ' + p.sub
        : 'CASE #' + esc(String(m.caseNo != null ? m.caseNo : req(m.meta, 'preset_seed'))) + ', filed at this window.');

    // The last clause is template-bound to the recorded ending — a NO DECREE
    // trace never promises a decree (usability finding).
    const lastClause = m.noDecree ? 'the decree is not guaranteed.' : 'the decree is inevitable.';

    $('#scene-cold').innerHTML =
      '<div class="corner-stamp">valuations sealed · ' + shortSeal(req(m.cast.A, 'seal'))
        + ' · ' + shortSeal(req(m.cast.B, 'seal')) + '</div>'
      + '<div class="cold-head"><h1>IRRECONCILABLE AGENTS</h1>'
      + '<p class="tagline">The divorce is fake. The math is real.</p>'
      // The premise used to be three paragraphs (~60 words) held for 18
      // seconds. The tagline above already does that job in eight words —
      // this is one line, and only when we haven't already said it.
      + (justFiled ? '' : '<p class="premise">Two of them. One pile of stuff. '
        + 'A court that can’t see how they feel.</p>')
      + '<p class="preset-sub">' + subline + '</p></div>'
      + '<div class="versus">' + portraitHTML(m, 'A', 'p-a')
      + '<div class="vs">vs</div>' + portraitHTML(m, 'B', 'p-b') + '</div>'
      + confNote(m)
      + '<p class="hint">click / space pauses, then steps one beat at a time · ▶ resumes · ' + lastClause + '</p>';

    // One line instead of three paragraphs means the poster no longer needs
    // an 18-second hold to be readable — it was a loading screen made of
    // prose. A just-filed case gets a beat to register its case number.
    const dur = justFiled ? 4000 : 6000;
    posterSeen = true;
    steps.push({ scene: 'cold', dur, run() { showScene('cold'); } });
  }

  function buildAct1(m, steps) {
    $('#scene-act1').innerHTML =
      '<div class="act-head"><div class="act-slab">ACT I</div>'
      + '<div class="act-sub">“your lawyers’ way” — billed hourly</div></div>'
      + '<div id="ticker-wrap"><span id="x-counter"></span>'
      + '<div id="ticker-scroll"><ul id="ticker"></ul></div></div>'
      + '<div id="freeze" hidden></div>'
      + '<p id="act1-summary" hidden></p>';

    // Ticker lines: one per real exchange. Milestones come FROM the log:
    //  - an accepted offer gets a ✓ line plus a clerk quip (counts from trace)
    //  - the 3rd occurrence of an identical offer (proposer+asset+share+transfer)
    //    starts the broken-record stretch: repeats slow down, pile up, and the
    //    clerk notes it once. Detection is pure data; no line is invented.
    // NO DECREE cut: once the clerk has called the broken record, the rest of
    // the log compresses hard — same real lines, faster — so the freeze-frame
    // arrives before the joke wears out (CMO finding). The nodecree variant
    // order leads with "Same numbers again. The record is broken."
    const lines = [];
    let n = 0, settledSoFar = 0, stallNotes = 0, fastCut = false;
    const offerCount = new Map();
    for (const ex of m.exchanges) {
      n += 1;
      const key = [req(ex, 'proposer'), req(ex, 'asset'), req(ex, 'share_a'), req(ex, 'transfer')].join('|');
      const c = (offerCount.get(key) || 0) + 1;
      offerCount.set(key, c);
      const stall = c >= 3;
      const ms = fastCut ? (stall ? 2 * TICK_FASTCUT_MS : TICK_FASTCUT_MS)
        : (stall ? TICK_STALL_MS : TICK_MS);
      lines.push({ text: exchangeLine(m, ex), cls: stall ? 'stall' : '', n, ms });
      if (c === 3) {
        lines.push({ text: pick(VOICE.stallNote, stallNotes + (m.noDecree ? 1 : 0)), cls: 'clerk-note', n, ms: TICK_NOTE_MS });
        stallNotes += 1;
        if (m.noDecree) fastCut = true;
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
        if (fast) { while (shown < lines.length) push(); settle(); return null; }
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
        dur: 4500,
        run() {
          const f = $('#freeze');
          f.hidden = false;
          f.innerHTML = '<div class="f-asset">' + esc(assetDisp(m, worst)) + '</div>'
            + '<div class="f-stat">' + count + ' EXCHANGES · 0 PROGRESS</div>'
            + '<div class="f-cap">' + esc(pick(VOICE.freezeCap, count)) + '</div>';
          ownScroll(f, 'nearest');
        },
      });
    }

    const settledCount = m.assetCount - m.unsettled.length;
    steps.push({
      scene: 'act1',
      dur: 4500,
      run() {
        const el = $('#act1-summary');
        el.hidden = false;
        const garnish = m.unsettled.length > 0
          ? pick(VOICE.act1Rest, m.exchanges.length)
          : VOICE.act1AllSettled;
        el.innerHTML = esc(settledCount + ' of ' + m.assetCount + ' assets settled after '
          + m.exchanges.length + ' exchanges.')
          + '<br><span class="s-clerk">' + esc(garnish) + '</span>';
        ownScroll(el, 'nearest');
      },
    });
  }

  function buildTurn(m, steps) {
    $('#scene-turn').innerHTML =
      '<span class="clerk-plate">MEDIATOR — window 4 · no appointments</span>'
      + '<p id="turn-line">“I have some questions.”</p>'
      + '<p id="turn-line2">“Both of you. Separately.”</p>'
      // The mechanism, said ONCE, plainly (usability finding #1):
      + '<p id="turn-mech">No prices. Just choices. The clerk works out what things are worth.</p>';
    steps.push({
      scene: 'turn',
      dur: 8600,
      run(fast) {
        showScene('turn');
        return seq(fast, [
          [900, () => { $('#turn-line').classList.add('shown'); }],
          [2500, () => { $('#turn-line2').classList.add('shown'); }],
          [4600, () => { $('#turn-mech').classList.add('shown'); }],
        ]);
      },
    });
  }

  function bandPanelHTML(m, side) {
    const rows = BAND_ASSETS.map((a) =>
      '<div class="band-row" data-asset="' + a + '">'
      + '<div class="b-head"><span>' + esc(assetDisp(m, a))
      + ' <span class="hill-chip" title="the item they won’t trade — detected from answers alone" hidden>HILL?</span></span>'
      + '<span class="b-med"></span></div>'
      + '<div class="b-track" hidden><div class="b-outer"></div><div class="b-inner"></div><div class="b-tick"></div></div>'
      + '</div>').join('');
    return '<div class="band-panel" data-side="' + side + '">'
      + '<h3>' + esc(m.names[side]) + '</h3>'
      + '<div class="band-sub">what ' + esc(m.names[side]) + '’s answers imply each item is worth</div>'
      + rows + '</div>';
  }

  function buildAct2(m, steps) {
    $('#scene-act2').innerHTML =
      '<div class="act-head"><div class="act-slab">ACT II</div>'
      + '<div class="act-sub">the interview — one of you at a time</div></div>'
      + '<div id="act2-grid">'
      + '<div id="dialogue-wrap"><div id="dialogue"></div>'
      + '<div id="montage-card" hidden><div class="mc-range"></div>'
      + '<div class="mc-quip">' + esc(VOICE.montageQuip) + '</div></div></div>'
      + '<div id="bands">' + bandPanelHTML(m, 'A') + bandPanelHTML(m, 'B')
      + '<div id="bands-legend">thick bar: likely range · tick: best estimate</div>'
      + '</div></div>';

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
        row.querySelector('.b-med').textContent = 'est. ' + fmtCompact(b[2]);
      }
      // name flash: which spouse's numbers just moved (usability finding #3)
      const h3 = panel.querySelector('h3');
      h3.classList.remove('bump'); void h3.offsetWidth; h3.classList.add('bump');
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

    // Montage plan: per side, the first 3 and last 2 questions play at full
    // beat; the middle runs at ~3x behind a clerk card whose question range
    // comes from the ACTUAL trace length (CMO pacing finding). Sides with
    // five or fewer questions have no middle to montage.
    const isFull = [];
    const sideSeen = { A: 0, B: 0 };
    for (const t of m.turns) {
      const len = m.traceQ[t.side].length;
      const idx = sideSeen[t.side]++;
      isFull.push(len <= 5 || idx < 3 || idx >= len - 2);
    }

    m.turns.forEach((turn, k) => {
      const { side, q } = turn;
      const qNum = k + 1;
      const who = m.names[side];
      const full = isFull[k];
      const montageStart = !full && (k === 0 || isFull[k - 1]);
      const montageEnd = !full && (k === m.turns.length - 1 || isFull[k + 1]);

      if (montageStart) {
        let end = k;
        while (end < m.turns.length && !isFull[end]) end++;
        const range = 'Questions ' + (k + 1) + '–' + end + '.';
        steps.push({
          scene: 'act2',
          dur: 2600,
          run() {
            showScene('act2');
            const card = $('#montage-card');
            card.querySelector('.mc-range').textContent = range;
            card.hidden = false;
          },
        });
      }

      steps.push({
        scene: 'act2',
        dur: full ? Q_FULL_MS : Q_FAST_MS,
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
                ? cap(disp) + ', or ' + fmtPrice(price) + ' more of ' + cleanDisp(m, 'wallet') + '?'
                  + pick(VOICE.probeWalletTail, qNum)
                : 'If the settlement paid you ' + fmtPrice(price)
                  + ' to give up ' + disp + ' — take it?'
                  + pick(VOICE.probeBuyoutTail, qNum);
              say('clerk', lead + offer);
            } else if (q.kind === 'pair') {
              say('clerk', lead + cap(assetDisp(m, req(q, 'A')))
                + ', or ' + assetDisp(m, req(q, 'B')) + '?'
                + pick(VOICE.pairTail, qNum));
            } else if (q.kind === 'linear') {
              // v2 all-choices interview: every question is a package choice
              // u(A)-u(B) = sum(weights*v)+sweetener. Cash appears only as a
              // rider inside a package — same registered trade-offer rule.
              const ws = req(q, 'weights');
              const sw = req(q, 'sweetener');
              const aSide = Object.keys(ws).filter((x) => ws[x] > 0).map((x) => assetDisp(m, x));
              const bSide = Object.keys(ws).filter((x) => ws[x] < 0).map((x) => assetDisp(m, x));
              if (bSide.length === 0 && sw < 0) {
                // pure cash-for-asset trade — the probe skeletons apply
                const t = Math.abs(sw);
                const disp = aSide.join(' and ');
                const offer = t <= 24000
                  ? cap(disp) + ', or ' + fmtPrice(t) + ' more of ' + cleanDisp(m, 'wallet') + '?'
                    + pick(VOICE.probeWalletTail, qNum)
                  : 'If the settlement paid you ' + fmtPrice(t)
                    + ' to give up ' + disp + ' — take it?'
                    + pick(VOICE.probeBuyoutTail, qNum);
                say('clerk', lead + offer);
              } else {
                let left = aSide.join(' and ');
                let right = bSide.join(' and ');
                if (sw > 0) left += (left ? ' plus ' : '') + fmtPrice(sw);
                if (sw < 0) right += (right ? ' plus ' : '') + fmtPrice(Math.abs(sw));
                say('clerk', lead + cap(left) + ' — or ' + right + '?'
                  + pick(VOICE.pairTail, qNum));
              }
            } else {
              throw new Error('unknown question kind "' + q.kind + '" in trace');
            }
          }]);
          parts.push([full ? Q_FULL_ANSWER_AT : Q_FAST_ANSWER_AT, () => {
            let ans;
            if (q.kind === 'probe') {
              ans = q.answer === true ? 'Yes.' : 'No.';
            } else if (q.kind === 'linear') {
              const ws = q.weights;
              const aSide = Object.keys(ws).filter((x) => ws[x] > 0).map((x) => assetDisp(m, x));
              const bSide = Object.keys(ws).filter((x) => ws[x] < 0).map((x) => assetDisp(m, x));
              if (bSide.length === 0 && q.sweetener < 0) {
                ans = q.answer === true ? 'Yes.' : 'No.';   // took/refused the trade
              } else if (q.answer === true) {
                ans = cap(aSide.join(' and ')) + '.';
              } else {
                ans = bSide.length ? cap(bSide.join(' and ')) + '.' : 'The money.';
              }
            } else if (q.answer === 'A') ans = cap(assetDisp(m, q.A)) + '.';
            else if (q.answer === 'B') ans = cap(assetDisp(m, q.B)) + '.';
            else ans = 'Neither.'; // pair answer "walk" (never invented; schema event type)
            say('reply', who + ': “' + ans + '”');
            const revealedHill = updateBands(side, req(q, 'bands'), req(q, 'step'));
            // deterministic clerk punctuation, keyed only to real events:
            // a hill detection, a refusal, an answer landing on the cadence.
            const cashDecline = q.answer === false
              && (q.kind === 'probe'
                  || (q.kind === 'linear' && q.sweetener < 0
                      && Object.values(q.weights).every((w) => w > 0)));
            if (revealedHill) say('aside', pick(VOICE.hill, hillSeen++));
            else if (cashDecline && k % 7 === 5) say('aside', 'That’s what they all say.');
            else if (q.kind === 'pair' && ans === 'Neither.') say('aside', 'Neither. Bold.');
            else if (k % 5 === 4) say('aside', pick(VOICE.ack, Math.floor(k / 5)));
          }]);
          return seq(fast, parts);
        },
      });

      if (montageEnd) {
        steps.push({
          scene: 'act2',
          dur: 400,
          run() { $('#montage-card').hidden = true; },
        });
      }
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
      + '<div class="fd-name">' + esc(m.names[side]) + '</div>'
      + '</div>'
      + '<div class="flip-face flip-back">'
      + '<h4>' + esc(m.names[side]) + ' — true valuations</h4>'
      + rows
      + '<div class="fv-row fv-strong"><span>walk-away</span><span class="fv-val">'
      + fmtMoney(req(f, 'walk_away')) + '</span></div>'
      + '<div class="fv-row"><span>SPITE</span><span class="fv-val">' + req(p, 'lam') + '</span></div>'
      + '<div class="fv-seal">' + esc(req(f, 'seal')) + '</div>'
      + '<div class="verify-result" data-side="' + side + '"></div>'
      + '</div></div></div>';
  }

  function verifyRowHTML() {
    return '<div class="verify-row"><button class="verify-btn">verify seals</button>'
      + '<div class="verify-note">sha-256 of each revealed payload, recomputed in your browser, vs the seal stamped at t0</div></div>';
  }

  function buildAct3(m, steps) {
    $('#scene-act3').innerHTML =
      '<div class="act-head"><div class="act-slab">ACT III</div>'
      + '<div class="act-sub">paperwork, then the flip</div></div>'
      + '<div id="act3-grid"><div id="drafts"></div><div id="act3-clerk"></div>'
      + '<div id="flip-area" class="proof-scope" hidden>'
      + '<div class="flip-grid">' + flipCardHTML(m, 'A') + flipCardHTML(m, 'B') + '</div>'
      + '<div id="flip-cta-row"><button id="flip-cta" hidden>flip them</button></div>'
      + verifyRowHTML()
      + '</div>';

    const clerkLine = (t) => { $('#act3-clerk').textContent = t; };
    let walkGlossUsed = false;

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
          div.scrollIntoView({ block: 'nearest', behavior: SCROLL_BEHAVIOR });
        },
      });

      steps.push({
        scene: 'act3',
        dur: 4200,
        run(fast) {
          const div = $('#drafts').lastElementChild;
          const sign = (side, ok, v) => () => {
            const slot = div.querySelector('.sig[data-side="' + side + '"]');
            if (ok) {
              slot.querySelector('.s-mark').innerHTML = sigMarkSVG();
              slot.querySelector('.s-verdict').textContent = pick(VOICE.signed, v);
            } else {
              // caption: WHY a refusal happens (usability finding #9) — the
              // engine refuses exactly when the draft falls below that side's
              // declared walk-away basis. Walk-away glossed once, plainly.
              const gloss = walkGlossUsed ? '' : ' <i class="walk-gloss">(the point where court beats the deal)</i>';
              walkGlossUsed = true;
              slot.querySelector('.s-verdict').innerHTML = '<span class="refused">REFUSED.</span>'
                + '<span class="refuse-cap">below ' + esc(m.names[side]) + '’s walk-away' + gloss + '</span>';
            }
          };
          const parts = [[400, sign('A', okA, i)], [1500, sign('B', okB, i + 1)]];
          if (!okA && !okB) parts.push([2400, () => clerkLine(VOICE.bothRefuse)]);
          else if (!okA || !okB) parts.push([2400, () => clerkLine(pick(VOICE.refuse, i))]);
          else parts.push([2400, () => clerkLine(pick(VOICE.ratify, i))]);
          return seq(fast, parts);
        },
      });
    });

    // THE FLIP — the gasp. The film auto-pauses on the sealed cards (a hold
    // step); the audience turns them over with one button. Skip and
    // fast-forward flip instantly.
    steps.push({
      scene: 'act3',
      dur: 2600,
      run() {
        clerkLine(m.noDecree ? VOICE.flipPreNoDecree : VOICE.flipPre);
        $('#flip-area').hidden = false;
        ownScroll($('#flip-area'), 'center');
      },
    });
    const flipNow = () => {
      document.querySelectorAll('#flip-area .flipcard').forEach((c) => c.classList.add('flipped'));
    };
    steps.push({
      scene: 'act3',
      dur: 1500,               // post-release: let the cards finish turning
      hold: true,
      run(fast, release) {
        if (fast) { flipNow(); return null; }
        const b = $('#flip-cta');
        b.hidden = false;
        ownScroll($('#flip-area'), 'center');
        b.onclick = (ev) => {
          ev.stopPropagation();
          b.hidden = true;
          flipNow();
          release();
        };
        return null;
      },
    });
    steps.push({
      scene: 'act3',
      dur: 5200,
      run() { clerkLine(VOICE.flipPost); },
    });
  }

  async function verifySeals(m, root) {
    const btn = root.querySelector('.verify-btn');
    btn.disabled = true;
    for (const side of ['A', 'B']) {
      const out = root.querySelector('.verify-result[data-side="' + side + '"]');
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
    return '<svg width="64" height="70" viewBox="0 0 140 150" fill="none" stroke="#1b1a17" '
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
    // The stamp OWNS "nobody peeked" on the decree screen — and it's a real
    // door: clicking it reopens the flip-and-verify panel, permanently.
    return '<button class="stamp" title="sealed before the first question — click to check them yourself">'
      + '<span class="st-top">NOBODY PEEKED</span>'
      + '<span class="st-sub">verified · snhp</span></button>';
  }

  /** Decree ledger lines carry NAMES, never pronouns — "hers/his" maps to
   *  nobody once the parties are user-named (usability finding). The 🐕
   *  emoji stays in the film; the decree ledger prints clean type. */
  function ledgerRowsHTML(m, shares) {
    const rows = [];
    for (const a of ASSET_ORDER) {
      const s = req(shares, a);
      const disp = cleanDisp(m, a);
      let val;
      if (a === 'wallet' && s > 0 && s < 1) {
        val = fmtMoney(s * m.walletTotal) + ' ' + m.names.A + ' · ' + fmtMoney((1 - s) * m.walletTotal) + ' ' + m.names.B;
      } else if (a === 'dog' && s === 0.5) {
        val = 'alternating custody.';
      } else if (s === 1) val = m.names.A + '’s.';
      else if (s === 0) val = m.names.B + '’s.';
      else val = pct(s) + '% ' + m.names.A + ' · ' + pct(1 - s) + '% ' + m.names.B + '.';
      rows.push('<div class="lg-row"><span class="lg-asset">' + esc(disp) + '</span> — ' + esc(val) + '</div>');
    }
    return rows.join('');
  }

  /** CASE line printed ON the cream (CMO: the chip crops out of screenshots;
   *  the number is the door). Presets are bundled archive traces — no ledger
   *  entry exists for them, so they never claim "same number, same divorce". */
  function caseLineHTML(m) {
    if (m.caseNo != null) {
      return '<div class="dc-case">CASE #' + esc(String(m.caseNo)) + ' — same number, same divorce.</div>';
    }
    return '<div class="dc-case">county archive — seed ' + esc(String(req(m.meta, 'preset_seed'))) + '</div>';
  }

  function taxBandHTML(label, numHTML) {
    return '<div class="dc-taxband"><div class="dc-tax-label">' + label + '</div>'
      + '<div class="dc-tax-num">' + numHTML + '</div></div>';
  }

  function buildDecree(m, steps, opts) {
    const sc = $('#scene-decree');
    const inre = 'IN RE: ' + esc(RELATIONSHIPS[m.rel].inre) + ' '
      + esc(m.names.A.charAt(0).toUpperCase()) + '. &amp; '
      + esc(m.names.B.charAt(0).toUpperCase()) + '.';
    const relNote = m.rel !== 'marriage'
      ? ' · county standard estate, relabeled for this filing' : '';

    let cardHTML, belowHTML;
    const shareRow = '<div class="dc-share"><span class="share-text" id="share-line">'
      + esc(shareLineText(m)) + '</span>'
      + '<button id="share-copy" title="copy the line">COPY THE LINE</button></div>';

    // ONE action under the card. The decree is the best screen in the product
    // and it used to offer six competing exits — none of which was "make your
    // own", the only one that turns a viewer into someone holding a case
    // number. Everything else is a quiet text link underneath (Jobs review).
    const filedThis = sessionFiled && currentPreset === null;
    const primary = filedThis
      ? '<button id="send-btn" class="primary">SEND IT TO THEM</button>'
      : '<button id="mine-btn" class="primary">FILE YOUR OWN →</button>';
    const small = [];
    if (opts && opts.toEnd) small.push('<a href="#" id="watch-link">watch how it happened</a>');
    if (filedThis) small.push('<a href="#" id="again-link">file another</a>');
    const actionsHTML = '<div id="post-actions">' + primary + '</div>'
      + (small.length ? '<p class="dc-small">' + small.join(' · ') + '</p>' : '')
      + '<p id="science-link"><a href="science.html">the math, measured →</a></p>';

    if (m.noDecree) {
      const why = m.decree.no_zopa ? VOICE.whyNoZopa : VOICE.whyAbstain;
      cardHTML =
        '<div id="decree-card" class="nodecree">'
        + '<div class="dc-head"><div class="dc-title">FINAL DECREE</div>'
        + '<div class="dc-inre">' + inre + '</div></div>'
        + '<div class="dc-nodecree">NO DECREE.</div>'
        + '<div class="dc-lines">'
        + '<p>' + m.assetCount + ' assets. ' + plural(m.exchanges.length, 'exchange') + '. '
        + plural(m.totalInterview, 'question') + '. ' + plural(m.drafts.length, 'draft') + '.</p>'
        + '<p class="dc-why">' + esc(why) + '</p>'
        + '</div>'
        + taxBandHTML('PETTINESS TAX', 'EVERYTHING.')
        + shareRow
        + '<div class="dc-bottom"><div class="dc-dog">' + dogSVG() + '</div>' + stampHTML() + '</div>'
        + caseLineHTML(m)
        + '<div class="dc-fine">valuations sealed · ' + shortSeal(m.flip.A.seal) + ' · '
        + shortSeal(m.flip.B.seal) + ' · no decree issued' + relNote + '</div>'
        + '</div>';
      belowHTML = actionsHTML;
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
        + ' · ' + shortSeal(req(rc, 'inputs.digest_b')) + ratifiedLine + relNote;

      cardHTML =
        '<div id="decree-card">'
        + '<div class="dc-head"><div class="dc-title">FINAL DECREE</div>'
        + '<div class="dc-inre">' + inre + '</div></div>'
        + '<div class="ledger">' + ledgerRowsHTML(m, m.sharesA) + '</div>'
        + taxBandHTML('PETTINESS TAX', esc(fmtMoney(tax)))
        + '<div class="dc-tax-sub">(' + esc(loserName) + ', dying on ' + esc(hillTitle(m, req(autopsy, 'hill')))
        + ' Hill — retail ' + fmtMoney(req(autopsy, 'retail')) + ')'
        + ' — what ' + esc(loserName) + '’s feelings cost at the table</div>'
        + shareRow
        + '<div class="dc-bottom"><div class="dc-dog">' + dogSVG() + '</div>' + stampHTML() + '</div>'
        + caseLineHTML(m)
        + '<div class="dc-fine">' + fine + '</div>'
        + '</div>';

      // Scoreboard keeps ONE line: what the lawyers' way cost (or didn't —
      // the rare reversal gets the clerk's flattest respect).
      const delta = req(s, 'joint_surplus') - req(s, 'arm_i_joint_surplus');
      const lawyersBit = delta > 0
        ? 'the lawyers’ way left ' + fmtMoney(delta) + ' on the table'
        : 'the lawyers’ way came out ' + fmtMoney(-delta) + ' ahead here';
      const totalTax = taxA + taxB;
      const closing = totalTax < 1000
        ? '<p id="closing-line">Nothing much set on fire. Was it ever love?</p>' : '';

      belowHTML =
        '<div id="scoreboard">' + esc(lawyersBit) + '</div>'
        + (delta <= 0 ? '<p id="rare-line">' + esc(VOICE.rareLawyers) + '</p>' : '')
        + closing
        + '<div id="receipt-row"><button id="rc-toggle">view receipt</button>'
        + '<div id="rc-panel" hidden>'
        + '<p class="rc-line">engine <span class="mono">' + esc(req(rc, 'engine_version')) + '</span>'
        + ' · two sealed digests · signature <span id="rc-sig" class="mono">checking…</span>'
        + ' — computed from the interviews alone, checkable by replay</p>'
        + '<div class="rc-settle">' + ledgerRowsHTML(m, req(rc, 'settlement.shares_a')) + '</div>'
        + '<p class="rc-counts">' + rcCountsText(m) + '</p>'
        + '<button id="rc-dev">for developers</button>'
        + '<pre id="rc-json"></pre>'
        + '</div></div>'
        + actionsHTML;
    }

    // The proof panel: the flip, permanently reopenable from the stamp.
    const proofHTML =
      '<div id="proof-panel" class="proof-scope" hidden>'
      + '<div class="pp-head">sealed before the first question — check them yourself</div>'
      + '<div class="flip-grid">' + flipCardHTML(m, 'A') + flipCardHTML(m, 'B') + '</div>'
      + verifyRowHTML()
      + '</div>';

    sc.innerHTML = '<p class="kicker">' + (m.noDecree ? 'no decree' : 'the decree') + '</p>'
      + cardHTML + proofHTML + belowHTML;

    // --- wiring ---------------------------------------------------------
    sc.querySelector('.stamp').addEventListener('click', (ev) => {
      ev.stopPropagation();
      const p = $('#proof-panel');
      if (p.hidden) {
        p.hidden = false;
        requestAnimationFrame(() => requestAnimationFrame(() => {
          p.querySelectorAll('.flipcard').forEach((c) => c.classList.add('flipped'));
        }));
      }
      ownScroll(p, 'center');
    });

    if (!m.noDecree) {
      $('#rc-json').textContent = JSON.stringify(m.receipt, null, 2);
      let sigChecked = false;
      $('#rc-toggle').addEventListener('click', () => {
        const el = $('#rc-panel');
        el.hidden = !el.hidden;
        $('#rc-toggle').textContent = el.hidden ? 'view receipt' : 'hide receipt';
        if (!el.hidden) {
          ownScroll(el, 'center');
          if (!sigChecked) { sigChecked = true; runSigCheck(m); }
        }
      });
      $('#rc-dev').addEventListener('click', () => {
        const j = $('#rc-json');
        j.classList.toggle('open');
        if (j.classList.contains('open')) ownScroll(j, 'nearest');
      });
    }

    const mine = $('#mine-btn');
    if (mine) mine.addEventListener('click', (ev) => { ev.stopPropagation(); openBuilder(); });
    const again = $('#again-link');
    if (again) {
      again.addEventListener('click', (ev) => {
        ev.preventDefault(); ev.stopPropagation();
        wiz.step = 0;                       // straight back to question one
        openBuilder();
      });
    }
    const watchLink = $('#watch-link');
    if (watchLink) {
      watchLink.addEventListener('click', (ev) => {
        ev.preventDefault(); ev.stopPropagation();
        playTrace(currentTrace, currentPreset, { rel: currentOpts.rel });
      });
    }
    // SEND IT TO THEM: one string that works as a paste AND as a screenshot
    // caption — the line alone was half a share (it pointed nowhere).
    const sendBtn = $('#send-btn');
    if (sendBtn) {
      sendBtn.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const parts = [shareLineText(m)];
        if (m.caseNo != null) {
          parts.push('CASE #' + m.caseNo + ' · arena.snhp.dev/divorce');
        }
        const text = parts.join('\n');
        const done = () => {
          sendBtn.textContent = 'COPIED — NOW PASTE IT';
          setTimeout(() => { sendBtn.textContent = 'SEND IT TO THEM'; }, 1800);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, done);
        } else { done(); }
      });
    }

    // the share line's copy affordance — clipboard if available, else select
    // it and SAY what to press (silent fallback was undiscoverable).
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
        copyBtn.textContent = 'COPIED';
        setTimeout(() => { copyBtn.textContent = 'COPY THE LINE'; }, 1200);
      };
      const manual = () => { selectShare(); copyBtn.textContent = 'PRESS ⌘C'; };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, manual);
      } else {
        manual();
      }
    });

    steps.push({
      scene: 'decree',
      dur: Infinity,
      run() {
        showScene('decree');
        ownScroll($('#decree-card'), 'start');
      },
    });
  }

  /** Reconciled totals (usability: "Question 1 of 20" vs "24 questions").
   *  Interview count = the two transcripts; ratification votes = one per
   *  side per draft; the receipt's n_questions counts both. */
  function rcCountsText(m) {
    const rat = m.drafts.length;
    let t = plural(m.totalInterview, 'interview question')
      + ' (' + m.traceQ.A.length + ' each)'
      + ' + ' + rat + ' ratification ' + (rat === 1 ? 'vote' : 'votes') + ' per side'
      + ' · ' + plural(m.drafts.length, 'draft');
    if (m.totalInterview + 2 * rat !== m.nQuestions) {
      t += ' · ' + m.nQuestions + ' total on the receipt';   // surfaced, never papered over
    }
    return esc(t);
  }

  async function runSigCheck(m) {
    const out = $('#rc-sig');
    if (!out) return;
    try {
      const ok = await verifyReceiptSig(m.receipt);
      out.textContent = ok ? '✓ VERIFIED' : '✗ DOES NOT VERIFY';
      out.className = 'mono ' + (ok ? 'v-ok' : 'v-bad');
      out.title = ok
        ? 'Ed25519 over the canonical receipt payload, checked in this browser against the receipt’s public key'
        : 'the recomputed canonical payload does not match this signature';
    } catch (e) {
      // an honest shrug, never a fake checkmark
      out.textContent = 'on file — this browser can’t check Ed25519';
      out.className = 'mono';
      out.title = String(e.message || e);
    }
  }

  /* ------------------------------------------------------------------ *
   *  boot / chrome state
   * ------------------------------------------------------------------ */

  let player = null;
  let currentPreset = null;   // preset key, or null for a live filing / case replay
  let currentTrace = null;    // last successfully played trace (for replay)
  let currentOpts = {};       // { toEnd, rel } of the current playback
  let currentModel = null;    // model of the current film (verify buttons)
  let sessionFiled = false;   // has THIS session filed a case?
  let archetypeInfo = null;   // cached GET /v1/divorce/archetypes
  let builderReady = false;   // intake DOM built once; state persists across tabs
  let builderRel = 'marriage';

  function refreshPP() {
    const b = $('#pp'), skip = $('#skip'), chip = $('#pause-chip');
    const active = !!player && !player.isFinished();
    b.disabled = !active || player.isHolding();
    skip.disabled = !active;
    b.innerHTML = (player && player.isPaused()) ? '&#9205;' : '&#9208;';
    b.title = (player && player.isPaused()) ? 'resume autoplay' : 'pause — then clicks step one beat';
    chip.hidden = !(active && player.isPaused());
  }

  function showError(msg) {
    for (const s of SCENES) $('#scene-' + s).classList.remove('active');
    $('#case-rail').hidden = true;
    $('#pause-chip').hidden = true;
    const el = $('#error');
    el.hidden = false;
    el.textContent = msg;
  }

  function setRail(m) {
    $('#cr-case').textContent = m.caseNo != null
      ? 'CASE #' + m.caseNo
      : 'ARCHIVE · SEED ' + req(m.meta, 'preset_seed');
    $('#cr-names').textContent = m.names.A.toUpperCase() + ' v. ' + m.names.B.toUpperCase();
    $('#case-rail').hidden = false;
  }

  function buildFilm(trace, opts) {
    const m = deriveModel(trace, opts);
    $('#engine-note').textContent = m.engineNote;
    const steps = [];
    buildColdOpen(m, steps, opts);
    buildAct1(m, steps);
    buildTurn(m, steps);
    buildAct2(m, steps);
    buildAct3(m, steps);
    buildDecree(m, steps, opts);
    return { m, steps };
  }

  /** Play a validated trace: presets, live filings and case replays share
   *  this one path. opts.toEnd shows the DECREE FIRST (case-number arrivals
   *  must not be 65 seconds from the payoff); "watch how it happened" then
   *  plays the film. */
  function playTrace(trace, presetKey, opts) {
    opts = opts || {};
    currentPreset = presetKey;
    currentTrace = trace;
    currentOpts = opts;
    document.querySelectorAll('#presets button').forEach((b) => {
      b.classList.toggle('active', b.dataset.preset === presetKey);
    });
    $('#build-btn').classList.remove('active');
    $('#playctl').hidden = false;
    if (player) { player.destroy(); player = null; }
    $('#error').hidden = true;
    lastScene = null;

    let film;
    try {
      film = buildFilm(trace, opts);
    } catch (e) {
      showError('Trace failed validation — ' + e.message
        + '\n\nNothing is rendered from a broken trace: no fallbacks, no invented numbers.');
      refreshPP();
      return;
    }
    currentModel = film.m;
    setRail(film.m);

    player = makePlayer(film.steps, (e) => {
      showError('Playback halted — ' + e.message
        + '\n\nNothing is rendered from a broken trace: no fallbacks, no invented numbers.');
      refreshPP();
    }, refreshPP);

    if (opts.toEnd) {
      instant(() => player.skipToEnd());
      ownScroll($('#decree-card'), 'start');
    } else {
      player.start();
    }
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

  /** ?case=N — the printed number IS the door. Decree first, film on demand. */
  async function loadCase(n) {
    if (player) { player.destroy(); player = null; }
    refreshPP();
    $('#error').hidden = true;

    let trace;
    try {
      const res = await fetch(API_BASE + '/v1/divorce/case/' + n);
      if (!res.ok) {
        let detail = null;
        try { const j = await res.json(); if (j && typeof j.detail === 'string') detail = j.detail; } catch (_e) { /* fall through */ }
        showError('CASE #' + n + ' — ' + (detail || ('the county returned HTTP ' + res.status + '.')));
        return;
      }
      trace = await res.json();
    } catch (e) {
      showError('The clerk’s office is unreachable — ' + e.message
        + '\n\nCase replays come from the live ledger; there is nothing honest to show without it.');
      return;
    }
    playTrace(trace, null, { toEnd: true });
  }

  /* ------------------------------------------------------------------ *
   *  BUILD YOUR EXES — the live mode. The form posts to the divorce API
   *  and plays back whatever trace the engine actually produced. If the
   *  office is closed, it says so; it never invents a trace and never
   *  quietly substitutes a preset. Form state persists across tabs and
   *  filings — "AMEND THE FILING" returns here, pre-filled.
   * ------------------------------------------------------------------ */

  const FRONTABLE = ['dog', 'vinyl', 'wildcard']; // per the API contract
  const SLIDER_KEYS = ['pettiness', 'spite', 'patience'];
  const WILDCARD_MAX = 40;
  // Matches the CSS mobile breakpoint; read once when the intake is built.
  const IS_NARROW = window.matchMedia('(max-width: 720px)').matches;

  function relLabelFor(key, wildcardText) {
    if (key === 'wildcard') return wildcardText || 'the wildcard item';
    const L = RELATIONSHIPS[builderRel].labels;
    if (L && key in L) return L[key];
    const n = FIXED_NAMES[key];
    return n ? n.replace(/\s*\u{1F415}\s*/gu, ' ').trim() : key;
  }

  /* ------------------------------------------------------------------ *
   *  THE INTAKE — four screens, one action each.
   *
   *  Jobs review (2026-07-18): the old intake was 2,076px / 30 controls on a
   *  phone and asked the visitor to do the product's job. Deleted outright:
   *  the six sliders (the archetype already implies them, and says it better
   *  in seven words than "spite 0.45" ever will), both hill dropdowns (you
   *  cannot stage a surprise for the person who wrote it — the client rolls
   *  it now, so Act IV's flip is a real reveal), the fronts checkboxes (the
   *  client always sends dog + the item they typed, which is strictly better
   *  than asking), and the seed field (a debug control on a consumer page;
   *  the case number already does reproducibility, better).
   *
   *  Everything deleted is still SENT — derived here, not asked for. Zero
   *  server changes: the /v1/divorce/run contract is unchanged.
   * ------------------------------------------------------------------ */

  const WIZ_STEPS = 4;
  const wiz = { step: 0, a: { name: 'Dana', archetype: null },
                b: { name: 'Morgan', archetype: null }, item: '' };

  /** The five archetype cards — one tap is the whole decision. */
  function archCardsHTML(side) {
    return '<div class="wz-cards">' + Object.keys(archetypeInfo.archetypes).map((k) =>
      '<button type="button" class="wz-card" data-arch="' + esc(k) + '">'
      + '<span class="ac-name">' + esc(k.replace(/_/g, ' ')) + '</span>'
      + (EPITHETS[k] ? '<span class="ac-epi">' + esc(EPITHETS[k]) + '</span>' : '')
      + '</button>').join('') + '</div>';
  }

  function wizDots() {
    let s = '<div class="wz-dots" aria-hidden="true">';
    for (let i = 0; i < WIZ_STEPS; i += 1) {
      s += '<i class="' + (i === wiz.step ? 'on' : (i < wiz.step ? 'done' : '')) + '"></i>';
    }
    return s + '</div>';
  }

  /** Back is a quiet text link — present on every step but the first. */
  function wizBack() {
    return wiz.step === 0 ? ''
      : '<button type="button" class="wz-back" id="wz-back">← back</button>';
  }

  function renderWizard() {
    const sc = $('#scene-build');
    let body = '';

    if (wiz.step === 0) {
      body = '<h2 class="wz-q">What kind of breakup?</h2>'
        + '<div class="wz-cards wz-rel">'
        + Object.keys(RELATIONSHIPS).map((k) =>
          '<button type="button" class="wz-card wz-big" data-rel="' + esc(k) + '">'
          + esc(RELATIONSHIPS[k].name) + '</button>').join('')
        + '</div>';
    } else if (wiz.step === 1 || wiz.step === 2) {
      const side = wiz.step === 1 ? 'a' : 'b';
      body = '<h2 class="wz-q">' + (side === 'a' ? 'Who’s the first one?' : 'And who’s the other one?')
        + '</h2>'
        + '<input type="text" class="wz-name" id="wz-name" maxlength="24" '
        + 'value="' + esc(wiz[side].name) + '" aria-label="name">'
        + '<p class="wz-hint">Now pick what they’re like.</p>'
        + archCardsHTML(side);
    } else {
      body = '<h2 class="wz-q">Name one thing they’d both refuse to give up.</h2>'
        + '<input type="text" class="wz-name" id="wz-item" maxlength="' + WILDCARD_MAX + '" '
        + 'value="' + esc(wiz.item) + '" placeholder="his mother’s painting" aria-label="the item">'
        + '<div class="wz-go"><button type="button" id="b-file">File for divorce →</button></div>'
        + '<p id="b-status"></p>';
    }

    sc.innerHTML = '<div class="wz">' + wizDots() + body + wizBack() + '</div>';

    const back = $('#wz-back');
    if (back) back.addEventListener('click', () => { wiz.step -= 1; renderWizard(); });

    // Tapping a card IS the action — no Next button anywhere in the flow.
    sc.querySelectorAll('[data-rel]').forEach((b) => {
      b.addEventListener('click', () => {
        builderRel = b.dataset.rel;
        wiz.step = 1;
        renderWizard();
      });
    });
    sc.querySelectorAll('[data-arch]').forEach((b) => {
      b.addEventListener('click', () => {
        const side = wiz.step === 1 ? 'a' : 'b';
        const nameEl = $('#wz-name');
        if (nameEl && nameEl.value.trim()) wiz[side].name = nameEl.value.trim();
        wiz[side].archetype = b.dataset.arch;
        wiz.step += 1;
        renderWizard();
      });
    });

    const item = $('#wz-item');
    if (item) {
      item.addEventListener('input', () => { wiz.item = item.value; });
      item.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); fileDivorce(); }
      });
    }
    const file = $('#b-file');
    if (file) file.addEventListener('click', fileDivorce);

    ownScroll(sc, 'start');
    builderReady = true;
  }

  function setFieldErr(anchor, msg) {
    let el = anchor.querySelector(':scope > .f-err');
    if (!msg) { if (el) el.remove(); return; }
    if (!el) {
      el = document.createElement('div');
      el.className = 'f-err';
      anchor.appendChild(el);
    }
    el.textContent = msg;
  }

  async function openBuilder() {
    if (player) { player.destroy(); player = null; }
    refreshPP();
    $('#error').hidden = true;
    $('#case-rail').hidden = true;
    $('#playctl').hidden = true;        // no playback chrome over the intake
    $('#pause-chip').hidden = true;
    document.querySelectorAll('#presets button').forEach((b) => b.classList.remove('active'));
    $('#build-btn').classList.add('active');
    if (!archetypeInfo) {
      $('#scene-build').innerHTML = '<p class="kicker">intake</p>'
        + '<p id="b-status">Pulling the intake forms…</p>';
      showScene('build');
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
    renderWizard();                       // always re-enter at step 0 with prior picks
    showScene('build');
  }

  function fileDivorce() {
    const status = $('#b-status');
    status.classList.remove('bad');
    status.textContent = '';

    // Nothing here can fail validation any more: the wizard cannot advance
    // past a side without an archetype, names fall back to their defaults,
    // and an empty item takes the county's own placeholder. The button is
    // never disabled — never punish someone for pressing Enter.
    const HILLABLE = archetypeInfo.hillable;
    const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

    const readPersona = (side) => {
      const w = wiz[side];
      const preset = archetypeInfo.archetypes[w.archetype] || {};
      // The dials are DERIVED from the archetype (same values the old sliders
      // were preset to) and the hill is rolled here, so the flip stays a
      // surprise to the person who filed.
      return {
        name: (w.name || '').trim() || (side === 'a' ? 'Dana' : 'Morgan'),
        archetype: w.archetype,
        pettiness: typeof preset.pettiness === 'number' ? preset.pettiness : 0.5,
        spite: typeof preset.spite === 'number' ? preset.spite : 0.2,
        patience: typeof preset.patience === 'number' ? preset.patience : 0.5,
        hill: pick(HILLABLE),
      };
    };
    const a = readPersona('a'), b = readPersona('b');
    const wildcard = (wiz.item || '').trim().slice(0, WILDCARD_MAX) || 'the karaoke machine';

    // Always dog + the item they typed: their own words, maximum consequence.
    const body = { a, b, wildcard_label: wildcard,
                   fronts: ['dog', 'wildcard'], rel: builderRel };

    const btn = $('#b-file');
    btn.disabled = true;
    status.textContent = 'Filing. The county appreciates your patience.';

    (async () => {
      let trace;
      try {
        const res = await fetch(API_BASE + '/v1/divorce/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          // The county's own 422 lines are clerk-voiced — display them
          // VERBATIM. Only an unreachable server is "the office is closed."
          let detail = null;
          try { const j = await res.json(); if (j && typeof j.detail === 'string') detail = j.detail; } catch (_e) { /* no body */ }
          btn.disabled = false;
          status.classList.add('bad');
          status.textContent = detail || ('The county returned HTTP ' + res.status + '.');
          return;
        }
        trace = await res.json();
      } catch (e) {
        btn.disabled = false;
        status.classList.add('bad');
        status.textContent = 'The clerk’s office is closed — start the divorce-api server. (' + e.message + ')';
        return;
      }
      btn.disabled = false;
      status.textContent = '';
      sessionFiled = true;
      // If the returned trace fails validation, playTrace shows the plain error —
      // never a fake trace, never a preset in disguise.
      playTrace(trace, null, { rel: builderRel, justFiled: true });
    })();
  }

  /* ------------------------------------------------------------------ *
   *  controls
   * ------------------------------------------------------------------ */

  // click/space: first press pauses into step mode; each further press
  // advances exactly one beat. The ▶ button resumes. The flip's hold beat
  // ignores this — its own button is the only way through.
  function userAdvance() {
    if (!player || player.isFinished() || player.isHolding()) return;
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
      speedVal = speedVal === 1 ? 2 : 1;
      $('#speed').textContent = speedVal + '×';
    });
    $('#skip').addEventListener('click', () => {
      if (!player) return;
      instant(() => player.skipToEnd());
      ownScroll($('#decree-card'), 'start');
    });
    $('#stage').addEventListener('click', (e) => {
      if (e.target.closest('button, a, pre, input, textarea, select, label, details')) return;
      userAdvance();
    });
    document.addEventListener('keydown', (e) => {
      if (e.code !== 'Space' || e.repeat) return;
      if (e.target.closest && e.target.closest('button, a, input, textarea, select, [contenteditable]')) return;
      e.preventDefault();
      userAdvance();
    });
    // verify buttons live in two places (Act III + the decree's proof panel);
    // both run the SAME real WebCrypto check, scoped to their own cards.
    document.addEventListener('click', (e) => {
      const b = e.target.closest('.verify-btn');
      if (!b || !currentModel) return;
      e.stopPropagation();
      verifySeals(currentModel, b.closest('.proof-scope'));
    });
    // tab-away pauses the film instead of silently finishing it
    document.addEventListener('visibilitychange', () => {
      if (document.hidden && player && !player.isFinished()) player.pause();
    });
  }

  wireControls();
  const params = new URLSearchParams(location.search);
  const caseParam = params.get('case');
  if (caseParam && /^\d+$/.test(caseParam)) {
    loadCase(parseInt(caseParam, 10));
  } else {
    const initial = params.get('preset');
    loadPreset(PRESETS[initial] ? initial : 'bloodbath');
  }

})();
