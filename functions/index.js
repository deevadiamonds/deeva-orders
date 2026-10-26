/**
 * Deeva Orders — notification server (Cloud Functions 2nd gen, asia-south1).
 * Sends a push notification (FCM) to the right people when an order changes:
 *   new order            → admins
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
const { onDocumentCreated, onDocumentUpdated } = require('firebase-functions/v2/firestore');
const { setGlobalOptions, logger } = require('firebase-functions/v2');
const admin = require('firebase-admin');

setGlobalOptions({ region: 'asia-south1', maxInstances: 5, memory: '256MiB' });
admin.initializeApp();
const db = admin.firestore();

const APP_URL = process.env.APP_URL || 'https://deevadiamonds.github.io/deeva-orders/';
const DEAD_TOKEN = /registration-token-not-registered|invalid-registration-token|invalid-argument/;
const short = (s, n) => { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
const STAGE = { new: 'नया', received: 'Factory को मिला', cad: 'CAD', cad_approval: 'CAD approval', casting: 'Casting', filing: 'Filing',
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
  await notify({ roles: ['admin'] }, o.createdBy, 'नया Order · ' + (o.storeName || o.createdByName || ''), o.no + ' — ' + itemLine(o) + ' · approval के लिए', event.params.orderId);
});

exports.orderUpdated = onDocumentUpdated('orders/{orderId}', async (event) => {
  const b = event.data && event.data.before.data();
  const a = event.data && event.data.after.data();
  if (!a || !b) return;
  const id = event.params.orderId, by = a.updatedBy, no = a.no, store = a.storeId;
  const newLogs = Object.entries(a.log || {}).filter(([k]) => !(b.log || {})[k]).map(([, v]) => v);
  const who = (l) => (l && l.name) || '';

  if (b.status !== a.status) {
    if (a.status === 'query') return notify({ storeId: store }, by, '❓ Query · ' + no, short((a.query && a.query.text) || '', 200), id);
    if (b.status === 'query' && a.status === 'review') return notify({ roles: ['admin'] }, by, '💬 Query का जवाब · ' + no, short((a.query && a.query.reply) || '', 200), id);
    if (a.status === 'factory' && !b.factoryVisible) return notify({ roles: ['factory'], storeId: store }, by, '✅ Approve · ' + no, itemLine(a) + (a.factoryDue ? ' · dispatch ' + a.factoryDue + ' तक' : ''), id);
    if (a.status === 'dispatched') return notify({ roles: ['admin'], storeId: store }, by, '🚚 Dispatched · ' + no, itemLine(a) + ' — factory से निकल गया', id);
    if (a.status === 'delivered') return notify({ roles: ['admin'] }, by, '🎁 Delivered · ' + no, itemLine(a), id);
    if (a.status === 'received') return;
  }
  if (b.stage !== a.stage) {
    if (a.stage === 'cad_approval') return notify({ roles: ['admin'], storeId: store }, by, 'CAD approval चाहिए · ' + no, 'Factory ने CAD भेजा है — देखकर OK करें', id);
    if (b.stage === 'cad_approval' && a.stage === 'casting') return notify({ roles: ['factory'] }, by, '👍 CAD OK · ' + no, 'Casting शुरू करें', id);
    if (b.stage === 'cad_approval' && a.stage === 'cad') return notify({ roles: ['factory'] }, by, '↩️ CAD में बदलाव · ' + no, short((a.cad && a.cad.note) || '', 200), id);
  }
  if (a.factoryVisible && b.factoryAck !== false && a.factoryAck === false) {
    const e = newLogs.find(l => l.type === 'edited');
    return notify({ roles: ['factory'] }, by, '⚠️ Order में बदलाव · ' + no, short((e && e.text) || 'Details देखें', 220), id);
  }
  for (const l of newLogs.filter(x => (x.type === 'note' || x.type === 'media' || x.type === 'stage') && x.role === 'factory')) {
    if (l.type === 'stage' && !/\n/.test(l.text || '')) continue; /* plain stage moves stay quiet */
    await notify({ roles: ['admin'], storeId: store }, by, 'Factory update · ' + no + ' (' + (STAGE[a.stage] || a.stage) + ')', short(l.text, 200), id);
  }
  for (const l of newLogs.filter(x => (x.type === 'note' || x.type === 'media') && x.role !== 'factory' && a.factoryVisible)) {
    await notify({ roles: ['factory'] }, by, 'Note · ' + no + ' · ' + who(l), short(l.text, 200), id);
  }
});
