/* One-time data update for several factories (29 Oct 2026). Safe to run again: it only touches what is missing.
   Factory logins and approved orders made before factories existed get the first factory ("Factory 1" is created
   if there is none — the Admin renames it under Team › Factories). Run by .github/workflows/firebase.yml. */
const fs = require('fs');
const admin = require('firebase-admin');
admin.initializeApp({ credential: admin.credential.cert(JSON.parse(fs.readFileSync(process.env.GOOGLE_APPLICATION_CREDENTIALS, 'utf8'))) });
const db = admin.firestore();
(async () => {
  const users = (await db.collection('users').where('role', '==', 'factory').get()).docs.filter(d => !d.data().factoryId);
  const orders = (await db.collection('orders').where('factoryVisible', '==', true).get()).docs.filter(d => !d.data().factoryId);
  if (!users.length && !orders.length) return console.log('Nothing to update');
  const facs = (await db.collection('factories').get()).docs.sort((a, b) => (a.data().at || 0) - (b.data().at || 0));
  let fid = facs.length ? facs[0].id : '', made = false;
  if (!fid) { fid = 'f_main'; await db.doc('factories/' + fid).set({ name: 'Factory 1', contact: '', phone: '', city: '', active: true, at: Date.now() }); made = true; }
  for (const d of users) await d.ref.update({ factoryId: fid });
  for (const d of orders) await d.ref.update({ factoryId: fid });
  console.log((made ? 'Created "Factory 1" · ' : '') + users.length + ' factory login(s) and ' + orders.length + ' order(s) linked to it');
})().catch(e => { console.log('ERROR: ' + e.message); process.exitCode = 1; });
