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
        await pg.wait_for_function("document.querySelector('#view').innerText.includes('Raipur')")
        await pg.click('[data-act="store-new"]')
        await pg.fill('#st-name', 'Bilaspur'); await pg.fill('#st-city', 'Bilaspur'); await pg.fill('#st-addr', 'Link Road, Bilaspur')
        await pg.click('[data-act="store-save"]')
        await pg.wait_for_function("document.querySelectorAll('[data-act=\"store-edit\"]').length === 2")
        sids = await pg.evaluate("Object.keys(__fake.store).filter(k => k.startsWith('stores/')).map(k => [k.split('/')[1], __fake.store[k].name])")
        raipur = [s for s in sids if s[1] == 'Raipur'][0][0]; bilaspur = [s for s in sids if s[1] == 'Bilaspur'][0][0]

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
        await add('Darshana', 'subadmin', 'darshana', 'darshana1', '9000000001')
        await add('Nishant', 'store', 'nishant', 'nishant1', '9000000002', raipur)
        msg = await add('Duplicate', 'store', 'dup', 'dup12345', '9000000009', raipur, expect_ok=False)
        assert 'already has Nishant' in msg, msg
        await pg.fill('#u-name', ''); await pg.fill('#u-lid', ''); await pg.fill('#u-pw', '')
        await add('Ravi', 'store', 'ravi', 'ravi1234', '9000000005', bilaspur)
        await add('Factory Raju', 'factory', 'factory', 'factory1', '9000000003')
        await pg.click('.card [data-act="rates-open"]')
        await pg.fill('#rt-14KT', '8544'); await pg.fill('#rt-18KT', '10950'); await pg.fill('#rt-making', '2000')
        await pg.click('[data-act="rates-save"]')
        await pg.wait_for_function("!document.querySelector('#sheet .sheet')")
        await pg.click('[data-act="brand-sign"]')
        box = await pg.query_selector('#bsig'); bb = await box.bounding_box()
        await pg.mouse.move(bb['x'] + 30, bb['y'] + 90); await pg.mouse.down()
        for i in range(8): await pg.mouse.move(bb['x'] + 40 + i * 25, bb['y'] + 60 + (i % 2) * 40)
        await pg.mouse.up()
        await pg.click('[data-act="brand-save"]')
        await pg.wait_for_function("!document.querySelector('#sheet .sheet')")
        # Google Sheet backup: shows the address to share with, saves the link
        card = await pg.inner_text('#sheet-card')
        assert '-compute@developer.gserviceaccount.com' in card and 'Google Sheet link' in card, card
        await pg.fill('#sh-url', 'https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-/edit#gid=0')
        await pg.click('[data-act="sheet-save"]')
        await pg.wait_for_function("document.querySelector('#sheet-card').innerText.includes('Open the sheet')")
        shc = await pg.evaluate("__fake.store['config/sheet']")
        assert shc['id'] == '1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-' and shc['syncReq'] > 0, shc
        print('ok  Google Sheet backup linked (server copies every order)')
        await shot('01-team')
        print('ok  default store Raipur + Bilaspur, one manager per store enforced, sub admin, logins, today\'s rate, Deeva signature')
        await logout()

        # ---- 3. store creates an order
        await login('nishant', 'nishant1')
        await pg.click('.banner [data-act="rates-open"]')
        await pg.fill('#rt-22KT', '13300')
        await pg.click('[data-act="rates-save"]')
        await pg.wait_for_function("!document.querySelector('#sheet .sheet')")
        rt = await pg.evaluate("__fake.store['config/rates']")
        assert rt['byName'].startswith('Nishant') and rt['gold']['22KT'] == 13300 and rt['gold']['14KT'] == 8544, rt
        print('ok  store manager sets today\'s gold rate')
        await pg.evaluate("location.hash='#/new'")
        await pg.wait_for_selector('#f-client-name')
        assert await pg.eval_on_selector_all('#view .mic, #view [data-act="mic"]', 'l => l.length') == 0, 'no dictation mic on the form'
        assert await pg.eval_on_selector_all('#view [data-act="rec"]', 'l => l.length') >= 1, 'voice note stays'
        print('ok  no 🎤 dictation on any field; voice note recording stays')
        await pg.click('[data-act="f-review"]')
        await pg.wait_for_selector('#sheet .miss-list li')
        n_miss = await pg.eval_on_selector_all('#sheet .miss-list li', 'l => l.length')
        assert n_miss >= 15, n_miss
        await close_sheet()
        print(f'ok  empty form blocked ({n_miss} required fields listed)')

        await pg.fill('#f-client-name', 'Nitu Pansari'); await pg.fill('#f-client-phone', '9777365551'); await pg.fill('#f-client-city', 'Raipur')
        await chip('spec.jtype', 'Pendant with chain'); await chip('spec.metalColor', 'Yellow Gold'); await chip('spec.purity', '14KT')
        await pg.fill('#f-spec-size', '16 inch')
        await pg.click('#diab-1 [data-act="fill"][data-v="Solitaire"]')
        await pg.fill('#f-spec-dia1Ct', '0.40')
        await pg.wait_for_selector('#dia1-detail:not([hidden])')
        await chip('spec.dia1Shape', 'Round — Portuguese cut'); await chip('spec.dia1Color', 'E-F'); await chip('spec.dia1Clarity', 'VVS1')
        await chip('spec.dia1Cut', 'Excellent'); await chip('spec.dia1Cert', 'IGI')
        await pg.click('[data-act="dia-add"]')
        await pg.wait_for_selector('#diab-2:not([hidden])')
        await pg.click('#diab-2 [data-act="fill"][data-v="Side"]')
        await pg.fill('#f-spec-dia2Ct', '0.10'); await pg.fill('#f-spec-dia2Pcs', '10')
        await chip('spec.dia2Shape', 'Round'); await chip('spec.dia2Color', 'F-G'); await chip('spec.dia2Clarity', 'VS')
        await pg.click('[data-act="dia-add"]'); await pg.wait_for_selector('#diab-3:not([hidden])')
        await pg.click('#diab-3 [data-act="dia-del"]'); await pg.wait_for_selector('#diab-3', state='hidden')
        assert await pg.input_value('#f-spec-dia2Ct') == '0.10', 'removing diamond 3 must keep diamond 2'
        await chip('spec.gem1Type', 'Ruby')
        await pg.wait_for_selector('#gem1-detail:not([hidden])')
        await chip('spec.gem1Color', 'Red'); await chip('spec.gem1Shape', 'Round'); await pg.fill('#f-spec-gem1Ct', '0.20'); await pg.fill('#f-spec-gem1Size', '2 mm'); await pg.fill('#f-spec-gem1Pcs', '4')
        assert (await pg.inner_text('#ctg-gem1')) == '= 0.040 g (40 mg)', await pg.inner_text('#ctg-gem1')
        await pg.fill('#f-spec-stoneNote', 'Centre stone set slightly higher')
        await pg.fill('#f-spec-design', 'Same as the reference image, but without the drop')
        await pg.set_input_files('#f-media input[data-pick="image"]', str(TMP / 'ref.png'))
        await pg.wait_for_function("document.querySelector('#f-media').innerText.includes('✓ Upload')")
        await pg.fill('#f-media .mitem input[data-desc]', 'Client reference — no drop')
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
        assert await pg.input_value('#f-price-calc-goldRate') == '8544', 'today\'s 14KT rate must fill in'
        assert await pg.input_value('#f-price-calc-making') == '2000', 'default making must fill in'
        assert 'Diamond 1 · Solitaire' in await pg.inner_text('#lbl-d1Rate') and 'Diamond 2 · Side' in await pg.inner_text('#lbl-d2Rate')
        for k, v in [('grossWt', '3.75'), ('d1Rate', '22000'), ('d2Rate', '15000'), ('gemAmt', '1500')]:
            await pg.fill(f'#f-price-calc-{k}', v)
        assert (await pg.inner_text('#ctg-dia1')) == '= 0.080 g (80 mg)'
        wt = await pg.inner_text('#wt-out')
        # stones: dia 0.40 + 0.10 + ruby 0.20 = 0.70 ct = 0.140 g -> net gold 3.750 − 0.140 = 3.610 g
        for x in ['Gross weight', '3.750 g', 'Diamond 1 · Solitaire', '0.40 ct = 0.080 g', 'Diamond 2 · Side', '0.10 ct = 0.020 g', 'Gemstone 1 · Ruby', '0.20 ct = 0.040 g', 'Net gold weight', '3.610 g']:
            assert x in wt, (x, wt)
        calc_txt = await pg.inner_text('#calc-out')
        # gold 3.61*8544 = 30843.84; dia 8800 + 1500; gem 1500; making 3.61*2000 = 7220; value 49863.84; GST 1495.92; total 51359.76
        for x in ['Net gold 3.610 g = gross 3.750 g − stones 0.7 ct (0.140 g)', 'Gold — net 3.610 g × ₹8,544', '₹30,843.84', 'Diamond 1 · Solitaire — 0.4 ct × ₹22,000', '₹8,800', 'Diamond 2 · Side — 0.1 ct × ₹15,000', 'Making — net 3.610 g × ₹2,000', '₹7,220', '₹49,863.84', '₹51,359.76']:
            assert x in calc_txt, (x, calc_txt)
        await pg.click('[data-act="calc-apply"]')
        assert await pg.input_value('#f-price-est') == '51360'
        await pg.fill('#f-price-est', '52000')
        print('ok  estimate: diamonds + gemstone ct → g (1 ct = 0.200 g), net gold = gross − stones, gold + making on net = 51,360; deal 52,000')
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
        assert 'Round — Portuguese cut' in rv and 'VVS1' in rv and 'Ruby' in rv and '₹52,000' in rv and 'Diamond 2 · Side' in rv, rv
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
        assert abs(pv['price']['calc']['final'] - 51359.7552) < 0.01 and abs(pv['price']['calc']['net'] - 3.61) < 1e-9 and pv['ack']['signData'].startswith('data:image/png')
        assert st['spec']['dia2Type'] == 'Side' and st['spec']['dia3Ct'] == '', st['spec']
        assert any(m.get('receipt') for m in pv['media'].values()), pv['media']
        print(f'ok  order {no} submitted (4Cs, gemstone, deal amount, booked rate, receipt, signature)')
        await shot('04-order-store')
        await logout()

        # ---- 4. other store's manager sees nothing
        await login('ravi', 'ravi1234')
        await pg.wait_for_function("document.body.innerText.includes('No active orders')")
        print('ok  Bilaspur manager does not see Raipur orders')
        await logout()

        # ---- 5. Darshana query, Nishant edit + reply, approve
        await login('darshana', 'darshana1')
        assert 'Sub Admin' in await pg.inner_text('#who')
        t = await pg.inner_text('#tabs'); assert 'Dashboard' in t and 'Activity' in t and 'Team' in t, t
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
        await pg.wait_for_function("document.querySelector('.dhead').innerText.includes('Awaiting approval')")
        t = await text(); assert 'Diamond 1 clarity: VVS1 → VVS2' in t, t
        assert 'Estimate calculation changed' not in t
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
        for secret in ['Nitu', '9777365551', '52,000', '26,000', 'Clarity VVS1 ya', 'receipt', 'Nishant', '9000000002', 'Darshana', '9000000001']:
            assert secret not in t, 'factory can see ' + secret
        assert 'Deeva Diamonds — Raipur' in t and 'Currency Tower' in t, 'factory sees the store and its address'
        for need in ['VVS2', 'Round — Portuguese cut', 'Diamond 1 · Solitaire', 'Diamond 2 · Side', 'Ruby', 'Centre stone set slightly higher', 'Client reference', 'Light weight chain', '🏬']:
            assert need in t, need
        assert await pg.eval_on_selector_all('.gal audio', 'l => l.length') >= 1
        await shot('05-order-factory-new')
        print('ok  factory sees 4Cs, gemstone, photo + its voice note; no client / price / receipt')
        await pg.click('.alertbox.ok [data-act="stage-quick"]')
        await pg.wait_for_function("document.querySelector('#stickbar').innerText.includes('Next')")
        await pg.click('#stickbar [data-act="stage-quick"]')
        await pg.wait_for_timeout(200)
        await pg.click('#stickbar [data-act="stage-open"]')
        await pg.click('#st-chips [data-k="cad_approval"]')
        await pg.set_input_files('#st-media input[data-pick="image"]', str(TMP / 'ref.png'))
        await pg.wait_for_function("document.querySelector('#st-media').innerText.includes('✓ Upload')")
        await pg.click('[data-act="stage-do"]')
        await pg.wait_for_function("document.body.innerText.includes('Awaiting CAD approval')")
        await logout()

        # ---- 7. store: CAD OK, then priority + date change
        await login('nishant', 'nishant1')
        await pg.click('.ocard')
        await pg.click('[data-act="cad-ok"]'); await pg.click('#sheet [data-act="confirm-ok"]')
        await pg.wait_for_function("!document.querySelector('[data-act=\"cad-ok\"]')")
        await pg.click('[data-act="sched-open"]')
        await pg.click('#sc-pri [data-v="urgent"]')
        await pg.fill('#sc-day', await pg.evaluate("(() => { const d = new Date(Date.now() + 10*864e5); return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0'); })()"))
        await pg.fill('#sc-why', 'The client needs it earlier')
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
        await pg.wait_for_selector('#dp-gross')
        assert await pg.input_value('#dp-d1-ct') == '0.40' and await pg.input_value('#dp-touch') == '58.5'
        await pg.click('[data-act="dispatch-do"]')
        await pg.wait_for_function("document.querySelector('#toasts').innerText.includes('Still required')")
        await pg.fill('#dp-gross', '3.62')
        await pg.fill('#dp-d1-ct', '0.42'); await pg.click('#dp-d1-cert [data-v="yes"]'); await pg.fill('#dp-d1-certno', 'IGI123'); await pg.fill('#dp-d1-rate', '21000')
        # side diamonds split into two sizes, each with its own rate (0.06 ct × 15,000 + 0.04 ct × 12,500 = 1,400)
        await pg.fill('#dp-d2-size', '−2'); await pg.fill('#dp-d2-ct', '0.06'); await pg.fill('#dp-d2-pcs', '8'); await pg.fill('#dp-d2-rate', '15000')
        await pg.click('[data-act="dp-part-add"][data-g="d2"]')
        await pg.wait_for_selector('#dp-d2p2-ct')
        assert await pg.input_value('#dp-d2p2-shape') == await pg.input_value('#dp-d2-shape'), 'new size keeps the shape'
        await pg.fill('#dp-d2p2-size', '+6'); await pg.select_option('#dp-d2p2-shape', 'Pear'); await pg.fill('#dp-d2p2-ct', '0.04'); await pg.fill('#dp-d2p2-pcs', '4'); await pg.fill('#dp-d2p2-rate', '12500')
        await pg.select_option('#dp-d2p2-color', 'G-H'); await pg.select_option('#dp-d2p2-clarity', 'VS2')
        await pg.click('#dp-d2-cert [data-v="no"]')
        # a diamond that was not in the order can be added (and removed again)
        await pg.click('[data-act="dp-extra-add"]'); await pg.wait_for_selector('#dp-d5-type')
        await pg.click('[data-act="dp-grp-del"][data-g="d5"]'); await pg.wait_for_function("!document.querySelector('#dp-d5-type')")
        await pg.fill('#dp-g1-amt', '1200')
        await pg.click('#dp-hm [data-v="yes"]'); await pg.fill('#dp-huid', 'AB1234')
        await pg.click('#dp-gm [data-v="fine"]'); await pg.fill('#dp-touch', '59')
        await pg.fill('#dp-lrate', '900'); await pg.fill('#dp-other', '300')
        assert await pg.input_value('#dp-net') == '3.476', await pg.input_value('#dp-net')   # 3.62 − 0.72 ct × 0.2
        assert await pg.input_value('#dp-d1-amt') == '8820'
        sm = await pg.inner_text('#dp-sum')
        # fine 3.476 × 59% = 2.051 g; total 8820 + 1400 + 1200 + 3.476×900 (3128.4) + 300 = 14,848.4
        for x in ['Net gold', '3.476 g', 'Fine gold — 3.476 g × 59%', '2.051 g', '₹14,848.4']:
            assert x in sm, (x, sm)
        await pg.click('#dp-mode [data-v="Courier"]'); await pg.fill('#dp-ref', 'DTDC 123')
        await pg.set_input_files('#dp-media input[data-pick="image"]', str(TMP / 'ref.png'))
        await pg.wait_for_function("document.querySelector('#dp-media').innerText.includes('✓ Upload')")
        await pg.click('[data-act="dispatch-do"]')
        await pg.wait_for_function("document.querySelector('.dhead').innerText.includes('Dispatched')")
        await pg.wait_for_selector('#sheet [data-act="fpdf"]')
        await pg.evaluate('''(libs) => {
          libs.forEach(src => { const s = document.createElement('script'); s.dataset.lib = src; document.head.appendChild(s); });
          window.html2canvas = async (el) => { window.__fbill = el.outerHTML; const c = document.createElement('canvas'); c.width = 1120; c.height = 1500; return c; };
          window.jspdf = {jsPDF: function(o){ this.addImage = () => {}; this.output = () => new Blob(['%PDF'], {type: 'application/pdf'}); }};
        }''', LIBS)
        async with pg.expect_download(timeout=8000) as dl:
            await pg.click('#sheet [data-act="fpdf"]')
        fname = (await dl.value).suggested_filename
        await pg.wait_for_function("!document.querySelector('#sheet .sheet')")
        fb = await pg.evaluate('window.__fbill')
        if SHOTS: SHOTS.mkdir(parents=True, exist_ok=True); (SHOTS / 'factory-bill.html').write_text('<base href="file://' + str(ROOT / 'web') + '/">' + fb, encoding='utf8')
        for x in ['FACTORY BILL', 'Deeva Diamonds — Raipur', 'Currency Tower', '2.051 g', '₹14,848.4', 'IGI123', 'AB1234', '59%']:
            assert x in fb, (x, fb[:400])
        for x in ['Nitu', '9777365551', 'Nishant']:
            assert x not in fb, 'factory PDF shows ' + x
        assert fname.startswith('Factory-Bill-') and fname.endswith('.pdf'), fname
        assert await pg.eval_on_selector_all('[data-act="fpdf"]', 'l => l.length') == 1, 'PDF button on the slip'
        print('ok  factory bill PDF saved with order number (' + fname + '), store + address, no client / store person')
        bill = await pg.evaluate("Object.entries(__fake.store).find(([k]) => k.endsWith('/factory/bill'))[1]")
        assert bill['goldMode'] == 'fine' and abs(bill['fine'] - 2.051) < 1e-9 and bill['total'] == 14848.4, bill
        d2 = [l for l in bill['lines'] if l['kind'] == 'd' and l['n'] == 2]
        assert [(l['size'], l['shape'], l['ct'], l['pcs'], l['rate'], l['amt']) for l in d2] == [('−2', 'Round', 0.06, '8', 15000, 900), ('+6', 'Pear', 0.04, '4', 12500, 500)], d2
        assert d2[1]['color'] == 'G-H' and d2[1]['clarity'] == 'VS2', d2
        st = await order_doc(); a = st['dispatch']['actual']
        assert a['netWt'] == 3.476 and a['dias'][0]['ct'] == 0.42 and a['dias'][0]['cert'] == 'yes' and a['hallmark'] == 'yes', a
        assert a['dias'][1]['ct'] == 0.1 and a['dias'][1]['pcs'] == '12' and len(a['dias'][1]['parts']) == 2 and len(a['dias']) == 2, a['dias']
        t = await text(); assert '−2 · Round' in t and '+6 · Pear · G-H · VS2' in t and 'Diamond 2 · Side (+6 · Pear) — 0.04 ct / 4 pc' in t, 'slip shows each size'
        print('ok  factory splits a diamond line into sizes with own rates, shape / colour / clarity per size; extra diamonds supported')
        t = await text(); assert 'Dispatch Slip' in t and 'Factory total' in t
        await shot('06-factory-slip')
        print('ok  factory dispatch slip: actual ct / pcs / certified / hallmark, net auto, fine 59% = 2.051 g, factory total ₹14,848.4')
        await logout()
        await login('owner@gmail.com', 'owner123')
        await pg.click('.ocard')
        await pg.wait_for_function("document.body.innerText.includes('Factory total')")
        t = await text(); assert '0.42 ct / 1 pc' in t and '✓ Yes · IGI123' in t and '✓ Yes · AB1234' in t, t
        print('ok  admin sees ordered vs actual + factory bill')
        await logout()

        # ---- 9. store: received, final bill, payment + receipt, PDF, delivered
        await login('nishant', 'nishant1')
        await pg.click('.ocard')
        await pg.wait_for_function("document.body.innerText.includes('Dispatch Slip')")
        t = await text()
        for secret in ['Raju', '9000000003', 'Factory bill', '14,848']:
            assert secret not in t, 'store can see ' + secret
        print('ok  store sees no factory person and no factory bill')
        assert '0.42 ct / 1 pc' in t and 'Factory total' not in t and '14,848' not in t and 'Fine gold' not in t, 'store must not see factory money'
        print('ok  store sees actual weights / carats / hallmark but not the factory bill')
        await pg.click('[data-act="recv"]')
        await pg.wait_for_selector('[data-act="deliv-open"]')
        await pg.click('#price-card [data-act="final-open"]')
        assert await pg.input_value('#fb-grossWt') == '3.62'
        assert await pg.get_attribute('#fb-goldRate', 'readonly') is not None
        assert await pg.input_value('#fb-netWt') == '3.476' and await pg.input_value('#fb-dct1') == '0.42'
        fb = await pg.input_value('#fb-final')
        # actual: net 3.476 g; gold 3.476×8544 = 29698.944; dia1 0.42×22000 = 9240; dia2 1500; gem 1500; making 3.476×2000 = 6952
        # value 48890.944; +3% = 50357.67
        assert fb == '50358', fb
        assert 'Net gold weight' in await pg.inner_text('#fb-wt') and '3.476 g' in await pg.inner_text('#fb-wt')
        await pg.fill('#fb-final', '51000')
        await pg.click('[data-act="final-do"]')
        await pg.wait_for_function("document.body.innerText.includes('Final bill')")
        await pg.click('#price-card [data-act="pay-open"]')
        await pg.fill('#py-amt', '25000'); await pg.click('#py-mode [data-v="Cash"]')
        await pg.set_input_files('#py-media input[data-pick="image"]', str(TMP / 'ref.png'))
        await pg.wait_for_function("document.querySelector('#py-media').innerText.includes('✓ Upload')")
        await pg.click('[data-act="pay-do"]')
        await pg.wait_for_function("!document.querySelector('#sheet .sheet') && document.body.innerText.includes('Cash')")
        t = await text(); assert 'Balance due\n₹0' in t and 'Total received\n₹51,000' in t, t
        assert '🧾 receipt' in t
        # receipt PDF (libraries stubbed: the sandbox has no CDN)
        await pg.evaluate("""(libs) => {
          libs.forEach(src => { const s = document.createElement('script'); s.dataset.lib = src; document.head.appendChild(s); });
          window.html2canvas = async (el) => { window.__receipt = el.outerHTML; const c = document.createElement('canvas'); c.width = 1588; c.height = 2400; return c; };
          window.jspdf = {jsPDF: function(o){ window.__pdfFormat = JSON.stringify(o && o.format); this.internal = {pageSize: {getWidth: () => 595.28, getHeight: () => 841.89}}; this.pages = 1; this.addPage = () => { this.pages++; }; this.addImage = () => {}; this.output = () => new Blob(['%PDF'], {type: 'application/pdf'}); window.__pdf = this; }};
        }""", LIBS)
        try:
            async with pg.expect_download(timeout=8000) as dl:
                await pg.click('#price-card [data-act="pdf-wa"]')
            d = await dl.value
            await pg.wait_for_selector('#sheet a.wa[href*="wa.me/919777365551"]', timeout=3000)
            await close_sheet()
        except Exception:
            print('TOASTS', await pg.inner_text('#toasts')); print(errs[-5:]); raise
        assert d.suggested_filename == no.replace(' ', '') .join(['Deeva-', '.pdf']) or d.suggested_filename == 'Deeva-' + no + '.pdf', d.suggested_filename
        rc = await pg.evaluate('window.__receipt')
        for need in ['Deeva Diamonds — Raipur', 'MADE TO ORDER', 'Nitu Pansari', 'Diamond 1 · Solitaire', 'Round — Portuguese cut', 'VVS2', 'Ruby', 'Final bill', '₹51,000', 'Booked @ ₹8,544/g (14KT)', 'Balance', 'Customer signature', 'For Deeva Diamonds', 'data:image/png', 'Net gold 3.476 g', 'Diamonds 0.52 ct (0.104 g)', 'Gross 3.620 g', '0.2 ct · 2 mm',
                     'Estimate (at order)', 'Diamond 1 · Solitaire — 0.4 ct × ₹22,000', 'Making — net 3.610 g × ₹2,000', 'Final bill (actual weight)', 'Total (actual)', 'Diamond 1 · Solitaire:</b> 0.42 ct', 'Diamond 1 · Solitaire — 0.42 ct × ₹22,000', 'Gold — net 3.476 g × ₹8,544', 'HUID AB1234', 'Certified</b> IGI123']:
            assert need in rc, need
        assert '14,848' not in rc and 'Fine' not in rc, 'factory cost never goes to the client'
        assert (await pg.evaluate('window.__pdfFormat')).startswith('[419.53,'), 'one A5-wide page'
        assert rc.count('data:image/png') >= 3, 'seal + client signature + Deeva signature'
        if SHOTS:
            rp = await ctx.new_page()
            await rp.set_viewport_size({'width': 560, 'height': 1100})
            await rp.goto('file://' + str(ROOT / 'web' / '_harness.html'))
            await rp.evaluate("(h) => { document.body.innerHTML = h; document.body.style.background = '#fff'; }", rc)
            await rp.wait_for_timeout(300)
            await rp.screenshot(path=str(SHOTS / '08-receipt.png'), full_page=True)
            await rp.close()
        print('ok  final bill from factory gross weight (net gold), payment with receipt photo, short A5 receipt → client WhatsApp')
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
        assert '₹51,000' in t and 'Bilaspur' in t and 'Pendant with chain' in t, t
        await pg.hover('[data-hover="orders"]')
        await shot('09-dashboard')
        await pg.click('[data-act="dash-store"][data-v="%s"]' % bilaspur)
        await pg.wait_for_function("document.querySelector('.kpi.hero b').innerText === '₹0'")
        print('ok  dashboard: KPIs, 3 line charts, store-wise table, store filter')
        await pg.evaluate("location.hash='#/activity'")
        await pg.wait_for_function("document.body.innerText.includes('All Activity') && document.querySelectorAll('#view .ocard').length > 10")
        t = await text()
        for need in ['Nishant · Raipur (Store)', 'Factory Raju (Factory)', 'Darshana (Sub Admin)', 'Diamond 1 clarity: VVS1 → VVS2', 'Payment ₹25,000 (Cash)', 'Nitu Pansari']:
            assert need in t, need
        await pg.click('[data-act="act-who"][data-v="money"]')
        await pg.wait_for_function("document.querySelectorAll('#view .ocard').length >= 2 && !document.querySelector('#view').innerText.includes('Dispatched —')")
        await shot('10-activity')
        print('ok  activity: every action by every person, payments filter')
        # past orders: the delivered order stays, with its history
        await pg.evaluate("location.hash='#/past'")
        await pg.wait_for_function("document.querySelector('#view').innerText.includes('Past Orders') && document.querySelectorAll('#view .ocard').length === 1")
        await pg.click('#view .ocard')
        await pg.wait_for_function("document.body.innerText.includes('Full history') && document.body.innerText.includes('Delivered to client')")
        print('ok  delivered order stays under Past Orders with its full history')
        await logout()
        # store manager and sub admin cannot delete; the main Admin can, after typing the order number
        await login('darshana', 'darshana1')
        await pg.evaluate("location.hash='#/past'")
        await pg.wait_for_selector('#view .ocard'); await pg.click('#view .ocard')
        await pg.wait_for_function("document.body.innerText.includes('Full history')")
        assert await pg.eval_on_selector_all('[data-act="del-open"]', 'l => l.length') == 0, 'sub admin must not delete'
        await logout()
        await login('owner@gmail.com', 'owner123')
        await pg.evaluate("location.hash='#/past'")
        await pg.wait_for_selector('#view .ocard'); await pg.click('#view .ocard')
        await pg.click('[data-act="del-open"]')
        await pg.fill('#del-no', 'DD-0000-000'); await pg.click('[data-act="del-do"]')
        await pg.wait_for_function("document.querySelector('#toasts').innerText.includes('does not match')")
        assert await pg.evaluate("Object.keys(__fake.store).some(k => k.startsWith('orders/'))")
        await pg.fill('#del-no', no.lower()); await pg.click('[data-act="del-do"]')
        await pg.wait_for_function("!Object.keys(__fake.store).some(k => k.startsWith('orders/') && __fake.store[k].no === " + repr(no) + ")")
        left = await pg.evaluate("Object.keys(__fake.store).filter(k => k.startsWith('orders/'))")
        assert not any(k.endswith('/private/info') or k.endswith('/factory/bill') for k in left), left
        await pg.wait_for_function("location.hash === '#/'")
        print('ok  only the main Admin can delete an order permanently (order no. typed to confirm)')
        await logout()
        await login('darshana', 'darshana1')
        await pg.evaluate("location.hash='#/team'")
        await pg.wait_for_selector('.urow')
        owner_row = await pg.evaluate("[...document.querySelectorAll('.urow')].find(r => r.innerText.includes('Mayuresh')).innerHTML")
        assert 'u-menu' not in owner_row, 'sub admin must not be able to change the admin'
        print('ok  sub admin cannot change the main admin')
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
