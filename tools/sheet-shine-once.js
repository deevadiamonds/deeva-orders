/* One time after the Shine Plan tabs were added to the Google Sheet copy (24 Nov 2026): ask the server for one
   "Copy everything again", so the linked sheet gets the tabs Shine members / Shine payments / Shine dues at once.
   Then waits up to 3 minutes and prints what the server reported. Run by .github/workflows/firebase.yml after the
   functions are deployed; does nothing when no sheet is linked or when it was already done (config/sheet.shineTabs). */
const fs = require('fs');
const admin = require('firebase-admin');
admin.initializeApp({ credential: admin.credential.cert(JSON.parse(fs.readFileSync(process.env.GOOGLE_APPLICATION_CREDENTIALS, 'utf8'))) });
const db = admin.firestore();
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const ref = db.doc('config/sheet');
  const s = await ref.get();
  const c = s.exists ? s.data() : null;
  if (!c || !c.id) return console.log('No sheet linked yet — nothing to do');
  if (c.shineTabs) return console.log('Shine Plan tabs already added · ' + ((c.status || {}).msg || ''));
  const now = Date.now();
  await ref.set({ syncReq: now, shineTabs: now, status: { ok: true, working: true, msg: 'Adding the Shine Plan tabs…', at: now } }, { merge: true });
  for (let i = 0; i < 36; i++) {
    await sleep(5000);
    const st = ((await ref.get()).data().status) || {};
    if (!st.working && st.at > now && (st.ok === false || /Shine Plan/.test(st.msg || ''))) return console.log((st.ok === false ? 'ERROR: ' : 'OK: ') + st.msg);
  }
  console.log('Still copying (the server continues on its own)');
})().catch(e => console.log('ERROR: ' + e.message));
