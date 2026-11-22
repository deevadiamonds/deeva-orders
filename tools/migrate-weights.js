/* One-time data update (22 Nov 2026): orders placed before the weight was shared with the factory get spec.grossWt /
   spec.netWt from their estimate (orders/{id}/private/info.price.calc). Safe to run again: only fills what is missing.
   Run by .github/workflows/firebase.yml. */
const fs = require('fs');
const admin = require('firebase-admin');
admin.initializeApp({ credential: admin.credential.cert(JSON.parse(fs.readFileSync(process.env.GOOGLE_APPLICATION_CREDENTIALS, 'utf8'))) });
const db = admin.firestore();
(async () => {
  const orders = (await db.collection('orders').get()).docs.filter(d => !(d.data().spec || {}).grossWt);
  let done = 0;
  for (const d of orders) {
    const p = await db.doc('orders/' + d.id + '/private/info').get();
    const c = p.exists && p.data().price && p.data().price.calc;
    const g = c && parseFloat(c.grossWt);
    if (!(g > 0)) continue;
    let net = parseFloat(c.net);
    if (!(net >= 0)) {
      const s = d.data().spec || {}, n = v => parseFloat(v) || 0;
      const ct = [1, 2, 3, 4].reduce((a, i) => a + (String(s['dia' + i + 'Ct']).toUpperCase() === 'NA' ? 0 : n(s['dia' + i + 'Ct'])), 0) + [1, 2].reduce((a, i) => a + (s['gem' + i + 'Type'] ? n(s['gem' + i + 'Ct']) : 0), 0);
      net = Math.max(0, g - ct * 0.2);
    }
    await d.ref.update({ 'spec.grossWt': g.toFixed(3), 'spec.netWt': (Math.round(net * 1000) / 1000).toFixed(3) });
    done++;
  }
  console.log(done + ' order(s) now show their gross / net weight to the factory');
})().catch(e => { console.log('ERROR: ' + e.message); process.exitCode = 1; });
