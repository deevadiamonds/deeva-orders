/* Upload self-test, run by .github/workflows/firebase.yml after the rules are deployed.
   Signs in as the Admin (custom token, nothing is changed), uploads a 1-pixel image to orders/_selftest/ exactly as the
   app does, deletes it again and prints PASS / FAIL <status> / SKIP (no Admin yet). */
const fs = require('fs');
const admin = require('firebase-admin');

const cfg = fs.readFileSync('web/config.js', 'utf8');
const pick = k => (new RegExp(k + ':\\s*"([^"]*)"').exec(cfg) || [])[1] || '';
const apiKey = pick('apiKey'), bucket = pick('storageBucket');
/* the key file itself, so the custom token is signed here (no extra IAM permission needed) */
admin.initializeApp({ credential: admin.credential.cert(JSON.parse(fs.readFileSync(process.env.GOOGLE_APPLICATION_CREDENTIALS, 'utf8'))), storageBucket: bucket });

(async () => {
  const a = await admin.firestore().doc('config/admin').get();
  if (!a.exists) { console.log('SKIP'); return; }
  const token = await admin.auth().createCustomToken(a.data().uid);
  const r = await fetch('https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=' + apiKey, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token, returnSecureToken: true })
  });
  const j = await r.json();
  if (!j.idToken) { console.log('FAIL sign-in ' + JSON.stringify(j).slice(0, 300)); process.exitCode = 2; return; }
  const name = 'orders/_selftest/check-' + Date.now() + '.png';
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', 'base64');
  const u = await fetch('https://firebasestorage.googleapis.com/v0/b/' + bucket + '/o?uploadType=media&name=' + encodeURIComponent(name), {
    method: 'POST', headers: { Authorization: 'Firebase ' + j.idToken, 'Content-Type': 'image/png' }, body: png
  });
  const txt = await u.text();
  if (u.ok) {
    await admin.storage().bucket().file(name).delete().catch(() => {});
    console.log('PASS');
  } else {
    console.log('FAIL ' + u.status + ' ' + txt.replace(/\s+/g, ' ').slice(0, 300));
    process.exitCode = 2;
  }
})().catch(e => { console.log('FAIL ' + (e && e.message)); process.exitCode = 3; });
