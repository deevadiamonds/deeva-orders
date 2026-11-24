/**
 * Deeva Orders — Google Sheet copy of every order (the owner's readable backup).
 *
 * The Admin pastes a Google Sheet link in the app (Team › Google Sheet backup); it is stored in config/sheet = { id, url,
 * syncReq, status }. The owner shares that sheet (Editor) with this server's Google account (shown in the app).
 * Three tabs are kept:
 *   All orders     — one row per order: order details + estimate + photo, then the dispatch summary once dispatched
 *   Orders placed  — a row is added when an order is placed
 *   Dispatched     — a row is added when the factory dispatches
 * Saving the link (or "Sync all again") rewrites the three tabs from the database.
 *
 * 💎 Deeva Shine Plan (savings plan) — three more tabs in the same sheet, rewritten whenever a member or payment changes,
 * and every morning (so "overdue" stays current):
 *   Shine members  — one row per member: details, nominee, installment, paid, next due, overdue, maturity, redemption
 *   Shine payments — one row per payment: receipt no., date, amount, mode, paid by / from, reference, cancelled, proof photo
 *   Shine dues     — every installment of every active member, by date: paid on / overdue / upcoming
 */
const { GoogleAuth } = require('google-auth-library');
const admin = require('firebase-admin');
const shine = require('./shine');

const API = 'https://sheets.googleapis.com/v4/spreadsheets/';
const T_ALL = 'All orders', T_PLACED = 'Orders placed', T_DISP = 'Dispatched';
const T_SM = 'Shine members', T_SP = 'Shine payments', T_SD = 'Shine dues';
const TABS = [T_ALL, T_PLACED, T_DISP, T_SM, T_SP, T_SD];
const STATUS = { review: 'Awaiting approval', query: 'Query', factory: 'In factory', dispatched: 'Dispatched', received: 'At store', delivered: 'Delivered', cancelled: 'Cancelled' };

const ORDER_HEAD = ['Order no.', 'Order date', 'Store', 'Taken by', 'Client', 'Phone', 'City', 'Item', 'Purity', 'Metal colour', 'Size', 'Diamonds (as ordered)',
  'Gemstones', 'Design / remarks', 'Delivery date', 'Priority', 'Gold rate booked', 'Gold rate ₹/g', 'Gross wt g', 'Net gold g', 'Gold ₹', 'Diamonds ₹', 'Making ₹',
  'Gemstone + other ₹', 'GST ₹', 'Estimate total ₹', 'Agreed amount ₹', 'Paid at order ₹', 'Photo', 'Photo link', 'Open in app'];
const DISP_HEAD = ['Dispatched on', 'Actual gross g', 'Actual net g', 'Diamonds (actual, by size)', 'Gemstones (actual)', 'Hallmark / HUID', 'Shipping', 'Dispatch note',
  'Factory gold', 'Factory stones ₹', 'Factory labour ₹', 'Factory other ₹', 'Factory total ₹', 'Dispatch photo'];
const HEAD = {
  [T_ALL]: ['Status'].concat(ORDER_HEAD, DISP_HEAD, ['Factory']),
  [T_PLACED]: ORDER_HEAD,
  [T_DISP]: ['Order no.', 'Store', 'Client', 'Item', 'Purity', 'Agreed amount ₹'].concat(DISP_HEAD, ['Open in app', 'Factory']),
  [T_SM]: ['Account no.', 'Status', 'Store', 'Member', 'Mobile', 'Alternate mobile', 'Email', 'Address', 'City', 'Date of birth', 'Anniversary', 'Photo ID',
    'Nominee', 'Monthly installment ₹', 'First installment date', 'Paid ₹', 'Installments paid (of 10½)', 'Balance ₹', 'Next due date', 'Next due ₹', 'Overdue',
    'Maturity moved (months)', 'Maturity', 'Redeem by', 'Payments', 'Last payment', 'Last reminder', 'Redeemed on', 'Deeva contribution ₹', 'Plan value ₹',
    'Jewellery bill no.', 'Jewellery taken', 'Enrolled on', 'Enrolled by', 'Closed / note', 'Open in app'],
  [T_SP]: ['Receipt no.', 'Date', 'Account no.', 'Member', 'Mobile', 'Store', 'Amount ₹', 'Mode', 'Paid by / from', 'Reference', 'Note', 'Received by', 'Entered at',
    'Status', 'Receipt sent on WhatsApp', 'Proof photo', 'Proof link', 'Open in app'],
  [T_SD]: ['Due date', 'Account no.', 'Member', 'Mobile', 'Store', 'Installment', 'Amount ₹', 'Status', 'Paid on', 'Open in app']
};

const auth = new GoogleAuth({ scopes: ['https://www.googleapis.com/auth/spreadsheets'] });
let robot = '';
async function robotEmail() {
  if (robot) return robot;
  try { robot = (await auth.getCredentials()).client_email || ''; } catch (e) { /* ignore */ }
  return robot || (process.env.GCLOUD_PROJECT_NUMBER ? process.env.GCLOUD_PROJECT_NUMBER + '-compute@developer.gserviceaccount.com' : 'the Deeva Orders server account');
}
async function api(method, url, data) {
  const client = await auth.getClient();
  try {
    const r = await client.request({ url, method, data });
    return r.data;
  } catch (e) {
    const st = e && e.response && e.response.status;
    const msg = (e && e.response && e.response.data && e.response.data.error && e.response.data.error.message) || (e && e.message) || String(e);
    const err = new Error(st === 403 || st === 401
      ? (/has not been used|is disabled/i.test(msg) ? 'Google Sheets is not switched on for this project yet — it is turned on with the next update.' : 'No access to the sheet — please share it (Editor) with ' + await robotEmail())
      : st === 404 ? 'Sheet not found — please check the link.' : msg);
    err.status = st;
    throw err;
  }
}
const q = t => encodeURIComponent("'" + t + "'");

/* ---------- formatting ---------- */
const n = v => { const x = parseFloat(v); return isFinite(x) ? x : 0; };
const r2 = v => Math.round(n(v) * 100) / 100;
const r3 = v => Math.round(n(v) * 1000) / 1000;
const when = ms => ms ? new Date(ms).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' }) : '';
const day = s => { if (!s) return ''; const [y, m, d] = String(s).split('-').map(Number); return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-IN', { timeZone: 'UTC', day: 'numeric', month: 'short', year: 'numeric' }); };
const jtype = s => s.jtype === 'Other' ? (s.jtypeOther || 'Other') : (s.jtype || '');
const hasCt = v => v != null && String(v).trim() !== '' && String(v).trim().toUpperCase() !== 'NA' && n(v) > 0;
const image = url => url ? '=IMAGE("' + String(url).replace(/"/g, '""') + '")' : '';
const txt = v => { const s = String(v == null ? '' : v); return /^[=+\-@]/.test(s) ? "'" + s : s; };   /* never let typed text become a formula */

function diamondsOrdered(s) {
  return [1, 2, 3, 4].filter(i => hasCt(s['dia' + i + 'Ct'])).map(i => {
    const p = 'dia' + i;
    return 'D' + i + (s[p + 'Type'] ? ' ' + s[p + 'Type'] : '') + ': ' + [s[p + 'Ct'] + ' ct', s[p + 'Pcs'] ? s[p + 'Pcs'] + ' pcs' : '', s[p + 'Shape'], s[p + 'Color'], s[p + 'Clarity'], s[p + 'Cut'] && s[p + 'Cut'] !== 'NA' ? s[p + 'Cut'] : '', s[p + 'Cert']].filter(Boolean).join(' · ');
  }).join('\n');
}
function gemsOrdered(s) {
  return [1, 2].filter(i => s['gem' + i + 'Type']).map(i => { const g = 'gem' + i; return [s[g + 'Type'], s[g + 'Color'], s[g + 'Shape'], n(s[g + 'Ct']) ? s[g + 'Ct'] + ' ct' : '', s[g + 'Size'], s[g + 'Pcs'] ? s[g + 'Pcs'] + ' pcs' : ''].filter(Boolean).join(' · '); }).join('\n');
}
function firstImage(map, pref) {
  const list = Object.values(map || {}).filter(m => m && !m.deleted && m.url && m.kind === 'image' && !m.receipt).sort((a, b) => (a.at || 0) - (b.at || 0));
  return (pref && list.find(pref)) || list[0] || null;
}
function orderCols(id, o, p, appUrl) {
  const s = o.spec || {}, pr = (p && p.price) || {}, c = (p && p.client) || {}, k = pr.calc || {};
  const paid = Object.values((p && p.payments) || {}).filter(x => !x.deleted && (x.at || 0) <= (o.createdAt || 0) + 60e3).reduce((a, x) => a + n(x.amount), 0);
  const img = firstImage(o.media, m => !m.stage) || firstImage(p && p.media);
  return [txt(o.no), day(o.orderDay), txt(o.storeName || ''), txt(String(o.createdByName || '').split(' · ')[0]), txt(c.name), txt(c.phone), txt(c.city),
    txt(jtype(s) + (s.qty && s.qty !== '1' ? ' × ' + s.qty : '')), txt(s.purity), txt(s.metalColor), txt(s.size), txt(diamondsOrdered(s)), txt(gemsOrdered(s)),
    txt([s.design, s.stoneNote, s.engraving ? 'Engraving: ' + s.engraving : ''].filter(Boolean).join('\n')), day(o.deliveryDay), o.priority === 'urgent' ? 'Urgent' : 'Normal',
    pr.goldRateBooked === 'yes' ? 'Yes' : pr.goldRateBooked === 'no' ? 'No' : '', n(k.goldRate || pr.goldRate) || '', r3(k.gross) || '', r3(k.net) || '',
    r2(k.gold) || '', r2(k.diaTotal) || '', r2(k.mk) || '', r2(n(k.gem) + n(k.oth)) || '', r2(k.gstAmt) || '', r2(k.final) || '', n(pr.est) || '', paid || '',
    image(img && img.url), img ? img.url : '', appUrl + '#/o/' + id];
}
function dispCols(o, bill) {
  const d = o.dispatch || {}, a = d.actual || {};
  if (!d.at) return DISP_HEAD.map(() => '');
  const dias = (a.dias || []).map(x => {
    const name = (x.n > 4 ? 'Extra ' + (x.n - 4) : 'D' + x.n) + (x.type ? ' ' + x.type : '');
    const parts = (x.parts || []).length > 1 ? ' [' + x.parts.map(p => [p.size, p.shape, p.color, p.clarity].filter(Boolean).join(' ') + ' ' + p.ct + ' ct/' + p.pcs + ' pc').join('; ') + ']' : '';
    return name + ': ' + x.ct + ' ct / ' + x.pcs + ' pc' + parts + (x.cert === 'yes' ? ' · certified' + (x.certNo ? ' ' + x.certNo : '') : '');
  }).join('\n');
  const gems = (a.gems || []).map(x => x.type + ': ' + x.ct + ' ct / ' + x.pcs + ' pc').join('\n');
  const b = bill || {};
  const diaAmt = (b.lines || []).filter(l => l.kind === 'd').reduce((t, l) => t + n(l.amt), 0) + (b.lines || []).filter(l => l.kind === 'g').reduce((t, l) => t + n(l.amt), 0);
  const img = Object.values(o.media || {}).find(m => m && !m.deleted && m.url && m.kind === 'image' && m.stage === 'dispatched');
  return [when(d.at), r3(a.grossWt || d.grossWt) || '', r3(a.netWt) || '', txt(dias), txt(gems), a.hallmark === 'yes' ? 'Yes' + (a.huid ? ' · ' + a.huid : '') : a.hallmark === 'no' ? 'No' : '',
    txt([d.mode, d.ref].filter(Boolean).join(' · ')), txt(d.note || ''),
    bill ? (b.goldMode === 'fine' ? 'Fine ' + r3(b.fine) + ' g (' + b.touch + '%)' : 'Money ₹' + r2(b.goldAmt)) : '', bill ? r2(diaAmt) : '', bill ? r2(b.labour) : '', bill ? r2(b.other) : '', bill ? r2(b.total) : '',
    image(img && img.url)];
}
const allRow = (id, o, p, bill, appUrl) => [STATUS[o.status] || o.status].concat(orderCols(id, o, p, appUrl), dispCols(o, bill), [txt(o.factoryName || '')]);
const placedRow = (id, o, p, appUrl) => orderCols(id, o, p, appUrl);
function dispatchedRow(id, o, p, bill, appUrl) {
  const s = o.spec || {}, pr = (p && p.price) || {};
  return [txt(o.no), txt(o.storeName || ''), txt(((p && p.client) || {}).name), txt(jtype(s)), txt(s.purity), n(pr.est) || ''].concat(dispCols(o, bill), [appUrl + '#/o/' + id, txt(o.factoryName || '')]);
}

/* ---------- sheet plumbing ---------- */
const TABS_CACHE = { id: '', at: 0, tabs: null };
async function ensureTabs(id) {
  if (TABS_CACHE.id === id && Date.now() - TABS_CACHE.at < 10 * 60e3) return TABS_CACHE.tabs;
  const meta = await api('GET', API + id + '?fields=sheets.properties(sheetId,title)');
  const have = new Map((meta.sheets || []).map(s => [s.properties.title, s.properties.sheetId]));
  const req = [];
  const want = TABS;
  if (!have.has(T_ALL) && have.has('Sheet1') && have.size === 1) {   /* a new blank sheet: its first tab becomes "All orders" */
    req.push({ updateSheetProperties: { properties: { sheetId: have.get('Sheet1'), title: T_ALL, gridProperties: { frozenRowCount: 1 } }, fields: 'title,gridProperties.frozenRowCount' } });
    have.set(T_ALL, have.get('Sheet1')); have.delete('Sheet1');
  }
  want.forEach((t, i) => { if (!have.has(t)) req.push({ addSheet: { properties: { title: t, index: i, gridProperties: { frozenRowCount: 1 } } } }); });
  let fresh = [];
  if (req.length) {
    const r = await api('POST', API + id + ':batchUpdate', { requests: req });
    (r.replies || []).forEach(x => { if (x.addSheet) have.set(x.addSheet.properties.title, x.addSheet.properties.sheetId); });
    fresh = want;
  }
  /* headers (always rewritten, so new columns appear) + bold, tinted header row, photo column widths */
  await api('POST', API + id + '/values:batchUpdate', { valueInputOption: 'RAW', data: want.map(t => ({ range: "'" + t + "'!A1", values: [HEAD[t]] })) });
  const fmt = [];
  want.forEach(t => {
    const sid = have.get(t);
    fmt.push({ repeatCell: { range: { sheetId: sid, startRowIndex: 0, endRowIndex: 1 }, cell: { userEnteredFormat: { textFormat: { bold: true }, backgroundColor: { red: 0.9, green: 0.95, blue: 0.91 }, wrapStrategy: 'WRAP', verticalAlignment: 'MIDDLE' } }, fields: 'userEnteredFormat(textFormat,backgroundColor,wrapStrategy,verticalAlignment)' } });
    fmt.push({ updateSheetProperties: { properties: { sheetId: sid, gridProperties: { frozenRowCount: 1 } }, fields: 'gridProperties.frozenRowCount' } });
    HEAD[t].forEach((h, i) => { if (/Photo$|photo$/.test(h) && !/link/.test(h)) fmt.push({ updateDimensionProperties: { range: { sheetId: sid, dimension: 'COLUMNS', startIndex: i, endIndex: i + 1 }, properties: { pixelSize: 110 }, fields: 'pixelSize' } }); });
  });
  await api('POST', API + id + ':batchUpdate', { requests: fmt });
  const tabs = { ids: have, fresh };
  Object.assign(TABS_CACHE, { id, at: Date.now(), tabs });
  return tabs;
}
async function rowHeights(id, sheetId, from, to) {
  if (to <= from) return;
  await api('POST', API + id + ':batchUpdate', { requests: [{ updateDimensionProperties: { range: { sheetId, dimension: 'ROWS', startIndex: from, endIndex: to }, properties: { pixelSize: 90 }, fields: 'pixelSize' } }] });
}
async function append(id, tabs, tab, row) {
  const r = await api('POST', API + id + '/values/' + q(tab) + '!A1:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS', { values: [row] });
  const m = /![A-Z]+(\d+)/.exec((r.updates && r.updates.updatedRange) || '');
  if (m) await rowHeights(id, tabs.ids.get(tab), +m[1] - 1, +m[1]);
}
async function upsertAll(id, tabs, no, row) {
  const col = await api('GET', API + id + '/values/' + q(T_ALL) + '!B:B');
  const i = ((col.values || []).findIndex(v => v[0] === no));
  if (i > 0) {
    await api('PUT', API + id + '/values/' + q(T_ALL) + '!A' + (i + 1) + '?valueInputOption=USER_ENTERED', { values: [row] });
    await rowHeights(id, tabs.ids.get(T_ALL), i, i + 1);
  } else await append(id, tabs, T_ALL, row);
}

/* ---------- reading an order ---------- */
const FAC = { at: 0, names: {} };
async function facName(db, fid) {
  if (!fid) return '';
  if (Date.now() - FAC.at > 5 * 60e3 || !(fid in FAC.names)) {
    const snap = await db.collection('factories').get();
    FAC.names = Object.fromEntries(snap.docs.map(d => [d.id, d.data().name || '']));
    FAC.at = Date.now();
  }
  return FAC.names[fid] || '';
}
async function load(db, id, o) {
  const [ps, bs] = await Promise.all([db.doc('orders/' + id + '/private/info').get(), o.dispatch && o.dispatch.at ? db.doc('orders/' + id + '/factory/bill').get() : null]);
  o.factoryName = o.factoryVisible ? await facName(db, o.factoryId) : '';
  return { p: ps.exists ? ps.data() : {}, bill: bs && bs.exists ? bs.data() : null };
}
async function config(db) {
  const s = await db.doc('config/sheet').get();
  const c = s.exists ? s.data() : null;
  return c && c.id ? c : null;
}
async function mark(db, ok, msg, extra) {
  await db.doc('config/sheet').set({ status: Object.assign({ ok, msg: String(msg || '').slice(0, 300), at: Date.now() }, extra || {}) }, { merge: true });
}

/* event: 'placed' | 'status' | 'dispatched' */
async function onOrder(db, id, o, event, appUrl) {
  const c = await config(db); if (!c) return;
  try {
    const tabs = await ensureTabs(c.id);
    const { p, bill } = await load(db, id, o);
    if (event === 'placed') await append(c.id, tabs, T_PLACED, placedRow(id, o, p, appUrl));
    if (event === 'dispatched') await append(c.id, tabs, T_DISP, dispatchedRow(id, o, p, bill, appUrl));
    await upsertAll(c.id, tabs, o.no, allRow(id, o, p, bill, appUrl));
    await mark(db, true, 'Updated ' + o.no + (event === 'placed' ? ' (placed)' : event === 'dispatched' ? ' (dispatched)' : ''));
  } catch (e) {
    await mark(db, false, e.message);
    throw e;
  }
}

/* rewrite all three tabs from the database */
async function rebuild(db, appUrl) {
  const c = await config(db); if (!c) return;
  TABS_CACHE.id = '';
  try {
    await mark(db, true, 'Copying all orders to the sheet…', { working: true });
    const tabs = await ensureTabs(c.id);
    const snap = await db.collection('orders').get();
    const orders = snap.docs.map(d => ({ id: d.id, o: d.data() })).sort((a, b) => (a.o.createdAt || 0) - (b.o.createdAt || 0));
    const full = [];
    for (const x of orders) full.push(Object.assign(x, await load(db, x.id, x.o)));
    const data = {
      [T_ALL]: full.map(x => allRow(x.id, x.o, x.p, x.bill, appUrl)),
      [T_PLACED]: full.map(x => placedRow(x.id, x.o, x.p, appUrl)),
      [T_DISP]: full.filter(x => x.o.dispatch && x.o.dispatch.at).sort((a, b) => a.o.dispatch.at - b.o.dispatch.at).map(x => dispatchedRow(x.id, x.o, x.p, x.bill, appUrl))
    };
    for (const t of [T_ALL, T_PLACED, T_DISP]) {
      await api('POST', API + c.id + '/values/' + q(t) + '!A2:ZZ:clear', {});
      if (data[t].length) {
        await api('PUT', API + c.id + '/values/' + q(t) + '!A2?valueInputOption=USER_ENTERED', { values: data[t] });
        await rowHeights(c.id, tabs.ids.get(t), 1, data[t].length + 1);
      }
    }
    await mark(db, true, 'All ' + orders.length + ' orders copied', { working: false, count: orders.length });
  } catch (e) {
    await mark(db, false, e.message, { working: false });
    throw e;
  }
  await shineSync(db, appUrl, 'all orders copied too');
}

/* an order deleted permanently by the Admin: remove its rows from all three tabs */
async function removeOrder(db, no) {
  const c = await config(db); if (!c || !no) return;
  try {
    const tabs = await ensureTabs(c.id);
    const reqs = [];
    for (const [t, col] of [[T_ALL, 'B'], [T_PLACED, 'A'], [T_DISP, 'A']]) {
      const v = await api('GET', API + c.id + '/values/' + q(t) + '!' + col + ':' + col);
      const rows = (v.values || []).map((r, i) => (i > 0 && r[0] === no ? i : -1)).filter(i => i > 0).sort((a, b) => b - a);
      rows.forEach(i => reqs.push({ deleteDimension: { range: { sheetId: tabs.ids.get(t), dimension: 'ROWS', startIndex: i, endIndex: i + 1 } } }));
    }
    if (reqs.length) await api('POST', API + c.id + ':batchUpdate', { requests: reqs });
    await mark(db, true, 'Removed ' + no + ' (deleted by the Admin)');
  } catch (e) {
    await mark(db, false, e.message);
    throw e;
  }
}

/* ---------- 💎 Deeva Shine Plan ---------- */
const PSTATUS = { active: 'Active', redeemed: 'Redeemed', closed: 'Closed' };
const inst11 = it => (it.half ? '11 (half)' : String(it.n));
const nm = s => String(s || '').split(' · ')[0];
function countText(c) { return c.full ? '10½' : String(c.n) + (c.paid - c.n * c.inst > 0.5 ? ' + ₹' + Math.round(c.paid - c.n * c.inst) : ''); }
function memberRow(id, p, c, t, appUrl) {
  const cu = p.cust || {}, r = p.redeem || {}, pays = c.pays;
  const last = pays.length ? pays[pays.length - 1] : null;
  const overdue = p.status === 'active' && c.overdue ? 'Yes — since ' + day(c.due) + (c.lateNow ? ' (' + c.lateNow + ' month' + (c.lateNow > 1 ? 's' : '') + ' late)' : '') : '';
  return [txt(p.acct), PSTATUS[p.status] || p.status, txt(p.storeName), txt(p.name), txt(p.phone), txt(cu.alt), txt(cu.email), txt(cu.address), txt(cu.city), day(cu.dob), day(cu.anniv),
    txt([cu.idType, cu.idNo].filter(Boolean).join(' · ')), txt([cu.nominee, cu.nomRel ? '(' + cu.nomRel + ')' : '', cu.nomPhone].filter(Boolean).join(' ')),
    n(p.inst), day(p.startDay), r2(c.paid), countText(c), r2(Math.max(0, c.total - c.paid)),
    p.status === 'active' && c.next ? day(c.due) : '', p.status === 'active' && c.next ? r2(c.left) : '', overdue, c.moved || '',
    day(c.maturity), day(c.redeemBy), pays.length, last ? day(last.day) : '', p.remind && p.remind.at ? when(p.remind.at) + ' · ' + nm(p.remind.name) : '',
    r.day ? day(r.day) : '', r.day ? r2(r.bonus) : '', r.day ? r2(r.value) : '', txt(r.billNo || ''), txt(r.item || ''),
    p.enrolDay ? day(p.enrolDay) : when(p.createdAt), txt(nm(p.createdByName)), txt([p.close && p.close.reason ? 'Closed: ' + p.close.reason : '', cu.note].filter(Boolean).join('\n')), appUrl + '#/crm/m/' + id];
}
function paymentRows(id, p, appUrl) {
  return Object.entries(p.payments || {}).map(([k, x]) => {
    const v = (p.void || {})[k];
    return { day: x.day || '', at: x.at || 0, proof: !!x.proofUrl, row: [txt(x.rno), day(x.day), txt(p.acct), txt(p.name), txt(p.phone), txt(p.storeName), n(x.amount), txt(x.mode), txt(x.from),
      txt(x.ref), txt(x.note), txt(nm(x.name)), when(x.at), v ? txt('Cancelled — ' + (v.reason || '') + ' (' + nm(v.name) + ', ' + when(v.at) + ')') : x.old ? 'OK (paid before the app)' : 'OK',
      (p.sent || {})[k] ? when(p.sent[k]) : '', image(x.proofUrl), x.proofUrl || '', appUrl + '#/crm/m/' + id] };
  });
}
function dueRows(id, p, c, t, appUrl) {
  if (p.status !== 'active') return [];
  return c.items.map(it => {
    const st = it.paid ? 'Paid' : it.part > 0 ? 'Part paid ₹' + Math.round(it.part) : it.due < t ? 'Overdue' : it.due === t ? 'Due today' : 'Upcoming';
    return { due: it.due, acct: p.acct || '', row: [day(it.due), txt(p.acct), txt(p.name), txt(p.phone), txt(p.storeName), inst11(it), r2(it.amt), st, it.paid ? day(it.paidDay) : '', appUrl + '#/crm/m/' + id] };
  });
}
/* write a whole tab: the new rows first, then clear whatever is left below (never an empty moment) */
async function writeTab(id, tab, rows) {
  if (rows.length) await api('PUT', API + id + '/values/' + q(tab) + '!A2?valueInputOption=USER_ENTERED', { values: rows });
  await api('POST', API + id + '/values/' + q(tab) + '!A' + (rows.length + 2) + ':AZ:clear', {});
}
async function shineSync(db, appUrl, why) {
  const c = await config(db); if (!c) return;
  try {
    const tabs = await ensureTabs(c.id);
    const t = shine.todayIST();
    const snap = await db.collection('shinePlans').get();
    const plans = snap.docs.map(d => ({ id: d.id, p: d.data() })).sort((a, b) => (a.p.createdAt || 0) - (b.p.createdAt || 0));
    const members = [], pays = [], dues = [];
    for (const { id, p } of plans) {
      const calc = shine.shineCalc(p, t);
      members.push(memberRow(id, p, calc, t, appUrl));
      pays.push(...paymentRows(id, p, appUrl));
      dues.push(...dueRows(id, p, calc, t, appUrl));
    }
    pays.sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : a.at - b.at));
    dues.sort((a, b) => (a.due < b.due ? -1 : a.due > b.due ? 1 : a.acct < b.acct ? -1 : 1));
    await writeTab(c.id, T_SM, members);
    await writeTab(c.id, T_SP, pays.map(x => x.row));
    await writeTab(c.id, T_SD, dues.map(x => x.row));
    /* payment rows with a proof photo are taller, the others normal */
    const sid = tabs.ids.get(T_SP), reqs = [];
    if (pays.length) reqs.push({ updateDimensionProperties: { range: { sheetId: sid, dimension: 'ROWS', startIndex: 1, endIndex: pays.length + 1 }, properties: { pixelSize: 21 }, fields: 'pixelSize' } });
    pays.forEach((x, i) => { if (x.proof) reqs.push({ updateDimensionProperties: { range: { sheetId: sid, dimension: 'ROWS', startIndex: i + 1, endIndex: i + 2 }, properties: { pixelSize: 90 }, fields: 'pixelSize' } }); });
    if (reqs.length) await api('POST', API + c.id + ':batchUpdate', { requests: reqs });
    await mark(db, true, 'Shine Plan copied — ' + plans.length + ' members, ' + pays.length + ' payments' + (why ? ' (' + why + ')' : ''));
  } catch (e) {
    await mark(db, false, 'Shine Plan: ' + e.message);
    throw e;
  }
}

module.exports = { onOrder, rebuild, removeOrder, shineSync, robotEmail, placedRow, dispatchedRow, allRow, HEAD, T_ALL, T_PLACED, T_DISP, T_SM, T_SP, T_SD };
