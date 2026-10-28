/* Writes the result of the weekly permanent archive to config/archive, so the Admin sees it in the app (Team page).
   Run by .github/workflows/archive.yml: node tools/archive-status.js <ok> <date> <copies> <files> <size> <bucket> */
const fs = require('fs');
const admin = require('firebase-admin');
admin.initializeApp({ credential: admin.credential.cert(JSON.parse(fs.readFileSync(process.env.GOOGLE_APPLICATION_CREDENTIALS, 'utf8'))) });
const [ok, stamp, copies, files, size, bucket] = process.argv.slice(2);
const doc = { at: Date.now(), ok: ok === 'success', bucket: String(bucket || '').replace(/^gs:\/\//, '') };
if (doc.ok) Object.assign(doc, { stamp, copies: Number(copies) || 0, files: Number(files) || 0, size: size || '' });
admin.firestore().doc('config/archive').set(doc, { merge: true })
  .then(() => console.log('archive status saved', JSON.stringify(doc)))
  .catch(e => { console.log('could not save archive status: ' + e.message); process.exitCode = 1; });
