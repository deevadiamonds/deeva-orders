/**
 * Deeva Orders — notification server (Cloud Functions 2nd gen, asia-south1).
 * Sends a push notification (FCM) to the right people when an order changes:
 *   new order            → admin + sub admin (all "admins" below means both)
 *   query sent           → that store's manager
 *   query answered       → admins
 *   approved             → the chosen factory (only its own logins) + that store
 *   moved to another factory → the new factory
 *   CAD sent for approval→ admins + that store
 *   CAD OK / change      → factory
 *   order changed after approval / date or priority changed → factory
 *   factory note / photo → admins + that store
 *   dispatched           → admins + that store
 *   delivered            → admins
 * Deeva Shine Plan (savings plan; never the factory):
 *   new member           → admins + that store
 *   payment / cancelled payment / redeemed → admins + that store
 *   every morning 9:40 (India) → each store manager: due today, overdue, due in 2 days, ready to redeem; admins: all stores
 *   every change (and every morning) → Google Sheet tabs Shine members / Shine payments / Shine dues
 * Device tokens: pushTokens/{token} = { uid, role, storeId, platform, at }. The person who made the change is never notified.
 * Client name, phone and price are never put into a notification.
 */
const { onDocumentCreated, onDocumentUpdated, onDocumentWritten, onDocumentDeleted } = require('firebase-functions/v2/firestore');
const { onSchedule } = require('firebase-functions/v2/scheduler');
const { setGlobalOptions, logger } = require('firebase-functions/v2');
const admin = require('firebase-admin');

setGlobalOptions({ region: 'asia-south1', maxInstances: 5, memory: '256MiB' });
admin.initializeApp();
const db = admin.firestore();
const sheet = require('./sheet');
const shine = require('./shine');
/* the Google Sheet copy never blocks a notification: its errors are written to config/sheet.status for the Admin */
const toSheet = (id, o, ev) => sheet.onOrder(db, id, o, ev, APP_URL).catch(e => logger.warn('sheet', { id, ev, err: e.message }));

const APP_URL = process.env.APP_URL || 'https://deevadiamonds.github.io/deeva-orders/';
const DEAD_TOKEN = /registration-token-not-registered|invalid-registration-token|invalid-argument/;
const short = (s, n) => { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
const STAGE = { new: 'New', received: 'Received by factory', cad: 'CAD', cad_approval: 'CAD approval', casting: 'Casting', filing: 'Filing',
  setting: 'Setting', polish: 'Polish', qc: 'QC / Hallmark', ready: 'Ready', dispatched: 'Dispatched' };

function itemLine(o) {
  const s = (o && o.spec) || {};
  const t = s.jtype === 'Other' ? (s.jtypeOther || 'Other') : s.jtype;
  return [t, [s.purity, s.metalColor].filter(Boolean).join(' ')].filter(Boolean).join(' · ');
}

/* who: { roles: ['admin'|'factory'], storeOf: order } → token docs, minus the person who made the change */
async function tokensFor(who, exceptUid) {
  const out = new Map();
  for (const r of who.roles || []) {
    const snap = await db.collection('pushTokens').where('role', '==', r).get();
    snap.forEach(d => out.set(d.id, d));
  }
  if (who.storeId) {
    const snap = await db.collection('pushTokens').where('storeId', '==', who.storeId).get();
    snap.forEach(d => { if (d.data().role === 'store') out.set(d.id, d); });
  }
  const docs = [...out.values()].filter(d => d.data().uid !== exceptUid);
  /* ignore tokens of people whose login was closed; a factory login hears only about its own factory's orders */
  const uids = [...new Set(docs.map(d => d.data().uid))];
  const live = new Set();
  await Promise.all(uids.map(async u => {
    const s = await db.doc('users/' + u).get(); if (!s.exists || !s.data().active) return;
    const x = s.data();
    if (x.role === 'factory' && (!who.factoryId || x.factoryId !== who.factoryId)) return;
    live.add(u);
  }));
  return docs.filter(d => live.has(d.data().uid));
}

async function notify(who, exceptUid, title, body, orderId, hash) {
  const docs = await tokensFor(who, exceptUid);
  if (!docs.length) { logger.info('no device tokens', { who, title }); return; }
  const link = APP_URL + (hash || '#/o/' + orderId);
  const res = await admin.messaging().sendEachForMulticast({
    tokens: docs.map(d => d.id),
    notification: { title: short(title, 80), body: short(body, 240) },
    data: { orderId: orderId || '', url: link },
    android: { priority: 'high', notification: { channelId: 'orders', icon: 'ic_stat', color: '#0D3B25', sound: 'default' } },
    webpush: {
      headers: { Urgency: 'high' },
      notification: { icon: APP_URL + 'icons/icon-192.png', badge: APP_URL + 'icons/icon-192.png', lang: 'hi' },
      fcmOptions: { link }
    }
  });
  const dead = [];
  res.responses.forEach((r, i) => { if (!r.success && DEAD_TOKEN.test((r.error && r.error.code) || '')) dead.push(docs[i].ref.delete()); });
  await Promise.all(dead);
  logger.info('sent', { title, ok: res.successCount, failed: res.failureCount, removed: dead.length });
}

exports.orderCreated = onDocumentCreated('orders/{orderId}', async (event) => {
  const o = event.data && event.data.data();
  if (!o) return;
  await notify({ roles: ['admin', 'subadmin'] }, o.createdBy, 'New order · ' + (o.storeName || o.createdByName || ''), o.no + ' — ' + itemLine(o) + ' · awaiting approval', event.params.orderId);
  await toSheet(event.params.orderId, o, 'placed');
});

/* the main Admin deleted an order permanently: remove what belongs to it (private + factory docs, photos / videos /
   voice notes, Google Sheet rows) and give its number back if it was the month's latest (so test orders do not use up numbers) */
exports.orderDeleted = onDocumentDeleted({ document: 'orders/{orderId}', timeoutSeconds: 120 }, async (event) => {
  const id = event.params.orderId, o = (event.data && event.data.data()) || {};
  await Promise.all(['private/info', 'factory/bill'].map(d => db.doc('orders/' + id + '/' + d).delete().catch(() => {})));
  const bucket = admin.storage().bucket();
  await Promise.all(['orders/' + id + '/', 'private/' + id + '/'].map(prefix => bucket.deleteFiles({ prefix }).catch(e => logger.warn('files', { prefix, err: e.message }))));
  await sheet.removeOrder(db, o.no).catch(e => logger.warn('sheet remove', { err: e.message }));
  if (o.ym) {
    await db.runTransaction(async tx => {
      const snap = await tx.get(db.collection('orders').where('ym', '==', o.ym));
      const max = snap.docs.reduce((m, d) => Math.max(m, Number(d.data().seq) || 0), 0);
      const ref = db.doc('counters/' + o.ym), cur = await tx.get(ref);
      if (cur.exists && (cur.data().n || 0) > max) tx.set(ref, { n: max });
    }).catch(e => logger.warn('counter', { err: e.message }));
  }
  logger.info('order deleted', { id, no: o.no });
});

/* Admin saved the sheet link or asked for "Sync all again": rewrite the three tabs from the database */
exports.sheetSetup = onDocumentWritten({ document: 'config/sheet', timeoutSeconds: 300 }, async (event) => {
  const b = event.data && event.data.before.exists ? event.data.before.data() : {};
  const a = event.data && event.data.after.exists ? event.data.after.data() : null;
  if (!a || !a.id || (a.id === b.id && a.syncReq === b.syncReq)) return;
  await sheet.rebuild(db, APP_URL).catch(e => logger.warn('sheet rebuild', { err: e.message }));
});

exports.orderUpdated = onDocumentUpdated('orders/{orderId}', async (event) => {
  const b = event.data && event.data.before.data();
  const a = event.data && event.data.after.data();
  if (!a || !b) return;
  const id = event.params.orderId, by = a.updatedBy, no = a.no, store = a.storeId;
  const newLogs = Object.entries(a.log || {}).filter(([k]) => !(b.log || {})[k]).map(([, v]) => v);
  /* Google Sheet: dispatched → a new row in "Dispatched"; any other status change refreshes the order's row in "All orders" */
  if (b.status !== a.status) await toSheet(id, a, a.status === 'dispatched' ? 'dispatched' : 'status');
  if (a.factoryVisible && b.factoryVisible && a.factoryId && b.factoryId && b.factoryId !== a.factoryId) {
    await toSheet(id, a, 'status');
    return notify({ roles: ['factory'], factoryId: a.factoryId }, by, '📦 New order · ' + no, itemLine(a) + (a.factoryDue ? ' · dispatch by ' + a.factoryDue : ''), id);
  }

  if (b.status !== a.status) {
    if (a.status === 'query') return notify({ storeId: store }, by, '❓ Query · ' + no, short((a.query && a.query.text) || '', 200), id);
    if (b.status === 'query' && a.status === 'review') return notify({ roles: ['admin', 'subadmin'] }, by, '💬 Query answered · ' + no, short((a.query && a.query.reply) || '', 200), id);
    if (a.status === 'factory' && !b.factoryVisible) return notify({ roles: ['factory'], storeId: store, factoryId: a.factoryId }, by, '✅ Approved · ' + no, itemLine(a) + (a.factoryDue ? ' · dispatch by ' + a.factoryDue : ''), id);
    if (a.status === 'dispatched') return notify({ roles: ['admin', 'subadmin'], storeId: store }, by, '🚚 Dispatched · ' + no, itemLine(a) + ' — dispatched by the factory', id);
    if (a.status === 'delivered') return notify({ roles: ['admin', 'subadmin'] }, by, '🎁 Delivered · ' + no, itemLine(a), id);
    if (a.status === 'received') return;
  }
  if (b.stage !== a.stage) {
    if (a.stage === 'cad_approval') return notify({ roles: ['admin', 'subadmin'], storeId: store }, by, 'CAD approval required · ' + no, 'The factory has shared the CAD — please review and approve', id);
    if (b.stage === 'cad_approval' && a.stage === 'casting') return notify({ roles: ['factory'], factoryId: a.factoryId }, by, '👍 CAD approved · ' + no, 'Please begin casting', id);
    if (b.stage === 'cad_approval' && a.stage === 'cad') return notify({ roles: ['factory'], factoryId: a.factoryId }, by, '↩️ CAD changes requested · ' + no, short((a.cad && a.cad.note) || '', 200), id);
  }
  if (a.factoryVisible && b.factoryAck !== false && a.factoryAck === false) {
    const e = newLogs.find(l => l.type === 'edited');
    return notify({ roles: ['factory'], factoryId: a.factoryId }, by, '⚠️ Order changed · ' + no, short((e && e.text) || 'Please review the details', 220), id);
  }
  for (const l of newLogs.filter(x => (x.type === 'note' || x.type === 'media' || x.type === 'stage') && x.role === 'factory')) {
    if (l.type === 'stage' && !/\n/.test(l.text || '')) continue; /* plain stage moves stay quiet */
    await notify({ roles: ['admin', 'subadmin'], storeId: store }, by, 'Factory update · ' + no + ' (' + (STAGE[a.stage] || a.stage) + ')', short(l.text, 200), id);
  }
  for (const l of newLogs.filter(x => (x.type === 'note' || x.type === 'media') && x.role !== 'factory' && a.factoryVisible)) {
    /* the factory never sees who at the store or office wrote it — only the store */
    await notify({ roles: ['factory'], factoryId: a.factoryId }, by, 'Note · ' + no + ' · Deeva Diamonds' + (a.storeName ? ' — ' + a.storeName : ''), short(l.text, 200), id);
  }
});

/* ---------- 💎 Deeva Shine Plan ---------- */
const memberLink = pid => '#/crm/m/' + pid;
/* the Google Sheet copy (tabs Shine members / Shine payments / Shine dues) — never blocks a notification */
const toShineSheet = why => sheet.shineSync(db, APP_URL, why).catch(e => logger.warn('shine sheet', { why, err: e.message }));

exports.shineCreated = onDocumentCreated('shinePlans/{pid}', async (event) => {
  const p = event.data && event.data.data();
  if (!p) return;
  await notify({ roles: ['admin', 'subadmin'], storeId: p.storeId }, p.createdBy, '💎 New Shine Plan member · ' + (p.storeName || ''),
    p.name + ' · ' + shine.inr(p.inst) + ' a month · ' + p.acct + ' · enrolled by ' + String(p.createdByName || '').split(' · ')[0], '', memberLink(event.params.pid));
  await toShineSheet('new member ' + p.acct);
});

exports.shineUpdated = onDocumentUpdated('shinePlans/{pid}', async (event) => {
  const b = event.data && event.data.before.data();
  const a = event.data && event.data.after.data();
  if (!a || !b) return;
  const who = { roles: ['admin', 'subadmin'], storeId: a.storeId }, by = a.updatedBy, link = memberLink(event.params.pid);
  const today = shine.todayIST();
  for (const [k, x] of Object.entries(a.payments || {})) {
    if ((b.payments || {})[k]) continue;
    const c = shine.shineCalc(a, today);
    await notify(who, by, '💰 Shine Plan payment · ' + a.name, shine.inr(x.amount) + ' (' + (x.mode || '') + ') · ' + a.acct + ' · ' + (c.full ? 'full plan paid' : c.n + ' of 10½ paid') + ' · by ' + String(x.name || '').split(' · ')[0], '', link);
  }
  for (const [k, v] of Object.entries(a.void || {})) {
    if ((b.void || {})[k]) continue;
    const x = (a.payments || {})[k] || {};
    await notify(who, by, '✖️ Shine Plan payment cancelled · ' + a.name, shine.inr(x.amount) + ' (' + (x.rno || '') + ') — ' + (v.reason || ''), '', link);
  }
  if (b.status !== 'redeemed' && a.status === 'redeemed' && a.redeem) {
    await notify(who, by, '🎁 Shine Plan redeemed · ' + a.name, a.acct + ' · paid ' + shine.inr(a.redeem.paid) + ' + contribution ' + shine.inr(a.redeem.bonus) + ' = ' + shine.inr(a.redeem.value), '', link);
  }
  await toShineSheet(a.acct);
});

/* every morning: who pays today, who is overdue (to each store manager; admins get all stores) */
exports.shineDaily = onSchedule({ schedule: '40 9 * * *', timeZone: 'Asia/Kolkata', timeoutSeconds: 120 }, async () => {
  const t = shine.todayIST();
  const snap = await db.collection('shinePlans').where('status', '==', 'active').get();
  const by = shine.digest(snap.docs.map(d => d.data()), t);
  const lines = [];
  for (const [sid, s] of Object.entries(by)) {
    const txt = shine.digestText(s);
    if (!txt) continue;
    lines.push((s.store || 'Store') + ': ' + txt);
    await notify({ storeId: sid }, null, '💎 Shine Plan today', txt + ' — tap to send reminders', '', '#/crm');
  }
  if (lines.length) await notify({ roles: ['admin', 'subadmin'] }, null, '💎 Shine Plan today', lines.join('\n'), '', '#/crm');
  logger.info('shine daily', { t, stores: lines.length });
  await toShineSheet('daily');
});

/* the main Admin deleted a member permanently: remove the payment proofs and give the account number back if it was the latest */
exports.shineDeleted = onDocumentDeleted({ document: 'shinePlans/{pid}', timeoutSeconds: 120 }, async (event) => {
  const id = event.params.pid, p = (event.data && event.data.data()) || {};
  await admin.storage().bucket().deleteFiles({ prefix: 'shine/' + id + '/' }).catch(e => logger.warn('files', { id, err: e.message }));
  if (p.ym && /^\d{4}$/.test(p.ym)) {
    await db.runTransaction(async tx => {
      const all = await tx.get(db.collection('shinePlans').where('ym', '==', p.ym));
      const max = all.docs.reduce((m, d) => Math.max(m, Number(d.data().seq) || 0), 0);
      const ref = db.doc('shineCounters/' + p.ym), cur = await tx.get(ref);
      if (cur.exists && (cur.data().n || 0) > max) tx.set(ref, { n: max });
    }).catch(e => logger.warn('counter', { err: e.message }));
  }
  logger.info('shine plan deleted', { id, acct: p.acct });
  await toShineSheet('deleted ' + (p.acct || ''));
});
