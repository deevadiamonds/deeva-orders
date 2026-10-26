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
(function(){
  const F = window.__fake, now = Date.now(), H = 3600e3, D = 24 * H;
  const pad = n => String(n).padStart(2, '0');
  const day = off => { const d = new Date(now + off * D); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); };
  const d0 = new Date(); const ym = String(d0.getFullYear()).slice(2) + pad(d0.getMonth() + 1);
  const svg = (body, bg) => 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><rect width="400" height="400" fill="${bg}"/>${body}<text x="200" y="378" text-anchor="middle" font-family="sans-serif" font-size="16" fill="#8a6a35">Demo photo</text></svg>`);
  const pendant = svg('<path d="M40 40 Q200 260 360 40" fill="none" stroke="#d1913f" stroke-width="4"/><g transform="translate(200 196)"><circle r="16" fill="#fff" stroke="#e7b150" stroke-width="3"/>' + [0,72,144,216,288].map(a => `<ellipse rx="13" ry="24" transform="rotate(${a}) translate(0 -28)" fill="#fdfbf6" stroke="#e7b150" stroke-width="3"/>`).join('') + '<circle r="7" fill="#e7b150"/></g><circle cx="200" cy="300" r="14" fill="#eef4f7" stroke="#d1913f" stroke-width="3"/><line x1="200" y1="252" x2="200" y2="286" stroke="#d1913f" stroke-width="3"/>', '#f3e3d3');
  const ring = svg('<ellipse cx="200" cy="230" rx="110" ry="96" fill="none" stroke="#c9875f" stroke-width="18"/><ellipse cx="200" cy="230" rx="110" ry="96" fill="none" stroke="#e8b48f" stroke-width="6"/><path d="M160 130 L200 92 L240 130 L200 172 Z" fill="#eef5fb" stroke="#9aa8b4" stroke-width="3"/><path d="M160 130 L240 130 M200 92 L185 130 L200 172 L215 130 Z" fill="none" stroke="#9aa8b4" stroke-width="2"/>', '#f4f1ec');
  const cad = svg('<g fill="none" stroke="#2c5e8c" stroke-width="2"><ellipse cx="200" cy="225" rx="105" ry="92"/><ellipse cx="200" cy="225" rx="88" ry="76"/><path d="M160 128 L200 90 L240 128 L200 170 Z"/><path d="M150 140 L250 140 M200 90 L200 170"/></g><text x="24" y="40" font-family="monospace" font-size="15" fill="#2c5e8c">CAD v1 · 18KT · 2.9 g</text>', '#eef3f8');
  const earr = svg('<g fill="#fff" stroke="#9aa8b4" stroke-width="3"><circle cx="130" cy="150" r="22"/><path d="M130 180 L105 260 L130 300 L155 260 Z"/><circle cx="270" cy="150" r="22"/><path d="M270 180 L245 260 L270 300 L295 260 Z"/></g>', '#eef0f2');
  const people = [
    ['u_mayuresh', 'mayuresh@demo', 'Mayuresh Sisodiya', 'admin', 'mayuresh@demo', '9000000001'],
    ['u_darshana', 'darshana-x1@demo', 'Darshana', 'admin', 'darshana', '9000000002'],
    ['u_nishant', 'nishant-x2@demo', 'Nishant', 'store', 'nishant', '9000000003'],
    ['u_factory', 'factory-x3@demo', 'Factory (Raju)', 'factory', 'factory', '9000000004']
  ];
  people.forEach(([uid, email, name, role, lid, phone]) => {
    F.account(email, 'demo123', uid);
    F.store['users/' + uid] = {name, role, loginId: lid, phone, active: true, at: now - 30 * D, by: 'u_mayuresh'};
    if (!lid.includes('@')) F.store['logins/' + lid] = {email, uid};
  });
  F.store['config/admin'] = {uid: 'u_mayuresh', at: now - 30 * D};
  F.store['counters/' + ym] = {n: 3};
  const L = (at, by, name, role, type, text) => ({at, by, name, role, type, text});
  const k = (i) => 'k' + (now - i) ;
  /* 1: in factory, waiting for CAD approval */
  F.store['orders/o1'] = {
    no: 'DD-' + ym + '-001', ym, seq: 1, orderDay: day(-4), createdAt: now - 4 * D, createdBy: 'u_nishant', createdByName: 'Nishant',
    status: 'factory', factoryVisible: true, stage: 'cad_approval', stageAt: {new: now - 3 * D, received: now - 3 * D + 2 * H, cad: now - 2 * D, cad_approval: now - 3 * H},
    priority: 'normal', deliveryDay: day(12), factoryDue: day(9), cadRequired: true, factoryNote: 'Center stone thoda uncha set karna', factoryAck: true,
    approvedAt: now - 3 * D, approvedBy: 'Darshana',
    spec: {jtype: 'Ring', jtypeOther: '', qty: '1', metalColor: 'Rose Gold', purity: '18KT', size: 'Ring size 12', dia1Ct: '0.50', dia1Shape: 'Oval', dia2Ct: '0.10', dia2Shape: 'Round', gem1: '', gem2: '', engraving: 'R ♥ A', design: 'Solitaire oval, side me chhote round diamonds. Band patla (2 mm).'},
    media: {m1: {kind: 'image', url: ring, path: 'demo', desc: 'Client ka reference', by: 'u_nishant', byName: 'Nishant', at: now - 4 * D}, m2: {kind: 'image', url: cad, path: 'demo', desc: 'CAD v1', by: 'u_factory', byName: 'Factory (Raju)', at: now - 3 * H, stage: 'cad_approval'}},
    edited: {}, query: {open: false}, updatedAt: now - 3 * H, updatedBy: 'u_factory',
    log: {[k(1)]: L(now - 4 * D, 'u_nishant', 'Nishant', 'store', 'created', 'Order बना — Ring · 18KT Rose Gold · Dia 0.50ct Oval'),
          [k(2)]: L(now - 3 * D, 'u_darshana', 'Darshana', 'admin', 'approved', 'Approve करके factory को भेजा. Factory due: ' + day(9) + ' · CAD approval ज़रूरी'),
          [k(3)]: L(now - 3 * D + 2 * H, 'u_factory', 'Factory (Raju)', 'factory', 'stage', 'Factory को order मिला — काम शुरू'),
          [k(4)]: L(now - 2 * D, 'u_factory', 'Factory (Raju)', 'factory', 'stage', 'Stage: CAD'),
          [k(5)]: L(now - 3 * H, 'u_factory', 'Factory (Raju)', 'factory', 'stage', 'CAD approval के लिए भेजा\n📎 1 photo/video')}
  };
  F.store['orders/o1/private/info'] = {
    client: {name: 'Ananya Jain (demo)', phone: '9800000011', city: 'Raipur'},
    price: {est: 78500, goldRateBooked: 'yes', goldRate: 10950, final: '', calc: null},
    payments: {p1: {amount: 40000, mode: 'Card', day: day(-4), note: 'Advance', by: 'u_nishant', name: 'Nishant', at: now - 4 * D}},
    internalNote: 'Anniversary gift — 12 tareekh se pehle chahiye', media: {},
    ack: {accepted: true, remote: false, at: now - 4 * D, signUrl: '', terms: 7},
    log: {[k(6)]: L(now - 4 * D, 'u_nishant', 'Nishant', 'store', 'payment', 'Advance ₹40,000 (Card)')}
  };
  /* 2: new, waiting for approval */
  F.store['orders/o2'] = {
    no: 'DD-' + ym + '-002', ym, seq: 2, orderDay: day(0), createdAt: now - 2 * H, createdBy: 'u_nishant', createdByName: 'Nishant',
    status: 'review', factoryVisible: false, stage: '', priority: 'normal', deliveryDay: day(15),
    spec: {jtype: 'Pendant with chain', jtypeOther: '', qty: '1', metalColor: 'Yellow Gold', purity: '14KT', size: '18 inch', dia1Ct: '0.40', dia1Shape: 'Mix', dia2Ct: 'NA', dia2Shape: '', gem1: 'NA', gem2: 'NA', engraving: '', design: 'Design customer ki ref image jaisa hi, par neeche ka drop nahi lagana.'},
    media: {m3: {kind: 'image', url: pendant, path: 'demo', desc: 'Reference — drop nahi chahiye', by: 'u_nishant', byName: 'Nishant', at: now - 2 * H}},
    edited: {}, query: {open: false}, updatedAt: now - 2 * H, updatedBy: 'u_nishant',
    log: {[k(7)]: L(now - 2 * H, 'u_nishant', 'Nishant', 'store', 'created', 'Order बना — Pendant with chain · 14KT Yellow Gold · Dia 0.40ct Mix · 18 inch\n📎 1 photo/video/voice')}
  };
  F.store['orders/o2/private/info'] = {
    client: {name: 'Riya Agrawal (demo)', phone: '9800000022', city: 'Raipur'},
    price: {est: 49790, goldRateBooked: 'no', goldRate: '', final: '',
      calc: {goldWt: '3.75', goldRate: '8544', diaRate: '22000', dia2Rate: '', gemAmt: '', making: '2000', other: '', gst: '3', wt: 3.75, d1: 0.4, d2: 0, gold: 32040, dia: 8800, dia2: 0, mk: 7500, gem: 0, oth: 0, value: 48340, gstPct: 3, gstAmt: 1450.2, final: 49790.2}},
    payments: {p2: {amount: 13000, mode: 'UPI', day: day(0), note: 'Advance', by: 'u_nishant', name: 'Nishant', at: now - 2 * H}},
    internalNote: '', media: {}, ack: {accepted: true, remote: false, at: now - 2 * H, signUrl: '', terms: 7},
    log: {[k(8)]: L(now - 2 * H, 'u_nishant', 'Nishant', 'store', 'payment', 'Advance ₹13,000 (UPI)')}
  };
  /* 3: dispatched from factory */
  const st3 = {}; ['new','received','cad','cad_approval','casting','filing','setting','polish','qc','ready'].forEach((s, i) => { st3[s] = now - (10 - i) * D + i * H; }); st3.dispatched = now - 20 * H;
  F.store['orders/o3'] = {
    no: 'DD-' + ym + '-003', ym, seq: 3, orderDay: day(-14), createdAt: now - 14 * D, createdBy: 'u_nishant', createdByName: 'Nishant',
    status: 'dispatched', factoryVisible: true, stage: 'dispatched', stageAt: st3, priority: 'urgent', deliveryDay: day(1), factoryDue: day(-1),
    cadRequired: false, factoryAck: true, approvedAt: now - 13 * D, approvedBy: 'Mayuresh Sisodiya',
    dispatch: {at: now - 20 * H, by: 'u_factory', byName: 'Factory (Raju)', mode: 'Courier', ref: 'DTDC 7731', note: 'Gold 4.1 g, hallmark done'},
    spec: {jtype: 'Earrings', jtypeOther: '', qty: '1 pair', metalColor: 'White Gold', purity: '18KT', size: 'NA', dia1Ct: '0.60', dia1Shape: 'Pear', dia2Ct: 'NA', dia2Shape: '', gem1: '', gem2: '', engraving: '', design: 'Pear drop earrings, screw back.'},
    media: {m4: {kind: 'image', url: earr, path: 'demo', desc: 'Bana hua piece', by: 'u_factory', byName: 'Factory (Raju)', at: now - 20 * H, stage: 'dispatched'}},
    edited: {}, query: {open: false}, updatedAt: now - 20 * H, updatedBy: 'u_factory',
    log: {[k(9)]: L(now - 20 * H, 'u_factory', 'Factory (Raju)', 'factory', 'dispatched', 'Dispatched — Courier · DTDC 7731 · Gold 4.1 g, hallmark done')}
  };
  F.store['orders/o3/private/info'] = {
    client: {name: 'Pooja Sharma (demo)', phone: '9800000033', city: 'Bilaspur'},
    price: {est: 64200, goldRateBooked: 'no', goldRate: '', final: '', calc: null},
    payments: {p3: {amount: 20000, mode: 'Cash', day: day(-14), note: 'Advance', by: 'u_nishant', name: 'Nishant', at: now - 14 * D}},
    internalNote: '', media: {}, ack: {accepted: true, remote: true, at: now - 14 * D, signUrl: '', terms: 7}, log: {}
  };
  F.preLogin('nishant-x2@demo');
})();
</script>"""

DEMO_BAR = """<div class="demo-bar" id="demo-bar"><div class="demo-in"><span class="demo-tag">DEMO</span><span class="demo-txt">नकली data · इस रूप में देखें:</span>
<span class="demo-btns"><button type="button" data-demo="nishant-x2@demo" class="on">Nishant · Store</button><button type="button" data-demo="darshana-x1@demo">Darshana · Admin</button><button type="button" data-demo="factory-x3@demo">Factory</button></span></div></div>"""
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
