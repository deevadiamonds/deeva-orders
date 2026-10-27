/**
 * Deeva Orders — notification server (Cloud Functions 2nd gen, asia-south1).
 * Sends a push notification (FCM) to the right people when an order changes:
 *   new order            → admin + sub admin (all "admins" below means both)
 *   query sent           → that store's manager
 *   query answered       → admins
 *   approved             → factory + that store
 *   CAD sent for approval→ admins + that store
 *   CAD OK / change      → factory
 *   order changed after approval / date or priority changed → factory
 *   factory note / photo → admins + that store
 *   dispatched           → admins + that store
 *   delivered            → admins
 * Device tokens: pushTokens/{token} = { uid, role, storeId, platform, at }. The person who made the change is never notified.
 * Client name, phone and price are never put into a notification.
 */
const { onDocumentCreated, onDocumentUpdated, onDocumentWritten, onDocumentDeleted } = require('firebase-functions/v2/firestore');
const { setGlobalOptions, logger } = require('firebase-functions/v2');
const admin = require('firebase-admin');

setGlobalOptions({ region: 'asia-south1', maxInstances: 5, memory: '256MiB' });
admin.initializeApp();
const db = admin.firestore();
const sheet = require('./sheet');
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
  /* ignore tokens of people whose login was closed */
  const uids = [...new Set(docs.map(d => d.data().uid))];
  const live = new Set();
  await Promise.all(uids.map(async u => { const s = await db.doc('users/' + u).get(); if (s.exists && s.data().active) live.add(u); }));
  return docs.filter(d => live.has(d.data().uid));
}

async function notify(who, exceptUid, title, body, orderId) {
  const docs = await tokensFor(who, exceptUid);
  if (!docs.length) { logger.info('no device tokens', { who, title }); return; }
  const link = APP_URL + '#/o/' + orderId;
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

  if (b.status !== a.status) {
    if (a.status === 'query') return notify({ storeId: store }, by, '❓ Query · ' + no, short((a.query && a.query.text) || '', 200), id);
    if (b.status === 'query' && a.status === 'review') return notify({ roles: ['admin', 'subadmin'] }, by, '💬 Query answered · ' + no, short((a.query && a.query.reply) || '', 200), id);
    if (a.status === 'factory' && !b.factoryVisible) return notify({ roles: ['factory'], storeId: store }, by, '✅ Approved · ' + no, itemLine(a) + (a.factoryDue ? ' · dispatch by ' + a.factoryDue : ''), id);
    if (a.status === 'dispatched') return notify({ roles: ['admin', 'subadmin'], storeId: store }, by, '🚚 Dispatched · ' + no, itemLine(a) + ' — dispatched by the factory', id);
    if (a.status === 'delivered') return notify({ roles: ['admin', 'subadmin'] }, by, '🎁 Delivered · ' + no, itemLine(a), id);
    if (a.status === 'received') return;
  }
  if (b.stage !== a.stage) {
    if (a.stage === 'cad_approval') return notify({ roles: ['admin', 'subadmin'], storeId: store }, by, 'CAD approval required · ' + no, 'The factory has shared the CAD — please review and approve', id);
    if (b.stage === 'cad_approval' && a.stage === 'casting') return notify({ roles: ['factory'] }, by, '👍 CAD approved · ' + no, 'Please begin casting', id);
    if (b.stage === 'cad_approval' && a.stage === 'cad') return notify({ roles: ['factory'] }, by, '↩️ CAD changes requested · ' + no, short((a.cad && a.cad.note) || '', 200), id);
  }
  if (a.factoryVisible && b.factoryAck !== false && a.factoryAck === false) {
    const e = newLogs.find(l => l.type === 'edited');
    return notify({ roles: ['factory'] }, by, '⚠️ Order changed · ' + no, short((e && e.text) || 'Please review the details', 220), id);
  }
  for (const l of newLogs.filter(x => (x.type === 'note' || x.type === 'media' || x.type === 'stage') && x.role === 'factory')) {
    if (l.type === 'stage' && !/\n/.test(l.text || '')) continue; /* plain stage moves stay quiet */
    await notify({ roles: ['admin', 'subadmin'], storeId: store }, by, 'Factory update · ' + no + ' (' + (STAGE[a.stage] || a.stage) + ')', short(l.text, 200), id);
  }
  for (const l of newLogs.filter(x => (x.type === 'note' || x.type === 'media') && x.role !== 'factory' && a.factoryVisible)) {
    /* the factory never sees who at the store or office wrote it — only the store */
    await notify({ roles: ['factory'] }, by, 'Note · ' + no + ' · Deeva Diamonds' + (a.storeName ? ' — ' + a.storeName : ''), short(l.text, 200), id);
  }
});
