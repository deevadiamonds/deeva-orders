"""End-to-end test of Deeva Orders against an in-memory fake Firebase (tools/fake-backend.js).

Run:  python3 tools/test_flow.py [screenshot_dir]
Needs: Python Playwright with Chromium. Does not touch the real Firebase project.
Covers: first admin setup (default store), stores + one manager per store, store isolation, store creates an
order (mandatory fields, diamond 4Cs, side stones, gemstone, photo + voice note on the photo, video, estimate
breakdown, deal amount, booked gold rate, advance + receipt photo, signature), admin query -> store reply + edit,
approve, factory view without client/price, CAD approval, date/priority change alert to factory, dispatch with
final weight, final bill, payment with receipt, delivered, receipt PDF content, admin dashboard.
"""
import asyncio, re, sys, tempfile, pathlib, base64
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.mkdtemp(prefix='do-test-'))
SHOTS = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
LIBS = ['https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js', 'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js']


def build_harness():
    src = (ROOT / 'web/index.html').read_text(encoding='utf8')
    fake = (ROOT / 'tools/fake-backend.js').read_text(encoding='utf8')
    src = re.sub(r'<!--FIREBASE-SDK-->.*?<!--/FIREBASE-SDK-->', lambda m: '<script>' + fake + '</script>', src, flags=re.S)
    src = src.replace('<link rel="stylesheet" href="https://fonts.googleapis.com', '<link rel="x" href="https://fonts.googleapis.com')
    out = ROOT / 'web' / '_harness.html'   # inside web/ so icons/ resolve
    out.write_text(src, encoding='utf8')
    (TMP / 'ref.png').write_bytes(PNG)
    (TMP / 'clip.mp4').write_bytes(b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 2000)
    return out


async def main():
    harness = build_harness()
    async with async_playwright() as p:
        b = await p.chromium.launch(args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--autoplay-policy=no-user-gesture-required'])
        ctx = await b.new_context(viewport={'width': 400, 'height': 860}, permissions=['microphone'])
        pg = await ctx.new_page()
        errs = []
        pg.on('pageerror', lambda e: errs.append('PAGEERR ' + str(e)))
        pg.on('console', lambda m: errs.append('CONSOLE ' + m.text) if m.type == 'error' else None)
        await pg.goto('file://' + str(harness))

        async def shot(name):
            if SHOTS:
                SHOTS.mkdir(parents=True, exist_ok=True)
                await pg.screenshot(path=str(SHOTS / (name + '.png')), full_page=True)

        async def close_sheet():
            await pg.click('#sheet [data-act="sheet-close"]')
            await pg.wait_for_function("!document.querySelector('#sheet .sheet')")

        async def login(lid, pw):
            await pg.wait_for_selector('#login-form', timeout=5000)
            await pg.fill('#l-id', lid); await pg.fill('#l-pw', pw); await pg.click('#l-submit')
            await pg.wait_for_selector('#tabs:not([hidden])', timeout=5000)
            await pg.wait_for_timeout(300)

        async def logout():
            await pg.evaluate("location.hash='#/account'")
            await pg.wait_for_selector('[data-act="logout"]')
            await pg.click('[data-act="logout"]')
            await pg.wait_for_selector('#login-form', timeout=5000)

        async def text():
            return await pg.inner_text('body')

        async def chip(path, val):
            await pg.click(f'[data-act="chip"][data-f="{path}"][data-v="{val}"]')

        async def order_doc():
            return await pg.evaluate("Object.entries(__fake.store).find(([k, d]) => k.startsWith('orders/') && k.split('/').length === 2)[1]")

        async def priv_doc():
            return await pg.evaluate("Object.entries(__fake.store).find(([k]) => k.endsWith('/private/info'))[1]")

        # ---- 1. first setup = admin + default store
        await pg.wait_for_selector('#setup-form', timeout=5000)
        await pg.fill('#s-name', 'Mayuresh Sisodiya'); await pg.fill('#s-email', 'owner@gmail.com')
        await pg.fill('#s-pw', 'owner123'); await pg.fill('#s-pw2', 'owner123'); await pg.click('#s-submit')
        await pg.wait_for_selector('#tabs:not([hidden])', timeout=5000)
        t = await pg.inner_text('#tabs'); assert 'Team' in t and 'Dashboard' in t, t
        print('ok  admin setup')

        # ---- 2. stores + logins
        await pg.evaluate("location.hash='#/team'")
        await pg.wait_for_selector('#u-name')
        await pg.wait_for_function("document.body.innerText.includes('Deeva Diamonds — VIP Road')")
        await pg.click('[data-act="store-new"]')
        await pg.fill('#st-name', 'Deeva Diamonds — Bilaspur'); await pg.fill('#st-city', 'Bilaspur'); await pg.fill('#st-addr', 'Link Road, Bilaspur')
        await pg.click('[data-act="store-save"]')
        await pg.wait_for_function("document.body.innerText.includes('Deeva Diamonds — Bilaspur')")
        sids = await pg.evaluate("Object.keys(__fake.store).filter(k => k.startsWith('stores/')).map(k => [k.split('/')[1], __fake.store[k].name])")
        raipur = [s for s in sids if 'VIP' in s[1]][0][0]; bilaspur = [s for s in sids if 'Bilaspur' in s[1]][0][0]

        async def add(name, role, lid, pw, phone, store=None, expect_ok=True):
            await pg.fill('#u-name', name)
            await pg.click(f'#u-role [data-v="{role}"]')
            if store: await pg.click(f'#u-store [data-v="{store}"]')
            await pg.fill('#u-lid', lid); await pg.fill('#u-pw', pw); await pg.fill('#u-phone', phone)
            await pg.click('#u-add')
            if not expect_ok:
                await pg.wait_for_selector('#u-err:not([hidden])'); return await pg.inner_text('#u-err')
            await pg.wait_for_selector('#sheet .cred', timeout=5000)
            await close_sheet()
        await add('Darshana', 'admin', 'darshana', 'darshana1', '9000000001')
        await add('Nishant', 'store', 'nishant', 'nishant1', '9000000002', raipur)
        msg = await add('Duplicate', 'store', 'dup', 'dup12345', '9000000009', raipur, expect_ok=False)
        assert 'पहले से Nishant' in msg, msg
        await pg.fill('#u-name', ''); await pg.fill('#u-lid', ''); await pg.fill('#u-pw', '')
        await add('Ravi', 'store', 'ravi', 'ravi1234', '9000000005', bilaspur)
        await add('Factory Raju', 'factory', 'factory', 'factory1', '9000000003')
        await pg.click('[data-act="brand-sign"]')
        box = await pg.query_selector('#bsig'); bb = await box.bounding_box()
        await pg.mouse.move(bb['x'] + 30, bb['y'] + 90); await pg.mouse.down()
        for i in range(8): await pg.mouse.move(bb['x'] + 40 + i * 25, bb['y'] + 60 + (i % 2) * 40)
        await pg.mouse.up()
        await pg.click('[data-act="brand-save"]')
        await pg.wait_for_function("!document.querySelector('#sheet .sheet')")
        await shot('01-team')
        print('ok  2 stores, one manager per store enforced, logins, Deeva signature')
        await logout()

        # ---- 3. store creates an order
        await login('nishant', 'nishant1')
        await pg.evaluate("location.hash='#/new'")
        await pg.wait_for_selector('#f-client-name')
        await pg.click('[data-act="f-review"]')
        await pg.wait_for_selector('#sheet .miss-list li')
        n_miss = await pg.eval_on_selector_all('#sheet .miss-list li', 'l => l.length')
        assert n_miss >= 15, n_miss
        await close_sheet()
        print(f'ok  empty form blocked ({n_miss} required fields listed)')

        await pg.fill('#f-client-name', 'Nitu Pansari'); await pg.fill('#f-client-phone', '9777365551'); await pg.fill('#f-client-city', 'Raipur')
        await chip('spec.jtype', 'Pendant with chain'); await chip('spec.metalColor', 'Yellow Gold'); await chip('spec.purity', '14KT')
        await pg.fill('#f-spec-size', '16 inch')
        await pg.fill('#f-spec-dia1Ct', '0.40')
        await pg.wait_for_selector('#dia1-detail:not([hidden])')
        await chip('spec.dia1Shape', 'Round — Portuguese cut'); await chip('spec.dia1Color', 'E-F'); await chip('spec.dia1Clarity', 'VVS1')
        await chip('spec.dia1Cut', 'Excellent'); await chip('spec.dia1Cert', 'IGI')
        await pg.fill('#f-spec-dia2Ct', '0.10'); await pg.fill('#f-spec-dia2Pcs', '10')
        await chip('spec.dia2Shape', 'Round'); await chip('spec.dia2Color', 'F-G'); await chip('spec.dia2Clarity', 'VS')
        await chip('spec.gem1Type', 'Ruby')
        await pg.wait_for_selector('#gem1-detail:not([hidden])')
        await chip('spec.gem1Color', 'Red'); await chip('spec.gem1Shape', 'Round'); await pg.fill('#f-spec-gem1Ct', '2 mm'); await pg.fill('#f-spec-gem1Pcs', '4')
        await pg.fill('#f-spec-stoneNote', 'Center stone thoda uncha')
        await pg.fill('#f-spec-design', 'Design ref image jaisa hi, par drop nahi lagana')
        await pg.set_input_files('#f-media input[data-pick="image"]', str(TMP / 'ref.png'))
        await pg.wait_for_function("document.querySelector('#f-media').innerText.includes('✓ Upload')")
        await pg.fill('#f-media .mitem input[data-desc]', 'Client ka reference — drop nahi')
        await pg.click('#f-media [data-act="rec-item"]')
        await pg.wait_for_timeout(1600)
        await pg.click('#f-media [data-act="rec-item"]')
        await pg.wait_for_selector('#f-media .mvoice audio', timeout=8000)
        await pg.set_input_files('#f-media input[data-pick="video"]', str(TMP / 'clip.mp4'))
        try:
            await pg.wait_for_function("document.querySelectorAll('#f-media .mitem').length === 2 && document.querySelector('#f-media').innerText.split('✓ Upload').length === 3", timeout=8000)
        except Exception:
            print(await pg.inner_text('#f-media')); print(errs); raise
        print('ok  photo with its own voice note + video, together')
        await chip('price.goldRateBooked', 'yes')
        lbl = await pg.inner_text('#w-f-price-calc-goldRate label'); assert 'Booked' in lbl, lbl
        for k, v in [('goldRate', '8544'), ('goldWt', '3.75'), ('diaRate', '22000'), ('dia2Rate', '15000'), ('making', '2000'), ('gemAmt', '1500')]:
            await pg.fill(f'#f-price-calc-{k}', v)
        calc_txt = await pg.inner_text('#calc-out')
        # 32040 + 8800 + 1500 + 1500 + 7500 = 51340; GST 1540.2; total 52880.2
        for x in ['₹32,040', '₹8,800', '₹1,500', '₹7,500', '₹51,340', '₹52,880.2', 'Making charges']:
            assert x in calc_txt, (x, calc_txt)
        await pg.click('[data-act="calc-apply"]')
        assert await pg.input_value('#f-price-est') == '52880'
        await pg.fill('#f-price-est', '52000')
        print('ok  estimate: gold + main dia + side dia + gemstone + making + GST = 52,880; deal 52,000')
        await pg.fill('#f-advance-amount', '26000'); await chip('advance.mode', 'UPI')
        await pg.set_input_files('#f-imedia input[data-pick="image"]', str(TMP / 'ref.png'))
        await pg.wait_for_function("document.querySelector('#f-imedia').innerText.includes('✓ Upload')")
        await pg.click('[data-act="f-days"][data-n="15"]')
        await pg.check('#f-ack')
        box = await pg.query_selector('#sig'); bb = await box.bounding_box()
        await pg.mouse.move(bb['x'] + 30, bb['y'] + 100); await pg.mouse.down()
        for i in range(10): await pg.mouse.move(bb['x'] + 40 + i * 20, bb['y'] + 60 + (i % 3) * 25)
        await pg.mouse.up()
        await shot('02-new-order-form')
        await pg.click('[data-act="f-review"]')
        await pg.wait_for_selector('#sheet [data-act="f-submit"]:not([disabled])', timeout=3000)
        rv = await pg.inner_text('#sheet')
        assert 'Round — Portuguese cut' in rv and 'VVS1' in rv and 'Ruby' in rv and '₹52,000' in rv, rv
        await shot('03-review')
        await pg.click('#sheet [data-act="f-submit"]')
        await pg.wait_for_selector('.dhead .no', timeout=5000)
        no = (await pg.inner_text('.dhead .no')).strip()
        assert re.match(r'^DD-\d{4}-001$', no), no
        await pg.wait_for_selector('#sheet .sheet', timeout=3000)
        await close_sheet()
        st = await order_doc()
        assert st['status'] == 'review' and st['storeId'] == raipur and st['spec']['dia1Clarity'] == 'VVS1' and st['spec']['gem1Type'] == 'Ruby', st
        assert 'client' not in st and 'price' not in st
        assert len(st['media']) == 2 and any(m.get('voiceUrl') for m in st['media'].values()), st['media']
        pv = await priv_doc()
        assert pv['storeId'] == raipur and pv['client']['name'] == 'Nitu Pansari' and pv['price']['est'] == 52000 and pv['price']['goldRate'] == 8544
        assert pv['price']['calc']['final'] > 52880 and pv['ack']['signData'].startswith('data:image/png')
        assert any(m.get('receipt') for m in pv['media'].values()), pv['media']
        print(f'ok  order {no} submitted (4Cs, gemstone, deal amount, booked rate, receipt, signature)')
        await shot('04-order-store')
        await logout()

        # ---- 4. other store's manager sees nothing
        await login('ravi', 'ravi1234')
        await pg.wait_for_function("document.body.innerText.includes('अभी कोई चालू order नहीं')")
        print('ok  Bilaspur manager does not see Raipur orders')
        await logout()

        # ---- 5. Darshana query, Nishant edit + reply, approve
        await login('darshana', 'darshana1')
        await pg.click('.ocard')
        await pg.click('.alertbox [data-act="query-open"]')
        await pg.fill('#qr-text', 'Clarity VVS1 ya VVS2?')
        await pg.click('[data-act="query-do"]')
        await pg.wait_for_selector('#sheet a.wa', timeout=3000)
        await close_sheet()
        await logout()
        await login('nishant', 'nishant1')
        await pg.click('.ocard')
        await pg.click('.alertbox a[href^="#/edit/"]')
        await pg.wait_for_selector('#f-spec-size')
        await chip('spec.dia1Clarity', 'VVS2')
        await pg.click('[data-act="f-review"]')
        await pg.wait_for_selector('.dhead .no')
        await pg.click('.alertbox [data-act="reply-open"]')
        await pg.fill('#rp-text', 'VVS2 final')
        await pg.click('[data-act="reply-do"]')
        await pg.wait_for_function("document.querySelector('.dhead').innerText.includes('Approval बाकी')")
        t = await text(); assert 'Main diamond clarity: VVS1 → VVS2' in t, t
        assert 'Estimate का हिसाब बदला' not in t
        await logout()
        await login('darshana', 'darshana1')
        await pg.click('.ocard')
        await pg.click('.alertbox [data-act="approve-open"]')
        await pg.fill('#ap-note', 'Light weight chain')
        await pg.click('[data-act="approve-do"]')
        await pg.wait_for_selector('#sheet a.wa', timeout=3000)
        await close_sheet()
        print('ok  query -> edit (diff logged) -> reply -> approve')
        await logout()

        # ---- 6. factory
        await login('factory', 'factory1')
        await pg.click('.ocard')
        await pg.wait_for_selector('.alertbox.ok [data-act="stage-quick"]')
        t = await text()
        for secret in ['Nitu', '9777365551', '52,000', '26,000', 'Clarity VVS1 ya', 'receipt']:
            assert secret not in t, 'factory can see ' + secret
        for need in ['VVS2', 'Round — Portuguese cut', 'Ruby', 'Center stone thoda uncha', 'Client ka reference', 'Light weight chain', '🏬']:
            assert need in t, need
        assert await pg.eval_on_selector_all('.gal audio', 'l => l.length') >= 1
        await shot('05-order-factory-new')
        print('ok  factory sees 4Cs, gemstone, photo + its voice note; no client / price / receipt')
        await pg.click('.alertbox.ok [data-act="stage-quick"]')
        await pg.wait_for_function("document.querySelector('#stickbar').innerText.includes('आगे')")
        await pg.click('#stickbar [data-act="stage-quick"]')
        await pg.wait_for_timeout(200)
        await pg.click('#stickbar [data-act="stage-open"]')
        await pg.click('#st-chips [data-k="cad_approval"]')
        await pg.set_input_files('#st-media input[data-pick="image"]', str(TMP / 'ref.png'))
        await pg.wait_for_function("document.querySelector('#st-media').innerText.includes('✓ Upload')")
        await pg.click('[data-act="stage-do"]')
        await pg.wait_for_function("document.body.innerText.includes('CAD approval का इंतज़ार')")
        await logout()

        # ---- 7. store: CAD OK, then priority + date change
        await login('nishant', 'nishant1')
        await pg.click('.ocard')
        await pg.click('[data-act="cad-ok"]'); await pg.click('#sheet [data-act="confirm-ok"]')
        await pg.wait_for_function("!document.querySelector('[data-act=\"cad-ok\"]')")
        await pg.click('[data-act="sched-open"]')
        await pg.click('#sc-pri [data-v="urgent"]')
        await pg.fill('#sc-day', await pg.evaluate("(() => { const d = new Date(Date.now() + 10*864e5); return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0'); })()"))
        await pg.fill('#sc-why', 'Client ko jaldi chahiye')
        await pg.click('[data-act="sched-do"]')
        await pg.wait_for_function("document.querySelector('.dhead').innerText.includes('Urgent')")
        st = await order_doc(); assert st['priority'] == 'urgent' and st['factoryAck'] is False, st
        print('ok  CAD OK; priority + date changed after order -> factory alerted')
        await logout()

        # ---- 8. factory: sees change, ready, dispatch with final weight
        await login('factory', 'factory1')
        await pg.click('.ocard')
        await pg.wait_for_selector('[data-act="seen"]')
        assert 'Priority: Normal → Urgent' in await pg.inner_text('.alertbox.bad')
        await pg.click('[data-act="seen"]')
        await pg.click('#stickbar [data-act="stage-open"]')
        await pg.click('#st-chips [data-k="ready"]')
        await pg.click('[data-act="stage-do"]')
        await pg.wait_for_selector('#stickbar [data-act="dispatch-open"]')
        await pg.click('#stickbar [data-act="dispatch-open"]')
        await pg.click('#dp-mode [data-v="Courier"]'); await pg.fill('#dp-ref', 'DTDC 123'); await pg.fill('#dp-wt', '3.62')
        await pg.click('[data-act="dispatch-do"]')
        await pg.wait_for_function("document.querySelector('.dhead').innerText.includes('Dispatched')")
        print('ok  factory dispatched with final gold weight')
        await logout()

        # ---- 9. store: received, final bill, payment + receipt, PDF, delivered
        await login('nishant', 'nishant1')
        await pg.click('.ocard')
        await pg.click('[data-act="recv"]')
        await pg.wait_for_selector('[data-act="deliv-open"]')
        await pg.click('#price-card [data-act="final-open"]')
        assert await pg.input_value('#fb-goldWt') == '3.62'
        assert await pg.get_attribute('#fb-goldRate', 'readonly') is not None
        fb = await pg.input_value('#fb-final')
        # 3.62*8544 + 8800 + 1500 + 1500 + 3.62*2000 = 30929.28 + 11800 + 7240 = 49969.28; +3% = 51468.36
        assert fb == '51468', fb
        await pg.fill('#fb-final', '51000')
        await pg.click('[data-act="final-do"]')
        await pg.wait_for_function("document.body.innerText.includes('Final bill')")
        await pg.click('#price-card [data-act="pay-open"]')
        await pg.fill('#py-amt', '25000'); await pg.click('#py-mode [data-v="Cash"]')
        await pg.set_input_files('#py-media input[data-pick="image"]', str(TMP / 'ref.png'))
        await pg.wait_for_function("document.querySelector('#py-media').innerText.includes('✓ Upload')")
        await pg.click('[data-act="pay-do"]')
        await pg.wait_for_function("!document.querySelector('#sheet .sheet') && document.body.innerText.includes('Cash')")
        t = await text(); assert 'बाकी\n₹0' in t and 'कुल मिला\n₹51,000' in t, t
        assert '🧾 receipt' in t
        # receipt PDF (libraries stubbed: the sandbox has no CDN)
        await pg.evaluate("""(libs) => {
          libs.forEach(src => { const s = document.createElement('script'); s.dataset.lib = src; document.head.appendChild(s); });
          window.html2canvas = async (el) => { window.__receipt = el.outerHTML; const c = document.createElement('canvas'); c.width = 1588; c.height = 2400; return c; };
          window.jspdf = {jsPDF: function(){ this.internal = {pageSize: {getWidth: () => 595.28, getHeight: () => 841.89}}; this.pages = 1; this.addPage = () => { this.pages++; }; this.addImage = () => {}; this.output = () => new Blob(['%PDF'], {type: 'application/pdf'}); window.__pdf = this; }};
        }""", LIBS)
        try:
            async with pg.expect_download(timeout=8000) as dl:
                await pg.click('#price-card [data-act="pdf"]')
            d = await dl.value
        except Exception:
            print('TOASTS', await pg.inner_text('#toasts')); print(errs[-5:]); raise
        assert d.suggested_filename == no.replace(' ', '') .join(['Deeva-', '.pdf']) or d.suggested_filename == 'Deeva-' + no + '.pdf', d.suggested_filename
        rc = await pg.evaluate('window.__receipt')
        for need in ['MADE TO ORDER', 'Nitu Pansari', 'Round — Portuguese cut', 'VVS2', 'Ruby', '₹51,000', 'Booked @ ₹8,544/g', 'Customer Signature', 'For Deeva Diamonds', 'data:image/png']:
            assert need in rc, need
        assert rc.count('data:image/png') >= 3, 'seal + client signature + Deeva signature'
        if SHOTS:
            rp = await ctx.new_page()
            await rp.set_viewport_size({'width': 794, 'height': 1123})
            await rp.goto('file://' + str(ROOT / 'web' / '_harness.html'))
            await rp.evaluate("(h) => { document.body.innerHTML = h; document.body.style.background = '#fff'; }", rc)
            await rp.wait_for_timeout(300)
            await rp.screenshot(path=str(SHOTS / '08-receipt.png'), full_page=True)
            await rp.close()
        print('ok  final bill from factory weight, payment with receipt photo, receipt PDF (logo, 4Cs, signatures, seal)')
        await pg.click('[data-act="deliv-open"]')
        await pg.click('[data-act="deliv-do"]')
        await pg.wait_for_function("document.querySelector('.dhead').innerText.includes('Delivered')")
        await shot('07-order-store-delivered')
        print('ok  delivered')
        await logout()

        # ---- 10. admin dashboard
        await login('owner@gmail.com', 'owner123')
        await pg.evaluate("location.hash='#/dash'")
        await pg.wait_for_selector('.kpi.hero', timeout=5000)
        await pg.wait_for_function("document.querySelectorAll('.chart svg').length === 3")
        t = await text()
        assert '₹51,000' in t and 'Deeva Diamonds — Bilaspur' in t and 'Pendant with chain' in t, t
        await pg.hover('[data-hover="orders"]')
        await shot('09-dashboard')
        await pg.click('[data-act="dash-store"][data-v="%s"]' % bilaspur)
        await pg.wait_for_function("document.querySelector('.kpi.hero b').innerText === '₹0'")
        print('ok  dashboard: KPIs, 3 line charts, store-wise table, store filter')
        await logout()

        await pg.fill('#l-id', 'nishant'); await pg.fill('#l-pw', 'nope'); await pg.click('#l-submit')
        await pg.wait_for_selector('#l-err:not([hidden])')
        print('ok  wrong password rejected')

        real = [e for e in errs if 'favicon' not in e and 'ERR_FILE_NOT_FOUND' not in e and 'net::' not in e]
        if real:
            print('\n'.join(real)); raise SystemExit('FAIL: page errors')
        await b.close()
    (ROOT / 'web' / '_harness.html').unlink(missing_ok=True)
    print('PASS')

asyncio.run(main())
