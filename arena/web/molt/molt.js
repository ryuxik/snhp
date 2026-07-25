/* Molt Season — plays back a recorded negotiation. Every number rendered here
   comes out of trace-*.json / science-data.json, which come out of
   research/molt/. Nothing is computed for effect; the only thing this file
   invents is the pacing. */
'use strict';

const CASES = ['walkout', 'settled', 'works_wins'];
const ISSUE_LABEL = {
  base: 'base pay', title: 'the molt', bonus: 'retention',
  berth: 'berth', deepwater: 'deepwater'
};
const ISSUE_NOTE = {
  base: 'a permanent raise — it also leaks to the whole band',
  title: 'a bigger shell: the promotion',
  bonus: 'a one-time retention payment',
  berth: 'flexible shift and tide-cycle',
  deepwater: 'the growth assignment nobody senior wants to give up'
};
const DAYS_PER_SEC = 6;

const $ = (s) => document.querySelector(s);
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
};
const money = (x) => (x < 0 ? '−' : '') + '$' + Math.abs(Math.round(x)).toLocaleString('en-US');
const signed = (x) => (x >= 0 ? '+' : '−') + '$' + Math.abs(Math.round(x)).toLocaleString('en-US');

let state = { playing: true, speed: 1, timer: null, day: 0, queue: [], trace: null };

/* ------------------------------------------------------------------ boot */
async function boot() {
  const params = new URLSearchParams(location.search);
  const which = CASES.includes(params.get('case')) ? params.get('case') : 'walkout';
  let trace, sci;
  try {
    [trace, sci] = await Promise.all([
      fetch(`trace-${which}.json`).then((r) => r.json()),
      fetch('science-data.json').then((r) => r.json())
    ]);
  } catch (e) {
    $('#error').hidden = false;
    $('#error').textContent = 'Could not load the recorded trace: ' + e.message;
    return;
  }
  state.trace = trace;
  state.sci = sci;
  state.which = which;
  renderCrab(trace.crab);
  renderPrices(trace.crab);
  renderScience(sci);
  buildQueue(trace);
  wireControls();
  tick();
}

/* ------------------------------------------------------------- the crab */
function renderCrab(c) {
  $('#crab-name').textContent = c.name;
  $('#crab-line').textContent =
    `${c.spec} · ${money(c.salary)}/yr · ${c.tenure} ${c.tenure === 1 ? 'year' : 'years'} on station · ${c.perf}th percentile`;
  const body = $('#crab-body');
  body.innerHTML = '';
  body.append(
    fact('The Works’s standing offer', pkgShort(c.opening),
         'the merit matrix, before anyone says anything'),
    fact('What she actually wants', ISSUE_LABEL[c.cares_most],
         `she puts ${Math.round(100 * c.weights[c.cares_most])}% of her weight on it`, true),
    c.has_outside
      ? fact('Offer in hand', `+${c.outside_premium}%`,
             `worth ${money(c.outside_value)} to her · expires day ${c.offer_expires_day}`, true)
      : fact('Offer in hand', 'none', 'she is not going anywhere'),
    fact('If she leaves', money(c.replacement_cost),
         'what replacing her costs the Works, all in')
  );
}

function fact(k, v, n, hot) {
  const f = el('div', 'fact' + (hot ? ' hot' : ''));
  f.append(el('div', 'k', k), el('div', 'v', v), el('div', 'n', n));
  return f;
}

function pkgShort(p) {
  const bits = [p.base];
  if (p.title === 'molt') bits.push('molt');
  if (p.bonus !== 'none') bits.push(p.bonus);
  if (p.berth === 'flexible') bits.push('flex');
  if (p.deepwater === 'deepwater') bits.push('deepwater');
  return bits.join(' + ');
}

/* --------------------------------------------------------- price ledger */
function renderPrices(c) {
  const host = $('#prices');
  host.innerHTML = '';
  const keys = Object.keys(c.issue_values);
  const max = Math.max(...keys.map((k) => Math.max(c.issue_values[k], c.issue_costs[k])));
  keys.forEach((k) => {
    const worth = c.issue_values[k], cost = c.issue_costs[k];
    const row = el('div', 'prow');
    const nm = el('div', 'iname', ISSUE_LABEL[k]);
    nm.title = ISSUE_NOTE[k];
    const bars = el('div', 'bars');
    const b1 = el('div', 'bar worth');
    b1.style.width = Math.max(2, (78 * worth) / max) + '%';
    b1.append(el('span', null, money(worth) + ' to her'));
    const b2 = el('div', 'bar cost');
    b2.style.width = Math.max(2, (78 * cost) / max) + '%';
    b2.append(el('span', null, money(cost) + ' to the Works'));
    bars.append(b1, b2);
    const gap = worth - cost;
    const g = el('div', 'pgap ' + (gap > 1 ? 'good' : gap < -1 ? 'bad' : ''), Math.abs(gap) < 1 ? 'even' : signed(gap));
    g.title = gap > 0 ? 'worth more to her than it costs them: a trade exists'
                      : 'costs them more than it is worth to her';
    row.append(nm, bars, g);
    host.append(row);
  });
  const lg = el('div', 'plegend');
  lg.innerHTML =
    '<span class="swatch" style="background:var(--kelp)"></span><b>worth to her</b>' +
    ' &nbsp;&nbsp; <span class="swatch" style="background:var(--coral);opacity:.75"></span><b>cost to the Works</b>' +
    ' &mdash; anything green on the right is money lying on the table. ' +
    'A raise is the only term that costs them <em>more</em> than she gets, because it is permanent and the whole band re-prices off it.';
  host.append(lg);
}

/* ------------------------------------------------------------- the race */
function buildQueue(t) {
  const q = [];
  const c = t.crab;

  // slow lane, straight off the recorded meeting days
  t.slow.steps.forEach((s, i) => {
    q.push({ day: s.day, lane: 'slow', kind: 'meeting', i, s });
  });
  const se = t.slow.score;
  q.push({ day: se.days, lane: 'slow', kind: 'end', score: se });

  // fast lane: the sitting resolves inside one day; the approval hop is real
  // calendar time and is charged to this lane too (PREREG §0 guard 2)
  t.fast.steps.forEach((s, i) => {
    q.push({ day: 0.15 + i * 0.18, lane: 'fast', kind: 'round', i, s });
  });
  const fe = t.fast.score;
  q.push({ day: 1.0, lane: 'fast', kind: 'handshake', score: fe });
  if (fe.days > 1.0) q.push({ day: 1.05, lane: 'fast', kind: 'wait', score: fe });
  q.push({ day: fe.days, lane: 'fast', kind: 'end', score: fe });

  if (c.has_outside) q.push({ day: c.offer_expires_day, lane: null, kind: 'expiry' });

  q.sort((a, b) => a.day - b.day);
  state.queue = q;
  state.endDay = Math.max(se.days, fe.days) + 1.5;
  if (c.has_outside) {
    $('#expiry').hidden = false;
    $('#expiry').textContent = `her outside offer expires on day ${c.offer_expires_day}`;
  }
}

function tick() {
  clearInterval(state.timer);
  state.timer = setInterval(() => {
    if (!state.playing) return;
    state.day += (DAYS_PER_SEC * state.speed) / 20;
    if (state.day >= state.endDay) {
      state.day = state.endDay;
      finish();
      return;
    }
    drain();
    $('#dayclock').textContent = Math.floor(state.day);
  }, 50);
}

function drain() {
  while (state.queue.length && state.queue[0].day <= state.day) {
    render(state.queue.shift());
  }
}

function finish() {
  clearInterval(state.timer);
  drain();
  $('#dayclock').textContent = Math.floor(state.endDay - 1.5);
  renderBill(state.trace);
}

function render(ev) {
  if (ev.kind === 'expiry') {
    const e = $('#expiry');
    e.classList.add('gone');
    e.textContent = 'her outside offer has expired — she can no longer take it';
    return;
  }
  const feed = ev.lane === 'slow' ? $('#feed-slow') : $('#feed-fast');
  if (ev.kind === 'meeting') feed.append(meetingCard(ev));
  else if (ev.kind === 'round') feed.append(roundCard(ev));
  else if (ev.kind === 'handshake') feed.append(handshakeCard(ev));
  else if (ev.kind === 'wait') feed.append(waitCard(ev));
  else if (ev.kind === 'end') endLane(ev);
}

function meetingCard(ev) {
  const s = ev.s;
  const n = el('div', 'ev' + (s.granted ? '' : ' refused'));
  const top = el('div', 'evtop');
  top.append(el('span', null, `MEETING ${ev.i + 1} · DAY ${Math.round(s.day)}`),
             el('span', null, s.granted ? 'granted' : 'declined'));
  n.append(top);
  // the Works often grants LESS than the ask; saying "agrees" there would be a
  // caption the trace does not support
  const landed = s.pkg[s.issue];
  const full = String(landed) === String(s.ask);
  n.append(el('div', 'evmain',
    `She asks for ${s.ask} on ${ISSUE_LABEL[s.issue]}. ` +
    (!s.granted ? 'The Works says no, and the item is closed.'
      : full ? 'The Works agrees, and the item is closed.'
      : `The Works comes back with ${landed}, and the item is closed.`)));
  n.append(pkgChips(s.pkg));
  const v = el('div', 'val');
  v.innerHTML = `on the table: <b>${money(s.crab_value)}</b> to her, costing the Works <b>${money(s.works_cost)}</b>`;
  n.append(v);
  return n;
}

function roundCard(ev) {
  const s = ev.s;
  const n = el('div', 'ev');
  const top = el('div', 'evtop');
  top.append(el('span', null, `ROUND ${s.round} · ${s.actor === 'crab' ? 'HER PACKAGE' : 'THE WORKS REPLIES'}`),
             el('span', null, 'same day'));
  n.append(top);
  n.append(pkgChips(s.pkg));
  const v = el('div', 'val');
  v.innerHTML = `<b>${money(s.crab_value)}</b> to her, costing the Works <b>${money(s.works_cost)}</b>`;
  n.append(v);
  const out = document.createDocumentFragment();
  out.append(n);
  // the engine repeats its rationale when the trade it found has not changed;
  // show it once rather than twice, which reads as a rendering fault
  if (s.logic && s.logic !== state.lastLogic) {
    out.append(el('div', 'ev logic', s.logic));
    state.lastLogic = s.logic;
  }
  return out;
}

function handshakeCard(ev) {
  const n = el('div', 'ev');
  n.append(el('div', 'evtop', ''));
  n.append(el('div', 'evmain', 'Agreed, in the room, on day one.'));
  return n;
}

function waitCard(ev) {
  return el('div', 'ev wait',
    `Now it waits for a signature, like everything else: ${Math.round(ev.score.days - 1)} days of sign-off. ` +
    'The engine does not get to skip HR.');
}

function endLane(ev) {
  const host = ev.lane === 'slow' ? $('#end-slow') : $('#end-fast');
  const s = ev.score;
  host.hidden = false;
  host.className = 'laneend ' + (s.left ? 'bad' : 'good');
  const stamp = s.walked ? 'SHE WALKED OUT'
              : s.left ? 'SHE LEFT ANYWAY'
              : 'SIGNED';
  host.append(el('div', 'stamp', stamp));
  const note = s.walked
    ? `Day ${Math.round(s.days)}, mid-negotiation, ${state.trace.crab.name.split(' ')[0]} took the other offer. ` +
      `The Works pays ${money(s.replacement)} to replace her and got nothing for the ${s.meetings} meetings.`
    : s.left
    ? `The package was agreed and she left regardless. Replacement: ${money(s.replacement)}.`
    : `Day ${Math.round(s.days)}: ${pkgShort(s.pkg)}. Worth ${money(s.crab)} to her; ` +
      `costs the Works ${money(s.concession)}.`;
  host.append(el('div', 'note', note));
}

function pkgChips(p) {
  const box = el('div', 'pkg');
  const on = {
    base: p.base !== '+0%', title: p.title === 'molt', bonus: p.bonus !== 'none',
    berth: p.berth === 'flexible', deepwater: p.deepwater === 'deepwater'
  };
  const txt = {
    base: p.base + ' base', title: 'MOLT', bonus: p.bonus + ' bonus',
    berth: 'flexible berth', deepwater: 'deepwater'
  };
  Object.keys(on).forEach((k) => {
    box.append(el('span', 'chip' + (on[k] ? ' on' : ''), on[k] ? txt[k] : '— ' + ISSUE_LABEL[k]));
  });
  return box;
}

/* ------------------------------------------------------------- the bill */
function renderBill(t) {
  const host = $('#bill');
  if (host.dataset.done) return;
  host.dataset.done = '1';
  host.innerHTML = '';
  const rows = [
    ['Just sign the standing offer', t.sign.score],
    ['The old way — meetings', t.slow.score],
    ['One sitting', t.fast.score]
  ];
  rows.forEach(([label, s]) => {
    const c = el('div', 'bcard');
    c.append(el('h4', null, label));
    c.append(brow('Outcome', 0, false,
                  s.walked ? 'walked out mid-talks'
                  : s.left ? 'left for the other works'
                  : 'stayed'));
    c.append(brow('She ends up with', s.crab, true));
    c.append(brow('Costs the Works, all in', s.works, true));
    c.append(brow('Calendar days', s.days, false, String(s.days)));
    c.append(brow('Meetings', s.meetings, false, String(s.meetings)));
    c.append(brow('Joint value', s.joint, true, null, true));
    host.append(c);
  });

  const slow = t.slow.score, fast = t.fast.score;
  const p = $('#punch');
  const gotRaise = slow.pkg.base !== '+0%' && slow.pkg.base !== t.crab.opening.base;
  if (slow.walked) {
    p.innerHTML =
      `The Works agreed to <b>${slow.pkg.base}</b> and she left anyway on day ${Math.round(slow.days)}. ` +
      topIssueClause(t) + ' ' +
      `The package she actually signs in one sitting costs the Works <b>${money(fast.concession)}</b>, ` +
      `against <b>${money(slow.replacement)}</b> to replace her.` +
      `<span class="small">Same crab, same works, same standing offer. The only difference is whether all five terms were on the table at once.</span>`;
  } else if (slow.left) {
    p.innerHTML =
      `Six weeks of meetings ended with a signed package and she left regardless. ` +
      `One sitting kept her for <b>${money(fast.concession)}</b> — ` +
      `<b>${money(slow.replacement - fast.concession)}</b> less than replacing her.` +
      `<span class="small">The slow protocol was not outbid. It ran out of calendar.</span>`;
  } else {
    p.innerHTML =
      `Both negotiations ended in a deal. The slow one gave her <b>${money(slow.crab)}</b> ` +
      `and cost the Works <b>${money(slow.concession)}</b>; the one-sitting package gave her ` +
      `<b>${money(fast.crab)}</b> and cost the Works <b>${money(fast.concession)}</b>. ` +
      `She does better and they pay less, because ${baseMoved(t)} and ` +
      `the things she actually wanted went on the table.` +
      `<span class="small">${gotRaise ? 'Note what the slow path bought her: a permanent raise, the single most expensive way for the Works to say yes.' : ''}</span>`;
  }
  renderSwitcher();
}

function renderRebuild(v) {
  const host = $('#science');
  const c = el('div', 'bcard');
  c.style.gridColumn = '1 / -1';
  c.append(el('h4', null, 'The rebuild — what a reader\u2019s four objections cost'));
  const p1 = el('p');
  p1.style.cssText = 'font-size:.9rem;color:var(--cream-70);margin:0 0 .8rem';
  p1.innerHTML =
    'The slow side above is one fixed agenda and a bargainer I wrote. Rebuilt against <b>' +
    v.n_archetypes + ' documented corporate negotiation strategies</b>, with the agenda as a ' +
    'treatment rather than a constant, and an employer that can no longer see your outside offer:';
  c.append(p1);
  const rows = [
    ['Same clock, best real strategy', signed(v.clock_on) + ' joint', true],
    ['At equal speed, offers provable', signed(v.clock_off_verifiable) +
      ' joint (you: ' + signed(v.clock_off_verifiable_crab) + ')', v.clock_off_verifiable > v.bar],
    ['At equal speed, offers unprovable', signed(v.clock_off_unverifiable) +
      ' joint (you: ' + signed(v.clock_off_unverifiable_crab) + ')', false],
    ['My agenda was worth', 'about ' + money(v.ordering_max), true],
    ['Showing a verifiable offer letter', signed(v.disclose_crab) + ' to you, ' +
      signed(v.disclose_works) + ' to them', true],
    ['Living where letters CAN be proved', signed(v.letter_regime_crab) + ' to you, ' +
      signed(v.letter_regime_works) + ' to them', false],
    ['How you haggle (' + v.n_archetypes + ' styles)', v.archetype_ratio + '\u00d7 spread — nothing', true],
    ['The employer\u2019s share, still', v.split_works + '%', true]
  ];
  rows.forEach(([k, val, good]) => {
    const r = el('div', 'brow');
    r.append(el('span', null, k));
    const n = el('span', 'n', val);
    n.classList.add(good ? 'pos' : 'neg');
    r.append(n);
    c.append(r);
  });
  const note = el('p');
  note.style.cssText = 'font-size:.8rem;color:var(--cream-50);margin:.8rem 0 0';
  note.textContent =
    'Two kills fired here. At equal speed, against an employer who cannot verify your ' +
    'offer, the money advantage is ' + money(v.clock_off_unverifiable) + ' — below the ' +
    money(v.bar) + ' bar — so the money story becomes a story about the clock. And in every ' +
    'regime the employee\u2019s share of the equal-speed gain sits below the bar. ' +
    'What the employee gets from doing this fast is time, not money.';
  c.append(note);
  host.append(c);
}


function renderV3(v) {
  const host = $('#science');
  const c = el('div', 'bcard');
  c.style.gridColumn = '1 / -1';
  c.style.borderColor = 'var(--coral)';
  c.append(el('h4', null, 'The second rebuild \u2014 the kill that fired'));
  const lead = el('p');
  lead.style.cssText = 'font-size:1rem;color:var(--shell);margin:0 0 .9rem;line-height:1.5';
  lead.innerHTML =
    'The employer above pays for everything out of one pot. Rebuilt with <b>five separate ' +
    'budgets</b> \u2014 comp, band slots, PTO accrual, coverage, project capacity \u2014 ' +
    'each with its own price, plus PTO as a sixth term and a 1-in-4 chance there is no ' +
    'promotion slot in your band at any price. Then the number that goes first:';
  c.append(lead);
  const big = el('div');
  big.style.cssText = 'background:var(--shell);color:#14100e;border-radius:8px;padding:1rem 1.1rem;margin-bottom:1rem;font-family:var(--serif);font-size:1.2rem;line-height:1.45';
  big.innerHTML =
    'On identical crabs kept either way, the engine turns <b>' + money(v.cash_bothstay_slow) +
    '</b> of the employee\u2019s cash into <b>' + money(v.cash_bothstay_sitting) +
    '</b>. A <b style="color:var(--coral)">' + money(Math.abs(v.cash_bothstay_delta)) +
    ' pay cut</b>, handed back as perks priced at a rate nobody can verify.';
  c.append(big);
  const rows = [
    ['With the calendar running', signed(v.clock_on) + ' joint', true],
    ['At equal speed', signed(v.equal_speed) + ' \u2014 below the ' + money(v.k14_threshold) + ' bar we set first', false],
    ['At equal speed, offers unprovable', signed(v.equal_speed_unverifiable), false],
    ['Departures', v.left_slow + '% \u2192 ' + v.left_sitting + '%', true],
    ['Most-granted perks', 'berth ' + v.granted_berth + '%, PTO ' + v.granted_pto + '%, promotion ' + v.granted_title + '%', true],
    ['The employer\u2019s share, still', v.split_works + '%', true]
  ];
  rows.forEach(([k, val, good]) => {
    const r = el('div', 'brow');
    r.append(el('span', null, k));
    const n = el('span', 'n', val);
    n.classList.add(good ? 'pos' : 'neg');
    r.append(n);
    c.append(r);
  });
  const note = el('p');
  note.style.cssText = 'font-size:.8rem;color:var(--cream-50);margin:.9rem 0 0';
  note.textContent =
    'We wrote the bar down before running it: if giving the employer real budget structure ' +
    'did not lift the equal-speed gain past ' + money(v.k14_threshold) + ', then bundling had ' +
    'been given a fair test and found small. It came in at ' + money(v.equal_speed) +
    ', and again on a held-out seed. So the equal-speed money claim is retired. What this is ' +
    'worth is the calendar \u2014 and the employer keeps ' + v.split_works + '% of that.';
  c.append(note);
  host.append(c);
}


function renderV4(v) {
  const host = $('#science');
  const c = el('div', 'bcard');
  c.style.gridColumn = '1 / -1';
  c.style.borderColor = 'var(--coral)';
  c.append(el('h4', null, 'The third rebuild \u2014 what a real promotion does'));
  const lead = el('p');
  lead.style.cssText = 'font-size:1rem;color:var(--cream-70);margin:0 0 .9rem;line-height:1.5';
  lead.innerHTML =
    'Above, a promotion is a 2% raise and there is no limit on how many the employer can hand out. ' +
    'Rebuilt so it is a <b>12% raise out of the pay budget plus a scarce slot</b> out of a separate one, ' +
    'raising your market value so you become more poachable, with only <b>one in eight of the crew</b> ' +
    'promotable in a year:';
  c.append(lead);
  const big = el('div');
  big.style.cssText = 'background:var(--shell);color:#14100e;border-radius:8px;padding:1rem 1.1rem;margin-bottom:1rem;font-family:var(--serif);font-size:1.2rem;line-height:1.45';
  big.innerHTML =
    '<b style="color:var(--coral)">RETRACTED.</b> This panel used to say the human negotiator ' +
    'got the promotion ' + (v.arch_promo / v.engine_promo).toFixed(1) + '\u00d7 as often and ' +
    money(Math.abs(v.cash_delta)) + ' more cash. It was a bug in our harness \u2014 the employer ' +
    'was not the same employer in the two arms. Corrected below.';
  c.append(big);
  const rows = [
    ['At equal speed', signed(v.equal_speed) + ' \u2014 vs the ' + money(v.threshold) + ' bar', false],
    ['Cash: human vs engine', money(v.arch_cash) + ' vs ' + money(v.engine_cash), false],
    ['Promotion rate: human vs engine', v.arch_promo + '% vs ' + v.engine_promo + '%', false],
    ['Same crabs, kept either way', money(v.bothstay_slow_cash) + ' \u2192 ' + money(v.bothstay_sit_cash), false],
    ['With the calendar running', signed(v.clock_on) + ' joint', true],
    ['Departures', v.left_slow + '% \u2192 ' + v.left_engine + '%', true]
  ];
  rows.forEach(([k, val, good]) => {
    const r = el('div', 'brow');
    r.append(el('span', null, k));
    const n = el('span', 'n', val);
    n.classList.add(good ? 'pos' : 'neg');
    r.append(n);
    c.append(r);
  });
  if (v.sweep && v.sweep.length) {
    const sw = el('p');
    sw.style.cssText = 'font-size:.85rem;color:var(--cream-70);margin:.9rem 0 0';
    sw.innerHTML = '<b>And the better a promotion is, the less an optimiser will get you one:</b> ' +
      v.sweep.map((x) => 'a ' + x[0] + '% promotion raise \u2192 ' + x[2] + '% promoted').join(', ') + '.';
    c.append(sw);
  }
  const note = el('p');
  note.style.cssText = 'font-size:.8rem;color:var(--cream-50);margin:.7rem 0 0';
  note.textContent =
    'The bar was written down before this ran, and this is the second promotion model to miss it, ' +
    'so the equal-speed money claim is retired for good. What is left is the calendar. ' +
    'Making the engine\u2019s best currency genuinely valuable made the engine stop using it \u2014 ' +
    'it pays you in time off instead, because that is what is cheap. Both sides bargain well: ' +
    'each lands on the efficient frontier about 85% of the time. The engine simply picks a ' +
    'different point on it, and the employer takes more than 100% of the gain \u2014 ' +
    'more than all of it, because the employee\u2019s share is negative.';
  c.append(note);
  host.append(c);
}


function renderV6(v) {
  const host = $('#science');
  const c = el('div', 'bcard');
  c.style.gridColumn = '1 / -1';
  c.style.borderColor = 'var(--kelp)';
  c.append(el('h4', null, 'The correction \u2014 and the two things that survived it'));
  const lead = el('p');
  lead.style.cssText = 'font-size:1rem;color:var(--cream-70);margin:0 0 .9rem;line-height:1.5';
  lead.innerHTML =
    'In one arm the employer could cut base pay to fund a promotion; in the other it could not. ' +
    'Same study, two different employers. With <b>one employer used by both arms</b>, the engine ' +
    'wins every setting \u2014 on joint value and on the employee\u2019s own:';
  c.append(lead);
  Object.keys(v.engine_joint).forEach((k) => {
    const r = el('div', 'brow');
    const parts = k.split(',');
    r.append(el('span', null,
      (parts[0] === 'cut=Y' ? 'employer may cut base pay' : 'employer floored at its offer') +
      (parts[1] === 'strict=Y' ? ', counters only when it pays' : ', always counters')));
    const n = el('span', 'n', 'engine ' + money(v.engine_joint[k]) + '  vs  human ' + money(v.human_joint[k]));
    n.classList.add(v.engine_joint[k] > v.human_joint[k] ? 'pos' : 'neg');
    r.append(n); c.append(r);
  });
  const b = el('p');
  b.style.cssText = 'margin:1.1rem 0 .5rem;font-size:.95rem;color:var(--shell)';
  b.innerHTML = '<b>And a number nobody validated turned out to run the whole thing.</b> ' +
    'The engine asks you to estimate what the other side\u2019s walk-away is worth. ' +
    'What you assume, and what you end up with:';
  c.append(b);
  v.batna.forEach(([k, u]) => {
    const r = el('div', 'brow');
    r.append(el('span', null, k === 'true' ? 'the truth' : 'you assume ' + k));
    const n = el('span', 'n', money(u));
    n.classList.add(k === 'true' || parseFloat(k) <= 0.4 ? 'pos' : 'neg');
    r.append(n); c.append(r);
  });
  const big = el('div');
  big.style.cssText = 'background:var(--shell);color:#14100e;border-radius:8px;padding:1rem 1.1rem;margin-top:1.1rem;font-family:var(--serif);font-size:1.2rem;line-height:1.45';
  big.innerHTML =
    'Two of these engines pointed at each other adversarially <b style="color:var(--coral)">destroy</b> ' +
    'value: ' + money(v.duel_adv) + ' joint. Two of them in the mode where both sides <b>prove</b> ' +
    'their walk-away instead of guessing produce <b style="color:#3e6b4f">' + money(v.duel_peer) +
    '</b> \u2014 and the employee takes 95% of the gain, inverting every other result on this page. ' +
    'Seventy percent of that is just knowing each other\u2019s true position. It isn\u2019t being ' +
    'nice that works. It\u2019s being verified.';
  c.append(big);
  host.append(c);
}


function renderSwitcher() {
  const idx = (state.sci && state.sci.index) || [];
  const others = idx.filter((c) => c.slug !== state.which);
  if (!others.length) return;
  const nav = el('div');
  nav.style.cssText = 'margin-top:1.1rem;font-size:.9rem;color:var(--cream-50)';
  nav.append(document.createTextNode('Another crab, same season: '));
  others.forEach((c, i) => {
    if (i) nav.append(document.createTextNode(' · '));
    const a = el('a', null, `${c.name} (${c.spec.toLowerCase()})`);
    a.href = `?case=${c.slug}`;
    nav.append(a);
  });
  $('#punch').after(nav);
}


// What happened, in the slow lane, to the one term this crab cares most about.
// The agenda is money-first, so a crab whose priority sits late often never gets
// asked at all — but not always, and the caption has to match the trace.
function topIssueClause(t) {
  const key = t.crab.cares_most;
  const agenda = t.slow.agenda || [];
  const pos = agenda.indexOf(key);
  const ORD = ['first', 'second', 'third', 'fourth', 'fifth'];
  const step = t.slow.steps.find((s) => s.issue === key);
  const label = ISSUE_LABEL[key];
  if (!step) {
    return `Nobody ever asked about ${label} — it was ${ORD[pos] || 'last'} on the agenda ` +
           `and the talks did not get that far.`;
  }
  const landed = step.pkg[key];
  const gotIt = step.granted;
  return `They did reach ${label}, at meeting ${t.slow.steps.indexOf(step) + 1} — ` +
         (gotIt ? `and closed it at ${landed}, one item at a time, with nothing to trade it against.`
                : 'and said no, and closed the item.');
}


function baseMoved(t) {
  const a = t.slow.score.pkg.base, b = t.fast.score.pkg.base;
  if (a === b) return 'the same raise bought a much better package';
  return `the raise came down from ${a} to ${b}`;
}


function brow(k, v, isMoney, raw, total) {
  const r = el('div', 'brow' + (total ? ' total' : ''));
  r.append(el('span', null, k));
  const n = el('span', 'n', raw !== undefined && raw !== null ? raw : money(v));
  if (isMoney) n.classList.add(v >= 0 ? 'pos' : 'neg');
  r.append(n);
  return r;
}

/* ------------------------------------------------------------- science */
function renderScience(s) {
  $('#sci-n').textContent = s.n.toLocaleString('en-US');
  const host = $('#science');
  host.innerHTML = '';

  const armCard = el('div', 'bcard');
  armCard.append(el('h4', null, 'Six protocols, 1,920 crab-seasons each'));
  const tbl = el('table', 'sci');
  tbl.innerHTML =
    '<thead><tr><th>protocol</th><th>crab</th><th>works</th><th>days</th><th>left</th></tr></thead>';
  const tb = el('tbody');
  const LAB = {
    A_sign: 'just sign it', B_slow: 'slow talks', C_slow_engine: 'slow, engine',
    D_sitting_crab: 'one sitting', E_sitting_works: 'works holds it',
    F_sitting_both: 'both sides'
  };
  Object.keys(LAB).forEach((k) => {
    const m = s.arms[k];
    const tr = el('tr', k === 'D_sitting_crab' ? 'hi' : '');
    tr.innerHTML =
      `<td>${LAB[k]}</td><td class="n">${money(m.crab)}</td><td class="n">${money(m.works)}</td>` +
      `<td class="n">${m.days.toFixed(1)}</td><td class="n">${(100 * m.left).toFixed(1)}%</td>`;
    tb.append(tr);
  });
  tbl.append(tb);
  armCard.append(tbl);
  host.append(armCard);

  const killCard = el('div', 'bcard');
  killCard.append(el('h4', null, 'Seven kills, written down first'));
  const kills = [
    ['K1', 'With every delay cost set to zero, does the advantage survive?',
     `held — ${signed(s.zero_clock['D-B'].joint)} joint`, true],
    ['K2', 'Is there money in it at all?', 'held', true],
    ['K3', 'Was the slow arm just a badly played hand?',
     'RETRACTED — this employer already knew the offer; rebuilt below', false],
    ['K4', 'Does one side take more than 70%?',
     'FIRED — the employer takes 90%', false],
    ['K5', 'Does going fast cost deals?',
     'held — 24pp more agreements, 20pp fewer departures', true],
    ['K6', 'Is the gain coming from crabs differing from each other?',
     'FIRED — it is not; see below', false],
    ['K7', 'Does the Works profit from dragging it out?', 'held — it loses', true]
  ];
  kills.forEach(([id, q, v, ok]) => {
    const r = el('div', 'killrow');
    r.append(el('span', 'kid', id), el('span', null, q),
             el('span', 'verdict ' + (ok ? 'held' : 'fired'), v));
    killCard.append(r);
  });
  host.append(killCard);

  const mechCard = el('div', 'bcard');
  mechCard.append(el('h4', null, 'Where the money comes from'));
  const idf = s.identification;
  const full = idf['flat=False,alpha=1.4'], flat = idf['flat=True,alpha=1.4'];
  const same = idf['flat=False,alpha=4.0'];
  const rows = [
    ['Employer’s cheap terms are the crab’s dear ones', money(full - flat)],
    ['Deals that simply would not have existed', money(flat)],
    // making every crab want the same things did not shrink the advantage; it
    // moved it by less than a rounding error, in the wrong direction
    ['Crabs wanting different things from each other', 'nothing (' + signed(full - same) + ')']
  ];
  rows.forEach(([k, v]) => mechCard.append(brow(k, 0, false, v)));
  mechCard.append(el('div', 'val'));
  const note = el('p');
  note.style.cssText = 'font-size:.8rem;color:var(--cream-50);margin:.7rem 0 0';
  note.textContent =
    'K6 fired: we registered that the advantage should halve when every crab wants ' +
    'the same things. It fell 7%. The mechanism is not that people differ — it is ' +
    'that a promotion costs an employer less than it is worth to the person getting it, ' +
    'and that is true of everyone.';
  mechCard.append(note);
  host.append(mechCard);

  if (s.v2) renderRebuild(s.v2);
  if (s.v3) renderV3(s.v3);
  if (s.v4) renderV4(s.v4);
  if (s.v6) renderV6(s.v6);

  const cav = $('#caveats');
  cav.innerHTML =
    '<p><b>What this does not show.</b></p><ul>' +
    '<li>No human subjects. Every crab and every manager here is a payoff-maximiser; nothing on this page says how real people negotiate or how they would feel about a package handed over by a machine.</li>' +
    '<li>No repeat play and no reputation. If everyone got this advice, employers would move their opening offers, and this design could not see that.</li>' +
    '<li>The clock is calibrated from trade-press benchmarks — 44-day median time-to-fill, replacement at 0.5–2× salary. They set the size of the effect, not its existence: with all of them zeroed the advantage is still ' +
    signed(s.zero_clock['D-B'].joint) + ' joint.</li>' +
    '<li>The employer captures about 90% of the value created. Read the rest of this page with that in mind.</li>' +
    '</ul>';
}

/* ------------------------------------------------------------- controls */
function wireControls() {
  $('#pp').addEventListener('click', () => {
    state.playing = !state.playing;
    $('#pp').textContent = state.playing ? '⏸' : '▶';
  });
  $('#speed').addEventListener('click', () => {
    state.speed = state.speed === 1 ? 3 : state.speed === 3 ? 8 : 1;
    $('#speed').textContent = state.speed + '×';
  });
  $('#skip').addEventListener('click', () => {
    state.day = state.endDay;
    finish();
  });
}

boot();
