/**
 * Deeva Shine Plan — the installment schedule on the server (daily dues notification).
 * shineCalc() is an exact copy of the one in web/index.html (between SHINE-CALC-START / -END);
 * tools/test_flow.py checks that both copies are identical.
 */
/* SHINE-CALC (the same function is in web/index.html and functions/shine.js — keep both copies identical)
   Deeva Shine Plan schedule for one plan, as of the day `t` (YYYY-MM-DD) — date based (owner's rule, 24 Nov 2026):
   installments are paid in advance on the first installment date and the same date every month: 1–10 full,
   11 = half (10½). Maturity = 12 months after the first installment, minus one day (15 Sep → 14 Sep next year);
   redeem within 15 days after maturity. An installment is on time when it is paid before the next installment date;
   each full month it is late moves every later date and the maturity ahead by one month (the plan pauses).
   Early redemption after 6–10 installments: 30/40/55/70/90 % of one installment; the full plan (10½ paid) at
   maturity: 150 % (1½ installments). */
function shineCalc(p, t){
  const inst = Number(p.inst) || 0;
  const pd = s => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || ''); return m ? [+m[1], +m[2] - 1, +m[3]] : null; };
  const ds = (y, m, d) => {
    const yy = y + Math.floor(m / 12), mm = ((m % 12) + 12) % 12, last = new Date(Date.UTC(yy, mm + 1, 0)).getUTCDate();
    return yy + '-' + String(mm + 1).padStart(2, '0') + '-' + String(Math.min(d, last)).padStart(2, '0');
  };
  const plus = (s, n) => { const a = pd(s); return new Date(Date.UTC(a[0], a[1], a[2] + n)).toISOString().slice(0, 10); };
  const [y0, m0, d0] = pd(p.startDay) || pd(t);
  /* whole months from an installment's date (y, m, d) to `day`: how many later installment dates have come by then */
  const monthsLate = (y, m, d, day) => { let j = 0; while (j < 240 && ds(y, m + j + 1, d) <= day) j++; return j; };
  const voids = p.void || {};
  const pays = Object.entries(p.payments || {}).filter(([k]) => !voids[k])
    .map(([k, x]) => ({k, amount: Number(x.amount) || 0, day: x.day || t, at: x.at || 0}))
    .sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : a.at - b.at));
  const paid = pays.reduce((s, x) => s + x.amount, 0);
  const items = [];
  for (let i = 0; i < 11; i++) items.push({n: i + 1, half: i === 10, amt: i === 10 ? inst / 2 : inst, y: y0, m: m0 + i, d: d0});
  let cum = 0, run = 0, pi = 0, shift = 0, next = null;
  for (const it of items) {
    cum += it.amt;
    while (pi < pays.length && run + 0.5 < cum) { run += pays[pi].amount; pi++; }
    it.due = ds(it.y, it.m + shift, it.d);
    if (run + 0.5 >= cum) {
      it.paid = true; it.paidDay = pays[pi - 1].day;
      it.late = monthsLate(it.y, it.m + shift, it.d, it.paidDay);
      shift += it.late;
    } else {
      it.paid = false; it.part = Math.max(0, run - (cum - it.amt));
      if (!next) next = it;
    }
  }
  /* the installment still to pay: each installment date that has passed since it was due moves the plan one month */
  const lateNow = next ? monthsLate(next.y, next.m + shift, next.d, t) : 0;
  const lateFrom = next ? ds(next.y, next.m + shift + lateNow + 1, next.d) : '';
  if (next) items.filter(it => !it.paid && it !== next).forEach(it => { it.due = ds(it.y, it.m + shift + lateNow, it.d); });
  const moved = shift + lateNow;
  let maturity = plus(ds(y0, m0 + 12 + moved, d0), -1), redeemBy = plus(maturity, 15);
  if (p.matDay && pd(p.matDay)) { maturity = p.matDay; redeemBy = plus(p.matDay, 15); }
  const total = inst * 10.5;
  const full = inst > 0 && paid + 0.5 >= total;
  const n = inst > 0 ? Math.min(10, Math.floor((paid + 0.5) / inst)) : 0;
  const matured = t >= maturity;
  const LADDER = {6: 0.3, 7: 0.4, 8: 0.55, 9: 0.7, 10: 0.9};
  const pct = full && matured ? 1.5 : (LADDER[n] || 0);
  const left = next ? next.amt - next.part : 0;
  return {
    inst, items, pays, paid, total, full, n, next, left, moved, shift, lateNow, lateFrom, maturity, redeemBy, matured, pct,
    bonus: Math.round(inst * pct), due: next ? next.due : '', overdue: !!(next && next.due < t),
    dueDays: next ? Math.round((Date.UTC(...pd(next.due)) - Date.UTC(...pd(t))) / 86400000) : null
  };
}

/* today in India (the store's day), YYYY-MM-DD */
function todayIST(now) { return new Date((now || Date.now()) + 5.5 * 3600e3).toISOString().slice(0, 10); }
const inr = n => '₹' + Math.round(Number(n) || 0).toLocaleString('en-IN');

/* one line per store: who pays today, who is overdue, which full plans are ready to redeem */
function digest(plans, t) {
  const by = {};
  for (const p of plans) {
    if (p.status !== 'active') continue;
    const c = shineCalc(p, t);
    const s = by[p.storeId] || (by[p.storeId] = { store: p.storeName || '', today: 0, todayAmt: 0, over: 0, overAmt: 0, soon: 0, ready: 0 });
    if (c.next && c.due === t) { s.today++; s.todayAmt += c.left; }
    else if (c.overdue) { s.over++; s.overAmt += c.left; }
    else if (c.next && c.dueDays > 0 && c.dueDays <= 2) s.soon++;
    if (c.full && c.matured) s.ready++;
  }
  return by;
}
function digestText(s) {
  const parts = [];
  if (s.today) parts.push(s.today + ' due today (' + inr(s.todayAmt) + ')');
  if (s.over) parts.push(s.over + ' overdue (' + inr(s.overAmt) + ')');
  if (s.soon) parts.push(s.soon + ' due in 2 days');
  if (s.ready) parts.push(s.ready + ' ready to redeem');
  return parts.join(' · ');
}

module.exports = { shineCalc, todayIST, digest, digestText, inr };
