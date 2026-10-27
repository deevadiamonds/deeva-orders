/* Prints the Google Sheet backup status (config/sheet) for the deploy log. Run by .github/workflows/firebase.yml. */
const fs = require('fs');
const admin = require('firebase-admin');
admin.initializeApp({ credential: admin.credential.cert(JSON.parse(fs.readFileSync(process.env.GOOGLE_APPLICATION_CREDENTIALS, 'utf8'))) });
const db = admin.firestore();
(async () => {
  const s = await db.doc('config/sheet').get();
  const c = s.exists ? s.data() : null;
  const st = (c && c.status) || {};
  const sheet = !c || !c.id ? 'Not linked yet (Team › Google Sheet backup)' : (st.ok === false ? 'ERROR: ' : 'OK: ') + (st.msg || 'linked') + (st.at ? ' · ' + new Date(st.at).toISOString() : '');
  /* orders in the app and the next order number this month, so a clean start can be confirmed */
  const orders = (await db.collection('orders').count().get()).data().count;
  const d = new Date(Date.now() + 5.5 * 3600e3), ym = String(d.getUTCFullYear()).slice(2) + String(d.getUTCMonth() + 1).padStart(2, '0');
  const cn = await db.doc('counters/' + ym).get();
  const next = (cn.exists ? Number(cn.data().n) || 0 : 0) + 1;
  console.log(sheet + ' · orders in the app: ' + orders + ' · next order no.: DD-' + ym + '-' + String(next).padStart(3, '0'));
})().catch(e => console.log('ERROR: ' + e.message));
