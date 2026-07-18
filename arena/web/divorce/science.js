/* science.js — renders science-data.json into science.html.
   No libraries. Every number on the page comes from the fetched JSON, with one
   pinned exception (MEDIAN_LEAK_SEVERITY_USD, sourced below). Kill flags in
   the data gate every claim: if a kill fired, the page prints the kill, not
   the claim. If the file is missing (the harness is still running), the page
   says so — it never estimates. */
'use strict';

// Median goodwill-leak severity (dollars below the committed rule's
// threshold) now travels IN science-data.json — computed from the per-leak
// records by science_eval's aggregate step, never pinned here.

const $id = (s) => document.getElementById(s);
const esc = (s) => String(s).replace(/[&<>"]/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const pct1 = (x) => (100 * x).toFixed(1) + '%';
const money = (x) => '$' + Math.round(x).toLocaleString('en-US');
const moneyCents = (x) => '$' + Number(x).toFixed(2);

const PENDING = '<p class="pending">results pending — the harness is running.</p>';
const UNREADABLE = '<p class="pending">the results file is present but not in the '
  + 'shape this page expects — numbers withheld rather than guessed.</p>';

const firedBlock = (text) => '<div class="claim fired">' + esc(text) + '</div>';

function seedsLabel(seeds) {
  if (Array.isArray(seeds) && seeds.length === 4) {
    return seeds.slice(0, 3).join(', ') + ' (committed) + '
      + seeds[3] + ' (fresh confirmatory)';
  }
  return (seeds || []).join(', ');
}

/* ── charts (hand-rolled inline SVG) ──────────────────────────────────── */

/** Line chart over question budgets. points: [{q, y, label, anno, red, title}] */
function lineChartSVG(cfg) {
  const W = 640, H = 330, L = 62, R = 26, T = 26, B = 64;
  const pw = W - L - R, ph = H - T - B;
  const qs = cfg.points.map((p) => p.q);
  const qMin = Math.min(...qs), qMax = Math.max(...qs);
  const x = (q) => L + ((q - qMin) / (qMax - qMin)) * pw;
  const yHi = 1.0;
  const y = (v) => T + (1 - (v - cfg.yLo) / (yHi - cfg.yLo)) * ph;
  let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="'
    + esc(cfg.aria) + '" xmlns="http://www.w3.org/2000/svg">';
  for (const t of cfg.yTicks) {
    s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(t).toFixed(1)
      + '" y2="' + y(t).toFixed(1) + '"/>';
    s += '<text class="tick" x="' + (L - 8) + '" y="' + (y(t) + 4).toFixed(1)
      + '" text-anchor="end">' + Math.round(t * 100) + '%</text>';
  }
  s += '<line class="axis" x1="' + L + '" x2="' + (W - R) + '" y1="' + (T + ph)
    + '" y2="' + (T + ph) + '"/>';
  for (const p of cfg.points) {
    s += '<text class="tick" x="' + x(p.q).toFixed(1) + '" y="' + (T + ph + 18)
      + '" text-anchor="middle">' + p.q + '</text>';
  }
  s += '<text class="axlabel" x="' + (L + pw / 2) + '" y="' + (H - 14)
    + '" text-anchor="middle">' + esc(cfg.xAxis) + '</text>';
  s += '<text class="axlabel" transform="rotate(-90 14 ' + (T + ph / 2) + ')" x="14" y="'
    + (T + ph / 2) + '" text-anchor="middle">' + esc(cfg.yAxis) + '</text>';
  s += '<path class="line" d="' + cfg.points.map((p, i) =>
    (i ? 'L' : 'M') + x(p.q).toFixed(1) + ' ' + y(p.y).toFixed(1)).join(' ') + '"/>';
  for (const p of cfg.points) {
    s += '<g><title>' + esc(p.title) + '</title>';
    s += '<circle class="dot' + (p.red ? ' dot-red' : '') + '" cx="' + x(p.q).toFixed(1)
      + '" cy="' + y(p.y).toFixed(1) + '" r="5.5"/>';
    s += '<text class="val' + (p.red ? ' val-red' : '') + '" x="' + x(p.q).toFixed(1)
      + '" y="' + (y(p.y) - 12).toFixed(1) + '" text-anchor="middle">' + esc(p.label) + '</text>';
    if (p.anno) {
      // fixed row just above the axis, clear of the line and the other points
      s += '<text class="anno" x="' + x(p.q).toFixed(1) + '" y="' + (T + ph - 10)
        + '" text-anchor="middle">' + esc(p.anno) + '</text>';
    }
    s += '</g>';
  }
  return s + '</svg>';
}

/** Histogram of dollar values (sorted ints). Red bar = the bin holding the median. */
function histSVG(values, cfg) {
  const W = 640, H = 340, L = 56, R = 24, T = 30, B = 64;
  const pw = W - L - R, ph = H - T - B;
  const binW = cfg.binW;
  const max = values[values.length - 1] || binW;
  const nb = Math.max(1, Math.ceil((max + 1) / binW));
  const counts = new Array(nb).fill(0);
  for (const v of values) counts[Math.min(nb - 1, Math.floor(v / binW))] += 1;
  const yMax = Math.max(...counts);
  const yTop = Math.max(10, Math.ceil(yMax / 10) * 10);
  const yStep = yTop > 40 ? 20 : 10;
  const y = (c) => T + (1 - c / yTop) * ph;
  const xv = (v) => L + (v / (nb * binW)) * pw;
  let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="'
    + esc(cfg.aria) + '" xmlns="http://www.w3.org/2000/svg">';
  for (let t = 0; t <= yTop; t += yStep) {
    s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(t).toFixed(1)
      + '" y2="' + y(t).toFixed(1) + '"/>';
    s += '<text class="tick" x="' + (L - 8) + '" y="' + (y(t) + 4).toFixed(1)
      + '" text-anchor="end">' + t + '</text>';
  }
  const medBin = Math.min(nb - 1, Math.floor(cfg.median / binW));
  for (let i = 0; i < nb; i += 1) {
    if (!counts[i]) continue;
    const bx = L + (i / nb) * pw + 1;
    const bw = pw / nb - 2;                       // 2px surface gap between bars
    const by = y(counts[i]);
    s += '<g><title>' + esc(money(i * binW) + '–' + money((i + 1) * binW) + ' · '
      + counts[i] + (counts[i] === 1 ? ' case' : ' cases')) + '</title>';
    s += '<rect class="bar' + (i === medBin ? ' bar-red' : '') + '" x="' + bx.toFixed(1)
      + '" y="' + by.toFixed(1) + '" width="' + bw.toFixed(1) + '" height="'
      + (T + ph - by).toFixed(1) + '" rx="2"/></g>';
  }
  s += '<line class="axis" x1="' + L + '" x2="' + (W - R) + '" y1="' + (T + ph)
    + '" y2="' + (T + ph) + '"/>';
  const tickStep = 4 * binW;
  for (let v = 0; v <= nb * binW; v += tickStep) {
    s += '<text class="tick" x="' + xv(v).toFixed(1) + '" y="' + (T + ph + 18)
      + '" text-anchor="middle">' + (v === 0 ? '$0' : '$' + (v / 1000) + 'k') + '</text>';
  }
  const mx = xv(cfg.median);
  s += '<line class="medline" x1="' + mx.toFixed(1) + '" x2="' + mx.toFixed(1)
    + '" y1="' + (T - 6) + '" y2="' + (T + ph) + '"/>';
  const flip = mx > W - R - 170;
  s += '<text class="medlabel" x="' + (flip ? mx - 8 : mx + 8).toFixed(1) + '" y="'
    + (T + 6) + '" text-anchor="' + (flip ? 'end' : 'start') + '">median '
    + esc(money(cfg.median)) + '</text>';
  s += '<text class="axlabel" x="' + (L + pw / 2) + '" y="' + (H - 14)
    + '" text-anchor="middle">' + esc(cfg.xAxis) + '</text>';
  s += '<text class="axlabel" transform="rotate(-90 14 ' + (T + ph / 2) + ')" x="14" y="'
    + (T + ph / 2) + '" text-anchor="middle">' + esc(cfg.yAxis) + '</text>';
  return s + '</svg>';
}

/* ── section renderers (each kill-conditional) ────────────────────────── */

function renderKillStrip(d) {
  const flags = [
    ['E1 selective-risk', !!d.E1.KILL_UP_fires],
    ['E1 pessimism', !!d.E1.KILL_DOWN_fires],
    ['E2 human-robust', !!d.E2.KILL_fires],
    ['E3 floor', !!d.E3.KILL_DOWN_fires],
    ['E3 stability', !!d.E3.KILL_UP_fires],
  ];
  $id('kill-strip').innerHTML = flags.map(([name, fired]) =>
    '<span class="ks' + (fired ? ' ks-fired' : '') + '">' + esc(name)
    + ' · <b>' + (fired ? 'FIRED' : 'survived') + '</b></span>').join('');
}

function renderTrap(t) {
  const leakShare = t.GOODWILL_LEAKS / t.n_decisions;
  const llm = (100 * t.llm_accept_rate).toFixed(1);
  const rule = (100 * t.rule_accept_rate).toFixed(1);
  const same = llm === rule;
  $id('trap-results').innerHTML =
    '<p>The model was <span class="mono">' + esc(t.model) + '</span>: ' + t.n_pairs
    + ' qualified pairs, ' + t.n_decisions + ' accept/reject decisions, '
    + moneyCents(t.total_spend_usd) + ' of metered inference. <b>' + t.GOODWILL_LEAKS
    + ' decisions — ' + pct1(leakShare) + ' — were goodwill leaks:</b> accepts of offers '
    + 'clearly below that side&rsquo;s walk-away bound (more than three noise standard '
    + 'deviations below the committed rule&rsquo;s threshold), giving away a median of '
    + money(t.median_leak_severity_usd) + ' per leak. The recorded reasonings are '
    + 'arithmetic-adjacent rationalization; in the cleanest specimen the model computed that '
    + 'the offer was worse than litigation, then accepted it. It also rejected '
    + t.clear_over_toughness_rejects + ' clearly acceptable offers and split with the rule on '
    + t.gray_zone_disagreements + ' gray-zone calls.</p>'
    + '<div class="agg" role="group" aria-label="aggregate accept rates">'
    + '<div class="agg-cell"><div class="agg-num">' + llm + '%</div>'
    + '<div class="agg-label">LLM accept rate</div></div>'
    + '<div class="agg-eq">' + (same ? '=' : '≠') + '</div>'
    + '<div class="agg-cell"><div class="agg-num">' + rule + '%</div>'
    + '<div class="agg-label">committed-rule accept rate</div></div></div>'
    + '<p>' + (same
      ? 'The aggregate accept rates are identical. The leaks and the over-tough rejections '
        + 'cancel to the decimal: an auditor watching the aggregate sees a model in perfect '
        + 'agreement with the rule it is quietly violating ' + pct1(leakShare)
        + ' of the time.'
      : 'The aggregate rates differ by ' + Math.abs(llm - rule).toFixed(1)
        + ' points — and still say nothing about which individual decisions were wrong.')
    + '</p>';
}

function renderE1(d, seeds) {
  const E1 = d.E1;
  const rc = E1.risk_coverage;
  const budgets = Object.keys(rc).map(Number).sort((a, b) => a - b);
  const points = budgets.map((q) => {
    const c = rc[String(q)];
    return {
      q, y: c.coverage, label: pct1(c.coverage), red: q === 10,
      anno: 'risk ' + pct1(c.selective_risk) + (q === 10 ? ' · shipped gate' : ''),
      title: 'Q=' + q + ': coverage ' + pct1(c.coverage) + ', selective risk '
        + pct1(c.selective_risk) + ', n=' + c.n,
    };
  });
  const yLo = Math.min(0.9,
    Math.floor((Math.min(...points.map((p) => p.y)) - 0.02) * 20) / 20);
  const yTicks = [];
  for (let t = yLo; t <= 1.0001; t += 0.05) yTicks.push(Math.round(t * 100) / 100);
  const n10 = rc['10'].n;
  const chart = '<figure>' + lineChartSVG({
    points, yLo, yTicks,
    xAxis: 'questions per side', yAxis: 'pairs receiving a certified decree',
    aria: 'Risk-coverage: share of pairs certified at each question budget, with '
      + 'selective risk annotated per point',
  }) + '<figcaption>Risk–coverage across question budgets. N = ' + n10
    + ' qualified, oracle-settled pairs per budget point; seeds ' + esc(seedsLabel(seeds))
    + '; 100 pairs sampled per seed. Coverage = share of pairs receiving a certified '
    + 'decree; selective risk = P(a true walk-away was violated | certified).'
    + '</figcaption></figure>';

  const q10 = rc['10'];
  const totalCert = budgets.reduce(
    (a, q) => a + Math.round(rc[String(q)].coverage * rc[String(q)].n), 0);
  const blocks = [];
  if (E1.KILL_UP_fires) {
    blocks.push(firedBlock('KILL FIRED: selective risk exceeded the registered 2% — the '
      + 'word “calibrated” is retired per registration. Measured at the shipped gate: '
      + pct1(q10.selective_risk) + '.'));
  }
  if (E1.KILL_DOWN_fires) {
    blocks.push(firedBlock('KILL FIRED: ' + pct1(E1.recoverable_rate) + ' of abstentions '
      + 'were recoverable — the gate is pessimism, not calibration; claim withdrawn per '
      + 'registration.'));
  }
  if (!blocks.length) {
    blocks.push('<p class="claim">Uncertainty became abstention, never a bad stamp.</p>');
    blocks.push('<p>Across ' + totalCert + ' certified decrees (three budgets over the same '
      + 'pairs), selective risk at the shipped gate — ten questions a side — was '
      + pct1(q10.selective_risk) + ', against the registered 2% ceiling. And the caution is '
      + 'not competence in hiding: of the ' + E1.abstained_at_10 + ' abstentions at Q&nbsp;='
      + '&nbsp;10, ' + E1.recoverable + ' (' + pct1(E1.recoverable_rate) + ') held a deal the '
      + 'mediator&rsquo;s own final posterior could certify and both true walk-aways would '
      + 'accept, against the registered 15% bound. Both registered kills survived; under this '
      + 'registration the gate keeps the word <i>calibrated</i>.</p>');
  } else {
    blocks.push('<p class="smallnote">Measured regardless: selective risk '
      + pct1(q10.selective_risk) + ' at Q=10; ' + E1.recoverable + ' of '
      + E1.abstained_at_10 + ' abstentions recoverable ('
      + pct1(E1.recoverable_rate) + ').</p>');
  }
  $id('e1-results').innerHTML = chart + blocks.join('');
}

function renderE2(d, seeds) {
  const E2 = d.E2;
  const cc = E2.capture_curve;
  const budgets = Object.keys(cc).map(Number).sort((a, b) => a - b);
  const qTop = Math.max(...budgets);
  const points = budgets.map((q) => ({
    q, y: cc[String(q)], label: pct1(cc[String(q)]), red: q === qTop,
    title: 'Q=' + q + ': median capture ' + pct1(cc[String(q)]) + ' of the oracle surplus',
  }));
  const yLo = Math.floor((Math.min(...points.map((p) => p.y)) - 0.02) * 20) / 20;
  const yTicks = [];
  for (let t = yLo; t <= 1.0001; t += 0.05) yTicks.push(Math.round(t * 100) / 100);
  const n = (d.E1 && d.E1.risk_coverage && d.E1.risk_coverage['10'])
    ? d.E1.risk_coverage['10'].n : null;
  const chart = '<figure>' + lineChartSVG({
    points, yLo, yTicks,
    xAxis: 'questions per side',
    yAxis: 'fraction of perfect-information surplus',
    aria: 'Elicitation-budget curve: median captured fraction of the '
      + 'perfect-information surplus at each question budget',
  }) + '<figcaption>Median captured share of the perfect-information (oracle) surplus vs '
    + 'question budget, honest answers — the same runs and population as E1'
    + (n ? ' (N = ' + n + ' pairs per point' : ' (')
    + '; seeds ' + esc(seedsLabel(seeds)) + ').</figcaption></figure>';

  const v2 = E2.v2_biased_median, v1 = E2.v1_honest_median;
  const table =
    '<table class="mini"><thead><tr><th>interview</th><th>answerer</th>'
    + '<th>median capture, Q = 10</th></tr></thead><tbody>'
    + '<tr><td>v1 — cash probes + pairwise picks</td><td>honest</td>'
    + '<td class="num">' + pct1(v1) + '</td></tr>'
    + '<tr><td>v2 — every question a package choice</td>'
    + '<td>biased-human model (frozen)</td>'
    + '<td class="num"><b>' + pct1(v2) + '</b></td></tr>'
    + '</tbody></table>'
    + '<p class="smallnote">The cross-comparison the kill is registered on: the shipped '
    + 'interview under adversarial answering vs the old interview under perfect honesty.</p>';

  const blocks = [chart, '<p class="claim">Ten choices a side buys ' + pct1(cc['10'])
    + ' of the perfect-information frontier; twenty-four buys ' + pct1(cc['24']) + '.</p>',
  '<p>The residual gap at demo budgets is elicitation information, purchasable with more '
    + 'questions — not a mechanism tax.</p>', table];
  if (E2.KILL_fires) {
    blocks.push(firedBlock('KILL FIRED: under the frozen bias model the v2 interview&rsquo;s '
      + 'median capture (' + pct1(v2) + ') did not beat the v1 interview under honest '
      + 'answers (' + pct1(v1) + ') — the phrase “human-robust” is dropped per '
      + 'registration.'));
  } else {
    blocks.push('<p>And the interview earns the registered sense of <i>human-robust</i>: '
      + 'handicapped by the frozen anchoring-and-acquiescence answer model, the all-choices '
      + 'interview still captures a median ' + pct1(v2) + ' — more than the old cash-probe '
      + 'interview manages with perfectly honest answers (' + pct1(v1) + ').</p>');
  }
  $id('e2-results').innerHTML = blocks.join('');
}

function renderE3(d, seeds) {
  const E3 = d.E3;
  const chart = '<figure>' + histSVG(E3.tax_distribution, {
    binW: 10000, median: E3.median_tax_abs,
    xAxis: 'worst side’s pettiness tax per case (dollars)', yAxis: 'cases',
    aria: 'Histogram of the worst side&rsquo;s pettiness tax across all cases, '
      + 'with the median marked',
  }) + '<figcaption>Distribution of the worse-off side&rsquo;s pettiness tax. N = ' + E3.n
    + ' oracle-settled pairs; seeds ' + esc(seedsLabel(seeds)) + '. Each value is one '
    + 'case&rsquo;s despiked counterfactual: the same pair re-run with the spite term '
    + 'deleted, in dollars.</figcaption></figure>';

  const bundle = E3.median_drift_nonhill > 2;
  const drift = Math.round(E3.median_drift_nonhill);
  const stab = E3.seed_stability_ratio;
  const blocks = [];
  if (E3.KILL_DOWN_fires) {
    blocks.push(firedBlock('KILL FIRED: the median tax ('
      + pct1(E3.headline_median_ratio) + ' of achievable surplus) fell below the registered '
      + '5% floor — a rounding error at this population; it is not headlined, per '
      + 'registration.'));
    blocks.push('<p class="smallnote">Measured regardless: median '
      + money(E3.median_tax_abs) + ' (' + pct1(E3.headline_median_ratio)
      + ' of achievable surplus).</p>');
  }
  if (E3.KILL_UP_fires) {
    blocks.push(firedBlock('KILL FIRED (stability): the median absolute tax varied ×'
      + (stab == null ? '?' : stab.toFixed(2)) + ' across the three committed seeds, beyond '
      + 'the registered 3× ceiling — no single number is reported; per-seed medians are in '
      + 'divorce/results-science-seed{7,11,23}.json.'));
  }
  if (!E3.KILL_DOWN_fires && !E3.KILL_UP_fires) {
    blocks.push('<p class="claim">The median case sets fire to '
      + pct1(E3.headline_median_ratio) + ' of its achievable surplus — '
      + money(E3.median_tax_abs) + '. Same divorce, minus the feelings, re-run to the '
      + 'dollar' + (bundle ? ' — as a bundle-level counterfactual' : '') + '.</p>');
    blocks.push('<p>The registered floor was 5%; below it, no headline. Stability across the '
      + 'committed seeds: the median absolute tax varies ×'
      + (stab == null ? '?' : stab.toFixed(2)) + ', inside the registered 3× ceiling, so a '
      + 'single median may be reported. Unlike the population coefficients in the prior '
      + 'work, this number re-derives per case: hand the engine the pair and it prints the '
      + 'counterfactual again.</p>');
  }
  if (bundle) {
    blocks.push('<div class="duty">REGISTERED LABELING DUTY: in the median case, ' + drift
      + ' non-hill assets moved more than 0.25 share when the spite term was removed '
      + '(&gt; 2 of 5) — the tax must be read as a bundle-level counterfactual: a property '
      + 'of the whole settlement, not a price tag on any single item.</div>');
  } else {
    blocks.push('<p class="smallnote">Attribution check (registered as a labeling duty): in '
      + 'the median case ' + drift + ' non-hill asset' + (drift === 1 ? '' : 's')
      + ' moved more than 0.25 share under despiking — at or below the registered 2-of-5 '
      + 'bound, so the per-item reading of the tax stands.</p>');
  }
  $id('e3-results').innerHTML = chart + blocks.join('');
}

/* ── entry ────────────────────────────────────────────────────────────── */

function renderPendingAll() {
  $id('pending-banner').hidden = false;
  $id('kill-strip').innerHTML =
    '<span class="ks">registered kills · <b>pending</b> — the harness is running</span>';
  for (const id of ['trap-results', 'e1-results', 'e2-results', 'e3-results']) {
    $id(id).innerHTML = PENDING;
  }
}

(async function main() {
  let d = null;
  try {
    const r = await fetch('science-data.json', { cache: 'no-store' });
    if (r.ok) d = await r.json();
  } catch (_) { /* no data yet — pending state below */ }
  if (!d) { renderPendingAll(); return; }

  const seeds = d.seeds || [];
  try { renderKillStrip(d); } catch (e) { $id('kill-strip').innerHTML = ''; }
  try { renderTrap(d.trap_check); } catch (e) { $id('trap-results').innerHTML = UNREADABLE; }
  try { renderE1(d, seeds); } catch (e) { $id('e1-results').innerHTML = UNREADABLE; }
  try { renderE2(d, seeds); } catch (e) { $id('e2-results').innerHTML = UNREADABLE; }
  try { renderE3(d, seeds); } catch (e) { $id('e3-results').innerHTML = UNREADABLE; }
}());
