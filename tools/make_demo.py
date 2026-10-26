"""Builds a self-contained demo page of Deeva Orders (fake data, no Firebase) for a claude.ai artifact.

Run:  python3 tools/make_demo.py <out.html>
Uses web/index.html + tools/fake-backend.js + seed data below. Nothing here is real client data.
"""
import re, sys, base64, pathlib, json

ROOT = pathlib.Path(__file__).resolve().parent.parent
out = pathlib.Path(sys.argv[1])
src = (ROOT / 'web/index.html').read_text(encoding='utf8')
fake = (ROOT / 'tools/fake-backend.js').read_text(encoding='utf8')

def data_uri(p):
    return 'data:image/png;base64,' + base64.b64encode((ROOT / 'web' / p).read_bytes()).decode()

head = re.search(r'<head>(.*?)</head>', src, re.S).group(1)
body = re.search(r'<body>(.*?)</body>', src, re.S).group(1)
fonts = re.findall(r'<link rel="(?:preconnect|stylesheet)"[^>]*>', head)
style = re.search(r'<style>.*?</style>', head, re.S).group(0)

SEED = r"""
<script>
window.__demoPdfPreview = true;
(function(){
  const F = window.__fake, now = Date.now(), H = 3600e3, D = 24 * H;
  const pad = n => String(n).padStart(2, '0');
  const dayAt = ms => { const d = new Date(ms); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); };
  const day = off => dayAt(now + off * D);
  const ymAt = ms => { const d = new Date(ms); return String(d.getFullYear()).slice(2) + pad(d.getMonth() + 1); };
  const svg = (body, bg) => 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><rect width="400" height="400" fill="${bg}"/>${body}<text x="200" y="378" text-anchor="middle" font-family="sans-serif" font-size="16" fill="#8a6a35">Demo photo</text></svg>`);
  const pendant = svg('<path d="M40 40 Q200 260 360 40" fill="none" stroke="#d1913f" stroke-width="4"/><g transform="translate(200 196)"><circle r="16" fill="#fff" stroke="#e7b150" stroke-width="3"/>' + [0,72,144,216,288].map(a => `<ellipse rx="13" ry="24" transform="rotate(${a}) translate(0 -28)" fill="#fdfbf6" stroke="#e7b150" stroke-width="3"/>`).join('') + '<circle r="7" fill="#e7b150"/></g><circle cx="200" cy="300" r="14" fill="#eef4f7" stroke="#d1913f" stroke-width="3"/><line x1="200" y1="252" x2="200" y2="286" stroke="#d1913f" stroke-width="3"/>', '#f3e3d3');
  const ring = svg('<ellipse cx="200" cy="230" rx="110" ry="96" fill="none" stroke="#c9875f" stroke-width="18"/><ellipse cx="200" cy="230" rx="110" ry="96" fill="none" stroke="#e8b48f" stroke-width="6"/><path d="M160 130 L200 92 L240 130 L200 172 Z" fill="#eef5fb" stroke="#9aa8b4" stroke-width="3"/><path d="M160 130 L240 130 M200 92 L185 130 L200 172 L215 130 Z" fill="none" stroke="#9aa8b4" stroke-width="2"/>', '#f4f1ec');
  const cad = svg('<g fill="none" stroke="#2c5e8c" stroke-width="2"><ellipse cx="200" cy="225" rx="105" ry="92"/><ellipse cx="200" cy="225" rx="88" ry="76"/><path d="M160 128 L200 90 L240 128 L200 170 Z"/><path d="M150 140 L250 140 M200 90 L200 170"/></g><text x="24" y="40" font-family="monospace" font-size="15" fill="#2c5e8c">CAD v1 · 18KT · 2.9 g</text>', '#eef3f8');
  const earr = svg('<g fill="#fff" stroke="#9aa8b4" stroke-width="3"><circle cx="130" cy="150" r="22"/><path d="M130 180 L105 260 L130 300 L155 260 Z"/><circle cx="270" cy="150" r="22"/><path d="M270 180 L245 260 L270 300 L295 260 Z"/></g>', '#eef0f2');
  F.store['stores/s_rpr'] = {name: 'Raipur', city: 'Raipur', address: '1st Floor, Currency Tower, VIP Road, Raipur', phone: '9201661918', active: true, at: now - 300 * D};
  F.store['stores/s_bsp'] = {name: 'Bilaspur (demo)', city: 'Bilaspur', address: 'Link Road, Bilaspur', phone: '', active: true, at: now - 120 * D};
  const people = [
    ['u_mayuresh', 'mayuresh@demo', 'Mayuresh Sisodiya', 'admin', 'mayuresh@demo', '9000000001', ''],
    ['u_darshana', 'darshana-x1@demo', 'Darshana', 'subadmin', 'darshana', '9000000002', ''],
    ['u_nishant', 'nishant-x2@demo', 'Nishant', 'store', 'nishant', '9000000003', 's_rpr'],
    ['u_ravi', 'ravi-x5@demo', 'Ravi (demo)', 'store', 'ravi', '9000000005', 's_bsp'],
    ['u_factory', 'factory-x3@demo', 'Factory (Raju)', 'factory', 'factory', '9000000004', '']
  ];
  people.forEach(([uid, email, name, role, lid, phone, storeId]) => {
    F.account(email, 'demo123', uid);
    F.store['users/' + uid] = {name, role, storeId, loginId: lid, phone, active: true, at: now - 300 * D, by: 'u_mayuresh'};
    if (!lid.includes('@')) F.store['logins/' + lid] = {email, uid};
  });
  F.store['config/admin'] = {uid: 'u_mayuresh', at: now - 300 * D};
  F.store['config/rates'] = {day: day(0), gold: {'9KT': 5500, '14KT': 8544, '18KT': 10950, '22KT': 13400}, making: 2000, gst: 3, at: now, by: 'u_darshana', byName: 'Darshana'};
  const L = (at, by, name, role, type, text) => ({at, by, name, role, type, text});
  let kn = 0; const k = () => 'k' + (++kn);
  const counters = {};
  const nextNo = ms => { const ym = ymAt(ms); counters[ym] = (counters[ym] || 0) + 1; F.store['counters/' + ym] = {n: counters[ym]}; return {ym, seq: counters[ym], no: 'DD-' + ym + '-' + pad(counters[ym]).padStart(3, '0')}; };
  const baseSpec = {jtype: '', jtypeOther: '', qty: '1', metalColor: '', purity: '', size: '', engraving: '', design: '', gem1Type: '', gem1Color: '', gem1Shape: '', gem1Ct: '', gem1Pcs: '', gem2Type: '', gem2Color: '', gem2Shape: '', gem2Ct: '', gem2Pcs: '', stoneNote: ''};
  [1, 2, 3, 4].forEach(i => ['Type', 'Ct', 'Pcs', 'Shape', 'Color', 'Clarity', 'Cut', 'Cert'].forEach(k => { baseSpec['dia' + i + k] = ''; }));
  [1, 2].forEach(i => ['Type', 'Color', 'Shape', 'Ct', 'Size', 'Pcs'].forEach(k => { baseSpec['gem' + i + k] = ''; }));
  const calcOf = (c, spec) => { const n = v => parseFloat(v) || 0; const gross = n(c.grossWt); const dias = [1, 2, 3, 4].filter(i => n(spec['dia' + i + 'Ct']) > 0).map(i => ({n: i, type: spec['dia' + i + 'Type'] || '', ct: n(spec['dia' + i + 'Ct']), rate: n(c['d' + i + 'Rate']), amt: n(spec['dia' + i + 'Ct']) * n(c['d' + i + 'Rate'])})); const gems = [1, 2].filter(i => spec['gem' + i + 'Type'] && n(spec['gem' + i + 'Ct']) > 0).map(i => ({n: i, type: spec['gem' + i + 'Type'], ct: n(spec['gem' + i + 'Ct']), g: n(spec['gem' + i + 'Ct']) * 0.2})); const diaCt = dias.reduce((a, d) => a + d.ct, 0), gemCt = gems.reduce((a, d) => a + d.ct, 0); const stoneCt = diaCt + gemCt, stoneG = stoneCt * 0.2, net = Math.max(0, gross - stoneG); const gold = net * n(c.goldRate), mk = net * n(c.making), diaTotal = dias.reduce((a, d) => a + d.amt, 0); const value = gold + diaTotal + mk + n(c.gemAmt) + n(c.other); const gstAmt = value * n(c.gst) / 100; return Object.assign({}, c, {gross, dias, gems, diaCt, gemCt, stoneCt, stoneG, net, gold, diaTotal, mk, gem: n(c.gemAmt), oth: n(c.other), value, gstPct: n(c.gst), gstAmt, final: value + gstAmt}); };
  const ITEMS = [
    ['Ring', 'Rose Gold', '18KT', 'Ring 12', '0.50', 'Oval', 'E-F', 'VVS1', 3.1],
    ['Pendant with chain', 'Yellow Gold', '14KT', '18 inch', '0.40', 'Round — Portuguese cut', 'F-G', 'VS1', 3.75],
    ['Earrings', 'White Gold', '18KT', 'NA', '0.60', 'Pear', 'E-F', 'VVS2', 4.1],
    ['Bracelet', 'Yellow Gold', '18KT', '6.5 inch', '1.20', 'Round', 'F-G', 'VS1', 9.5],
    ['Mangalsutra', 'Yellow Gold', '22KT', '22 inch', '0.30', 'Marquise', 'G-H', 'VS2', 8.2],
    ['Ring', 'White Gold', '18KT', 'Ring 15', '1.00', 'Cushion', 'E', 'VVS1', 4.4],
    ['Nose pin', 'Rose Gold', '14KT', 'NA', '0.08', 'Round', 'F', 'VVS2', 0.6],
    ['Necklace', 'Yellow Gold', '18KT', '16 inch', '2.10', 'Emerald', 'F-G', 'VS1', 18.5]
  ];
  const CLIENTS = ['Ananya Jain', 'Riya Agrawal', 'Pooja Sharma', 'Kavita Soni', 'Meera Tiwari', 'Sneha Gupta', 'Neha Verma', 'Priya Chandrakar', 'Ritu Sahu', 'Anjali Patel'];
  let rnd = 7; const rr = () => { rnd = (rnd * 9301 + 49297) % 233280; return rnd / 233280; };
  function makeOrder(id, createdAt, st, store, item, client, extra){
    const nn = nextNo(createdAt);
    const spec = Object.assign({}, baseSpec, {jtype: item[0], metalColor: item[1], purity: item[2], size: item[3], dia1Type: 'Solitaire', dia1Ct: item[4], dia1Pcs: '1', dia1Shape: item[5], dia1Color: item[6], dia1Clarity: item[7], dia1Cut: item[5].startsWith('Round') ? 'Excellent' : '', dia1Cert: 'IGI', design: 'Design as per the client’s reference.'}, extra.spec || {});
    const rate = {'14KT': 8544, '18KT': 10950, '22KT': 13400}[item[2]] || 8544;
    const calc = calcOf({grossWt: String(item[8]), goldRate: String(rate), making: '2000', d1Rate: '22000', d2Rate: '15000', d3Rate: '', d4Rate: '', gemAmt: spec.gem1Type ? '1500' : '', other: '', gst: '3'}, spec);
    const est = Math.round(calc.final / 100) * 100;
    const approvedAt = createdAt + (0.4 + rr()) * D;
    const makeDays = 7 + Math.round(rr() * 9);
    const o = Object.assign({no: nn.no, ym: nn.ym, seq: nn.seq, orderDay: dayAt(createdAt), createdAt, createdBy: store === 's_rpr' ? 'u_nishant' : 'u_ravi', createdByName: store === 's_rpr' ? 'Nishant · Raipur' : 'Ravi (demo) · Bilaspur (demo)', storeId: store, storeName: F.store['stores/' + store].name,
      status: st, factoryVisible: st !== 'review' && st !== 'query', stage: '', priority: rr() < 0.2 ? 'urgent' : 'normal', deliveryDay: dayAt(createdAt + (makeDays + 4) * D), factoryDue: dayAt(approvedAt + (makeDays + (rr() < 0.25 ? -2 : 1)) * D),
      cadRequired: true, cad: {ok: true, by: 'Nishant', at: approvedAt + 2 * D}, factoryAck: true, approvedAt, approvedBy: 'Darshana',
      spec, media: {}, edited: {}, query: {open: false}, updatedAt: createdAt, updatedBy: 'u_factory', log: {}}, extra.o || {});
    if (['dispatched', 'received', 'delivered'].includes(st) && !o.dispatch) { const at = approvedAt + makeDays * D; o.dispatch = {at, by: 'u_factory', byName: 'Factory (Raju)', mode: 'Courier', ref: 'DTDC ' + Math.round(1000 + rr() * 8000), grossWt: String(item[8]), note: 'Hallmark done'}; o.stage = 'dispatched'; o.stageAt = {dispatched: at}; o.updatedAt = at; }
    if (o.dispatch && !o.dispatch.actual) {
      const dias = [1, 2, 3, 4].filter(i => parseFloat(spec['dia' + i + 'Ct']) > 0).map(i => ({n: i, type: spec['dia' + i + 'Type'], ct: Math.round(parseFloat(spec['dia' + i + 'Ct']) * (1 + (rr() - 0.4) * 0.1) * 100) / 100, pcs: spec['dia' + i + 'Pcs'] || '1', cert: spec['dia' + i + 'Type'] === 'Solitaire' ? 'yes' : 'no', certNo: spec['dia' + i + 'Type'] === 'Solitaire' ? 'IGI LG' + Math.round(100000 + rr() * 800000) : ''}));
      const gems = [1, 2].filter(i => spec['gem' + i + 'Type']).map(i => ({n: i, type: spec['gem' + i + 'Type'], ct: parseFloat(spec['gem' + i + 'Ct']) || 0, pcs: spec['gem' + i + 'Pcs'] || '1'}));
      const gross = Math.round(item[8] * (1 + (rr() - 0.5) * 0.08) * 1000) / 1000;
      const stoneCt = dias.concat(gems).reduce((a, x) => a + x.ct, 0);
      const net = Math.round((gross - stoneCt * 0.2) * 1000) / 1000;
      o.dispatch.grossWt = String(gross);
      o.dispatch.actual = {grossWt: gross, netWt: net, hallmark: 'yes', huid: 'HU' + Math.round(1000 + rr() * 8000), dias, gems};
      const touch = {'14KT': 59, '18KT': 76, '22KT': 92}[item[2]] || 59;
      const lines = dias.map(x => ({kind: 'd', n: x.n, type: x.type, ct: x.ct, pcs: x.pcs, rate: 18500, amt: Math.round(x.ct * 18500)})).concat(gems.map(x => ({kind: 'g', n: x.n, type: x.type, ct: x.ct, pcs: x.pcs, rate: 0, amt: 900})));
      const labour = Math.round(net * 850 * 100) / 100;
      const total = lines.reduce((a, l) => a + l.amt, 0) + labour + 250;
      F.store['orders/' + id + '/factory/bill'] = {orderNo: nn.no, goldMode: 'fine', purity: item[2], netWt: net, touch, fine: Math.round(net * touch / 100 * 1000) / 1000, goldRate: 0, goldAmt: 0, lines, labourRate: 850, labour, other: 250, total, at: o.dispatch.at, by: 'u_factory', byName: 'Factory (Raju)'};
    }
    if (st === 'delivered') o.delivered = {at: o.dispatch.at + 2 * D, by: 'Nishant'};
    o.log[k()] = L(createdAt, o.createdBy, o.createdByName, 'store', 'created', 'Order created — ' + item[0]);
    F.store['orders/' + id] = o;
    const paid = st === 'delivered' ? est : Math.round(est * (0.3 + rr() * 0.3) / 100) * 100;
    const pays = {pa: {amount: paid, mode: rr() < 0.5 ? 'UPI' : 'Card', day: dayAt(createdAt), note: st === 'delivered' ? 'Full' : 'Advance', by: o.createdBy, name: o.createdByName, at: createdAt}};
    F.store['orders/' + id + '/private/info'] = Object.assign({storeId: store, client: {name: client + ' (demo)', phone: '98000000' + pad(Math.round(rr() * 99)), city: F.store['stores/' + store].city},
      price: {est, goldRateBooked: rr() < 0.5 ? 'yes' : 'no', goldRate: 8544, calc, final: ''}, payments: pays, internalNote: '', media: {}, ack: {accepted: true, remote: false, at: createdAt, signData: '', terms: 7}, log: {}}, extra.p || {});
    return o;
  }
  /* history: about 26 orders over 8 months, both stores */
  for (let i = 0; i < 26; i++) {
    const ago = 240 - i * 8.6 - rr() * 4;
    const store = rr() < 0.72 ? 's_rpr' : 's_bsp';
    if (store === 's_bsp' && ago > 120) continue;
    makeOrder('h' + i, now - ago * D, rr() < 0.06 ? 'cancelled' : 'delivered', store, ITEMS[Math.floor(rr() * ITEMS.length)], CLIENTS[Math.floor(rr() * CLIENTS.length)], {});
  }
  /* live orders */
  makeOrder('o1', now - 4 * D, 'factory', 's_rpr', ITEMS[0], 'Ananya Jain', {
    spec: {engraving: 'R ♥ A', dia2Type: 'Side', dia2Ct: '0.10', dia2Pcs: '12', dia2Shape: 'Round', dia2Color: 'F-G', dia2Clarity: 'VS', design: 'Oval solitaire on a slim 2 mm band.', stoneNote: 'Set the centre stone slightly higher'},
    o: {stage: 'cad_approval', stageAt: {new: now - 3 * D, received: now - 3 * D + 2 * H, cad: now - 2 * D, cad_approval: now - 3 * H}, approvedAt: now - 3 * D, factoryDue: day(9), deliveryDay: day(12), cad: {}, priority: 'normal',
      media: {m1: {kind: 'image', url: ring, path: 'demo', desc: 'Client reference — slimmer band', by: 'u_nishant', byName: 'Nishant', at: now - 4 * D}, m2: {kind: 'image', url: cad, path: 'demo', desc: 'CAD v1', by: 'u_factory', byName: 'Factory (Raju)', at: now - 3 * H, stage: 'cad_approval'}},
      log: {k90: L(now - 3 * D, 'u_darshana', 'Darshana', 'admin', 'approved', 'Approved and sent to the factory · CAD approval required'), k91: L(now - 3 * H, 'u_factory', 'Factory (Raju)', 'factory', 'stage', 'Sent for CAD approval\n📎 1 photo')}}
  });
  makeOrder('o2', now - 2 * H, 'review', 's_rpr', ITEMS[1], 'Riya Agrawal', {
    spec: {gem1Type: 'Ruby', gem1Color: 'Red', gem1Shape: 'Round', gem1Ct: '0.20', gem1Size: '2 mm', gem1Pcs: '4', design: 'Same as the client’s reference image, but without the drop at the bottom.'},
    o: {factoryVisible: false, approvedAt: null, factoryDue: '', cad: {}, deliveryDay: day(15), media: {m3: {kind: 'image', url: pendant, path: 'demo', desc: 'Reference — no drop', by: 'u_nishant', byName: 'Nishant', at: now - 2 * H}}}
  });
  makeOrder('o3', now - 14 * D, 'dispatched', 's_rpr', ITEMS[2], 'Pooja Sharma', {
    o: {priority: 'urgent', deliveryDay: day(1), factoryDue: day(-1), approvedAt: now - 13 * D, dispatch: {at: now - 20 * H, by: 'u_factory', byName: 'Factory (Raju)', mode: 'Courier', ref: 'DTDC 7731', note: 'Screw back'}, stage: 'dispatched', stageAt: {dispatched: now - 20 * H},
      media: {m4: {kind: 'image', url: earr, path: 'demo', desc: 'Finished piece', by: 'u_factory', byName: 'Factory (Raju)', at: now - 20 * H, stage: 'dispatched'}}}
  });
  makeOrder('o4', now - 6 * D, 'factory', 's_bsp', ITEMS[3], 'Kavita Soni', {o: {stage: 'setting', stageAt: {setting: now - D}, approvedAt: now - 5 * D, factoryDue: day(-1), deliveryDay: day(3)}});
  F.preLogin('nishant-x2@demo');
})();
</script>"""

DEMO_BAR = """<div class="demo-bar" id="demo-bar"><div class="demo-in"><span class="demo-tag">DEMO</span><span class="demo-txt">Sample data · view as:</span>
<span class="demo-btns"><button type="button" data-demo="nishant-x2@demo" class="on">Nishant · Store</button><button type="button" data-demo="darshana-x1@demo">Darshana · Sub Admin</button><button type="button" data-demo="factory-x3@demo">Factory</button><button type="button" data-demo="ravi-x5@demo">Ravi · Bilaspur</button><button type="button" data-demo="mayuresh@demo">Mayuresh · Admin</button></span></div></div>"""
DEMO_CSS = """<style>
.demo-bar{background:var(--gold-soft);border-bottom:1px solid var(--gold);padding-block:7px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.demo-in{max-width:680px;margin:0 auto;display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;font-size:13.5px;color:var(--ink)}
.demo-tag{font-family:var(--num);font-weight:700;letter-spacing:1.5px;font-size:11px;background:var(--g8);color:var(--gold);border-radius:6px;padding:2px 7px}
.demo-btns{display:flex;flex-wrap:wrap;gap:6px}
.demo-btns button{border:1px solid var(--line2);background:var(--card);color:var(--ink);border-radius:999px;padding:4px 11px;font:inherit;font-weight:600;cursor:pointer}
.demo-btns button.on{background:var(--g7);border-color:var(--g7);color:var(--cream)}
.demo-btns button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
</style>"""
DEMO_JS = """<script>
document.getElementById('demo-bar').addEventListener('click', e => {
  const b = e.target.closest('[data-demo]'); if (!b) return;
  document.querySelectorAll('[data-demo]').forEach(x => x.classList.toggle('on', x === b));
  location.hash = '#/';
  window.__fake.as(b.dataset.demo);
});
</script>"""

body = re.sub(r'<!--FIREBASE-SDK-->.*?<!--/FIREBASE-SDK-->', lambda m: '<script>' + fake + '</script>' + SEED, body, flags=re.S)
body = body.replace("if ('serviceWorker' in navigator && location.protocol === 'https:') navigator.serviceWorker.register('sw.js').catch(() => {});", '')
for name in ['mark.png', 'wordmark.png', 'icon-192.png']:
    body = body.replace('icons/' + name, data_uri('icons/' + name))
style = style.replace('icons/', '')
page = ('<title>Deeva Orders Demo</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n' + '\n'.join(fonts) + '\n' + style + '\n' + DEMO_CSS +
        '\n' + DEMO_BAR + body + DEMO_JS)
out.write_text(page, encoding='utf8')
print(out, len(page))
