/* Irreconcilable Agents — cinematic trace player.
 *
 * This file renders NOTHING it invented. Every number, count, band, draft,
 * verdict and hash on screen is read from the loaded trace JSON (real engine
 * output). The clerk speaks only fixed templates keyed to real event types.
 * No Math.random. No fabricated fallbacks: a missing field is a plain error.
 */
'use strict';

(() => {

  /* ------------------------------------------------------------------ *
   *  constants & tiny utils
   * ------------------------------------------------------------------ */

  const PRESETS = {
    bloodbath:    { file: 'trace-bloodbath.json',    label: 'The Bloodbath' },
    spreadsheets: { file: 'trace-spreadsheets.json', label: 'The Two Spreadsheets' },
    nodecree:     { file: 'trace-nodecree.json',     label: 'NO DECREE' },
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
  const TICKER_RATE = 10;           // act I exchanges per second

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
   *  player: steps grouped by scene; click/space completes the current
   *  scene and moves on; skip fast-forwards to the decree.
   * ------------------------------------------------------------------ */

  function makePlayer(steps, onError) {
    let i = 0, timer = null, anim = null, finished = false;

    const completeAnim = () => { if (anim && anim.finish) anim.finish(); anim = null; };

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
      if (i >= steps.length) { finished = true; return; }
      const s = runNext(false);
      if (s.dur === Infinity) { finished = true; return; }
      const d = REDUCED ? Math.min(600, s.dur) : s.dur;
      timer = setTimeout(() => { completeAnim(); schedule(); }, d);
    }

    return {
      start() { schedule(); },
      advance() {
        if (finished) return;
        clearTimeout(timer); completeAnim();
        const cur = i > 0 ? steps[i - 1].scene : null;
        while (i < steps.length && steps[i].scene === cur) { runNext(true); completeAnim(); }
        schedule();
      },
      skipToEnd() {
        clearTimeout(timer); completeAnim();
        while (i < steps.length) { runNext(true); completeAnim(); }
        finished = true;
      },
      destroy() { clearTimeout(timer); completeAnim(); i = steps.length; finished = true; },
    };
  }

  /** Run parts [[offsetMs, fn], …]; fast mode runs them all now. */
  function seq(fast, parts) {
    const ran = parts.map(() => false);
    const fire = (k) => { if (!ran[k]) { ran[k] = true; parts[k][1](); } };
    if (fast || REDUCED) { parts.forEach((_, k) => fire(k)); return null; }
    const timers = parts.map((p, k) => setTimeout(() => fire(k), p[0]));
    return { finish() { timers.forEach(clearTimeout); parts.forEach((_, k) => fire(k)); } };
  }

  /** Suppress CSS transitions/animations while fast-forwarding. */
  function instant(fn) {
    document.body.classList.add('instant');
    fn();
    requestAnimationFrame(() => requestAnimationFrame(() => document.body.classList.remove('instant')));
  }

  const SCENES = ['cold', 'act1', 'turn', 'act2', 'act3', 'decree'];
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
    return '<div class="portrait ' + cls + '">'
      + '<div class="monogram">' + esc(c.name.charAt(0).toUpperCase()) + '</div>'
      + '<div class="p-name">' + esc(c.name) + '</div>'
      + '<span class="chip">' + esc(String(c.archetype).replace(/_/g, ' ')) + '</span>'
      + meters
      + '<div class="p-fight">declared fight cost · ' + fmtMoney(req(c, 'fight_cost')) + '</div>'
      + '</div>';
  }

  function buildColdOpen(m, steps) {
    $('#scene-cold').innerHTML =
      '<div class="corner-stamp">valuations sealed · ' + shortSeal(req(m.cast.A, 'seal'))
        + ' · ' + shortSeal(req(m.cast.B, 'seal')) + '</div>'
      + '<div class="cold-head"><h1>IRRECONCILABLE AGENTS</h1>'
      + '<p class="tagline">The divorce is fake. The math is real.</p></div>'
      + '<div class="versus">' + portraitHTML(m, 'A', 'p-a')
      + '<div class="vs">vs</div>' + portraitHTML(m, 'B', 'p-b') + '</div>'
      + '<p class="hint">click / space advances · skip to decree any time</p>';

    steps.push({ scene: 'cold', dur: 8000, run() { showScene('cold'); } });
  }

  function buildAct1(m, steps) {
    $('#scene-act1').innerHTML =
      '<p class="kicker">ACT I · “your lawyers’ way”</p>'
      + '<div id="ticker-wrap"><span id="x-counter"></span>'
      + '<div id="ticker-scroll"><ul id="ticker"></ul></div></div>'
      + '<div id="freeze" hidden></div>'
      + '<p id="act1-summary" hidden></p>';

    // ticker lines: one per real exchange; settles get a quiet check line
    const lines = [];
    let n = 0;
    for (const ex of m.exchanges) {
      n += 1;
      lines.push({ text: exchangeLine(m, ex), cls: '', n });
      if (req(ex, 'accepted') === true) {
        lines.push({ text: '✓ ' + assetDisp(m, ex.asset) + ' settled', cls: 'ok', n });
      }
    }
    const totalX = m.exchanges.length;

    steps.push({
      scene: 'act1',
      dur: Math.ceil(lines.length * (1000 / TICKER_RATE)) + 700,
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
        let raf; const t0 = performance.now();
        const loop = (t) => {
          const want = Math.min(lines.length, Math.floor(((t - t0) / 1000) * TICKER_RATE));
          while (shown < want) push();
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
        dur: 3600,
        run() {
          const f = $('#freeze');
          f.hidden = false;
          f.innerHTML = '<div class="f-asset">' + esc(assetDisp(m, worst)) + '</div>'
            + '<div class="f-stat">' + count + ' EXCHANGES · 0 PROGRESS</div>';
        },
      });
    }

    const settledCount = m.assetCount - m.unsettled.length;
    steps.push({
      scene: 'act1',
      dur: 3000,
      run() {
        const el = $('#act1-summary');
        el.hidden = false;
        el.textContent = settledCount + ' of ' + m.assetCount + ' assets settled after '
          + m.exchanges.length + ' exchanges.';
      },
    });
  }

  function buildTurn(m, steps) {
    $('#scene-turn').innerHTML =
      '<span class="clerk-plate">MEDIATOR — window 4</span>'
      + '<p id="turn-line">“I have some questions.”</p>';
    steps.push({
      scene: 'turn',
      dur: 3800,
      run(fast) {
        showScene('turn');
        return seq(fast, [[900, () => { $('#turn-line').classList.add('shown'); }]]);
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
      '<p class="kicker">ACT II · the interview</p>'
      + '<div id="act2-grid"><div id="dialogue"></div>'
      + '<div id="bands">' + bandPanelHTML(m, 'A') + bandPanelHTML(m, 'B') + '</div></div>';

    const dlg = () => $('#dialogue');
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
        } else if (!isHill) {
          chip.hidden = true;
        }
      }
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
        dur: 1250,
        run(fast) {
          showScene('act2');
          activate(side);
          const parts = [];
          parts.push([0, () => {
            if (q.kind === 'probe') {
              // A probe is a TRADE OFFER, never a valuation question — humans
              // can answer "would you take this deal", not "what is it worth"
              // (the engine's update is the same inequality either way).
              const price = req(q, 'price');
              const disp = assetDisp(m, req(q, 'asset'));
              const offer = price <= 24000
                ? cap(disp) + ', or ' + fmtPrice(price) + ' more of the wallet?'
                : 'If the settlement paid you ' + fmtPrice(price)
                  + ' to give up ' + disp + ' — take it?';
              say('clerk', 'Question ' + qNum + ' of ' + m.totalInterview + '. ' + offer);
            } else if (q.kind === 'pair') {
              say('clerk', 'Question ' + qNum + '. ' + cap(assetDisp(m, req(q, 'A')))
                + ', or ' + assetDisp(m, req(q, 'B')) + '?');
            } else {
              throw new Error('unknown question kind "' + q.kind + '" in trace');
            }
          }]);
          parts.push([620, () => {
            let ans;
            if (q.kind === 'probe') {
              ans = q.answer === true ? 'Yes.' : 'No.';
            } else if (q.answer === 'A') ans = cap(assetDisp(m, q.A)) + '.';
            else if (q.answer === 'B') ans = cap(assetDisp(m, q.B)) + '.';
            else ans = 'Neither.'; // pair answer "walk" (never invented; schema event type)
            say('reply', who + ': “' + ans + '”');
            updateBands(side, req(q, 'bands'), req(q, 'step'));
            // deterministic clerk punctuation, keyed only to "an answer happened"
            if (k % 5 === 4) say('aside', 'Noted.');
            else if (q.kind === 'probe' && q.answer === false && k % 7 === 5) say('aside', 'That’s what they all say.');
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
      '<p class="kicker">ACT III · drafts &amp; the flip</p>'
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
        dur: 1500,
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
        dur: 2400,
        run(fast) {
          const div = $('#drafts').lastElementChild;
          const sign = (side, ok) => () => {
            const slot = div.querySelector('.sig[data-side="' + side + '"]');
            if (ok) {
              slot.querySelector('.s-mark').innerHTML = sigMarkSVG();
              slot.querySelector('.s-verdict').textContent = 'Signed.';
            } else {
              slot.querySelector('.s-verdict').innerHTML = '<span class="refused">REFUSED.</span>';
            }
          };
          const parts = [[250, sign('A', okA)], [950, sign('B', okB)]];
          if (!okA || !okB) parts.push([1500, () => clerkLine('“Refused. Noted.”')]);
          else parts.push([1500, () => clerkLine('“Ratified.”')]);
          return seq(fast, parts);
        },
      });
    });

    // the flip — sealed cards turn over; runs on every path (NO DECREE included)
    steps.push({
      scene: 'act3',
      dur: 1400,
      run() {
        clerkLine(m.noDecree ? '“Out of drafts. Cards on the table.”' : '“Show your cards.”');
        $('#flip-area').hidden = false;
      },
    });
    steps.push({
      scene: 'act3',
      dur: 2600,
      run(fast) {
        return seq(fast, [[400, () => {
          document.querySelectorAll('.flipcard').forEach((c) => c.classList.add('flipped'));
        }]]);
      },
    });
    steps.push({
      scene: 'act3',
      dur: 4200,
      run() { clerkLine('“Nobody peeked. Check it yourself.”'); },
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
    const p = (d) => '<path d="' + d + '"/>';
    return '<svg width="86" height="94" viewBox="0 0 140 150" fill="none" stroke="#1b1a17" '
      + 'stroke-width="2.2" stroke-linecap="round" aria-hidden="true">'
      + p('M30 34 C 32 21, 45 15, 56 20')          // skull
      + p('M53 17 C 62 12, 69 21, 62 32 C 59 36, 55 36, 54 31') // ear
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
      + p('M105 108 C 117 106, 123 96, 119 86 C 117 80, 111 78, 107 83') // tail
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

    if (m.noDecree) {
      const verdict = m.decree.no_zopa
        ? 'No overlap exists. Some marriages even math can’t save.'
        : 'The mediator declined to certify a deal.';
      cardHTML =
        '<div id="decree-card">'
        + '<div class="dc-head"><div class="dc-title">FINAL DECREE</div>'
        + '<div class="dc-inre">' + inre + '</div></div>'
        + '<div class="dc-nodecree">NO DECREE.</div>'
        + '<div class="dc-lines">'
        + '<p>' + m.assetCount + ' assets. ' + m.exchanges.length + ' exchanges. ' + m.nQuestions + ' questions.</p>'
        + '<p>' + esc(verdict) + '</p>'
        + '</div>'
        + '<hr class="dc-rule">'
        + '<div class="dc-tax" style="text-align:center">PETTINESS TAX: everything.</div>'
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

    steps.push({ scene: 'decree', dur: Infinity, run() { showScene('decree'); } });
  }

  /* ------------------------------------------------------------------ *
   *  boot
   * ------------------------------------------------------------------ */

  let player = null;
  let currentPreset = null;

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

  async function loadPreset(key) {
    const preset = PRESETS[key];
    if (!preset) throw new Error('unknown preset "' + key + '"');
    currentPreset = key;
    document.querySelectorAll('#presets button').forEach((b) => {
      b.classList.toggle('active', b.dataset.preset === key);
    });
    if (player) { player.destroy(); player = null; }
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

    let film;
    try {
      film = buildFilm(trace);
    } catch (e) {
      showError('Trace ' + preset.file + ' failed validation — ' + e.message
        + '\n\nNothing is rendered from a broken trace: no fallbacks, no invented numbers.');
      return;
    }

    const verifyHook = () => {
      const btn = $('#verify-btn');
      if (btn) btn.addEventListener('click', (ev) => { ev.stopPropagation(); verifySeals(film.m); });
    };
    verifyHook();

    player = makePlayer(film.steps, (e) => {
      showError('Playback halted — ' + e.message
        + '\n\nNothing is rendered from a broken trace: no fallbacks, no invented numbers.');
    });
    player.start();
  }

  function userAdvance() {
    if (player) instant(() => player.advance());
  }

  function wireControls() {
    document.querySelectorAll('#presets button').forEach((b) => {
      b.addEventListener('click', () => loadPreset(b.dataset.preset));
    });
    $('#skip').addEventListener('click', () => {
      if (player) instant(() => player.skipToEnd());
    });
    $('#replay').addEventListener('click', () => {
      if (currentPreset) loadPreset(currentPreset);
    });
    $('#stage').addEventListener('click', (e) => {
      if (e.target.closest('button, a, pre, input, textarea')) return;
      userAdvance();
    });
    document.addEventListener('keydown', (e) => {
      if (e.code !== 'Space' || e.repeat) return;
      if (e.target.closest && e.target.closest('button, a, input, textarea, [contenteditable]')) return;
      e.preventDefault();
      userAdvance();
    });
  }

  wireControls();
  const params = new URLSearchParams(location.search);
  const initial = params.get('preset');
  loadPreset(PRESETS[initial] ? initial : 'bloodbath');

})();
