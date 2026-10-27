/* Prints the Google Sheet backup status (config/sheet) for the deploy log. Run by .github/workflows/firebase.yml. */
const fs = require('fs');
const admin = require('firebase-admin');
admin.initializeApp({ credential: admin.credential.cert(JSON.parse(fs.readFileSync(process.env.GOOGLE_APPLICATION_CREDENTIALS, 'utf8'))) });
admin.firestore().doc('config/sheet').get().then(s => {
  const c = s.exists ? s.data() : null;
  if (!c || !c.id) return console.log('Not linked yet (Team › Google Sheet backup)');
  const st = c.status || {};
  console.log((st.ok === false ? 'ERROR: ' : 'OK: ') + (st.msg || 'linked') + (st.at ? ' · ' + new Date(st.at).toISOString() : ''));
}).catch(e => console.log('ERROR: ' + e.message));
