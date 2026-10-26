"""End-to-end test of Deeva Orders against an in-memory fake Firebase (tools/fake-backend.js).

Run:  python3 tools/test_flow.py [screenshot_dir]
Needs: Python Playwright with Chromium. Does not touch the real Firebase project.
Covers: first admin setup, team logins, store creates an order (mandatory fields, calculator,
photo + voice note, signature), admin query -> store reply + edit, approve, factory view without
client/price, CAD approval, stage updates, admin edit alert to factory, dispatch, payment, delivered.
"""
import asyncio, re, sys, tempfile, pathlib, base64
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(tempfile.mkdtemp(prefix='do-test-'))
SHOTS = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')


def build_harness():
    src = (ROOT / 'web/index.html').read_text(encoding='utf8')
    fake = (ROOT / 'tools/fake-backend.js').read_text(encoding='utf8')
    src = re.sub(r'<!--FIREBASE-SDK-->.*?<!--/FIREBASE-SDK-->', '<script>' + fake + '</script>', src, flags=re.S)
    src = src.replace('<link rel="stylesheet" href="https://fonts.googleapis.com', '<link rel="x" href="https://fonts.googleapis.com')
    out = ROOT / 'web' / '_harness.html'   # inside web/ so icons/ resolve
    out.write_text(src, encoding='utf8')
    (TMP / 'ref.png').write_bytes(PNG)
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
        pg.on('dialog', lambda d: asyncio.ensure_future(d.accept()))
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
            await pg.wait_for_timeout(250)

        async def logout():
            await pg.evaluate("location.hash='#/account'")
            await pg.wait_for_selector('[data-act="logout"]')
            await pg.click('[data-act="logout"]')
            await pg.wait_for_selector('#login-form', timeout=5000)

        async def text():
            return await pg.inner_text('body')

        # ---- 1. first setup = admin
        await pg.wait_for_selector('#setup-form', timeout=5000)
        await shot('00-setup')
        await pg.fill('#s-name', 'Mayuresh Sisodiya'); await pg.fill('#s-email', 'owner@gmail.com')
        await pg.fill('#s-pw', 'owner123'); await pg.fill('#s-pw2', 'owner123'); await pg.click('#s-submit')
        await pg.wait_for_selector('#tabs:not([hidden])', timeout=5000)
        assert 'Team' in await pg.inner_text('#tabs')
        print('ok  admin setup')

        # ---- 2. team logins
        await pg.evaluate("location.hash='#/team'")
        await pg.wait_for_selector('#u-name')
        async def add(name, role, lid, pw, phone):
            await pg.fill('#u-name', name)
            await pg.click(f'#u-role [data-v="{role}"]')
            await pg.fill('#u-lid', lid); await pg.fill('#u-pw', pw); await pg.fill('#u-phone', phone)
            await pg.click('#u-add')
            await pg.wait_for_selector('#sheet .cred', timeout=5000)
            t = await pg.inner_text('#sheet .cred'); assert lid in t and pw in t, t
            await close_sheet()
        await add('Darshana', 'admin', 'darshana', 'darshana1', '9000000001')
        await add('Nishant', 'store', 'nishant', 'nishant1', '9000000002')
        await add('Factory Raju', 'factory', 'factory', 'factory1', '9000000003')
        await pg.wait_for_function("document.querySelectorAll('.urow').length === 4")
        await shot('01-team')
        print('ok  3 logins created (admin, store, factory)')
        await logout()

        # ---- 3. store creates an order
        await login('nishant', 'nishant1')
        tabs = await pg.inner_text('#tabs'); assert 'नया Order' in tabs and 'Team' not in tabs, tabs
        await pg.evaluate("location.hash='#/new'")
        await pg.wait_for_selector('#f-client-name')
        await pg.click('[data-act="f-review"]')
        await pg.wait_for_selector('#sheet .miss-list li')
        n_miss = await pg.eval_on_selector_all('#sheet .miss-list li', 'l => l.length')
        assert n_miss >= 12, n_miss
        await close_sheet()
        print(f'ok  empty form blocked ({n_miss} required fields listed)')

        await pg.fill('#f-client-name', 'Nitu Pansari'); await pg.fill('#f-client-phone', '9777365551'); await pg.fill('#f-client-city', 'Raipur')
        await pg.click('[data-act="chip"][data-f="spec.jtype"][data-v="Pendant with chain"]')
        await pg.click('[data-act="chip"][data-f="spec.metalColor"][data-v="Yellow Gold"]')
        await pg.click('[data-act="chip"][data-f="spec.purity"][data-v="14KT"]')
        await pg.fill('#f-spec-size', '16 inch')
        await pg.fill('#f-spec-dia1Ct', '0.40'); await pg.click('[data-act="chip"][data-f="spec.dia1Shape"][data-v="Mix"]')
        await pg.fill('#f-spec-design', 'Design ref image jaisa hi, par drop nahi lagana')
        await pg.set_input_files('#f-media input[data-pick="image"]', str(TMP / 'ref.png'))
        await pg.wait_for_selector('#f-media .mitem input[data-desc]')
        await pg.wait_for_function("document.querySelector('#f-media').innerText.includes('✓ Upload')")
        await pg.fill('#f-media .mitem input[data-desc]', 'Client ka reference — drop nahi')
        # voice note (fake mic)
        await pg.click('#f-media [data-act="rec"]')
        await pg.wait_for_timeout(1600)
        await pg.click('#f-media [data-act="rec"]')
        await pg.wait_for_function("document.querySelectorAll('#f-media .mitem').length === 2", timeout=8000)
        await pg.wait_for_function("!document.querySelector('#f-media').innerText.includes('Upload ')||document.querySelector('#f-media').innerText.split('✓ Upload').length===3", timeout=8000)
        voice_ok = await pg.eval_on_selector_all('#f-media .mitem audio', 'l => l.length')
        assert voice_ok == 1, voice_ok
        descs = await pg.query_selector_all('#f-media .mitem input[data-desc]')
        await descs[1].fill('Client ne design samjhaya')
        print('ok  photo + voice note attached with descriptions')
        # calculator -> est amount
        await pg.click('[data-act="calc-toggle"]')
        for k, v in [('goldWt', '3.75'), ('goldRate', '8544'), ('diaRate', '22000'), ('making', '2000'), ('gst', '3')]:
            await pg.fill(f'#c-{k}', v)
        calc_txt = await pg.inner_text('#calc-out')
        assert '49,790' in calc_txt, calc_txt
        await pg.click('[data-act="calc-apply"]')
        assert await pg.input_value('#f-price-est') == '49790'
        print('ok  calculator 3.75g x 8544 + 0.40ct x 22000 + making + 3% GST = 49,790')
        await pg.click('[data-act="chip"][data-f="price.goldRateBooked"][data-v="no"]')
        await pg.fill('#f-advance-amount', '13000'); await pg.click('[data-act="chip"][data-f="advance.mode"][data-v="UPI"]')
        await pg.click('[data-act="f-days"][data-n="15"]')
        await pg.check('#f-ack')
        box = await pg.query_selector('#sig'); bb = await box.bounding_box()
        await pg.mouse.move(bb['x'] + 30, bb['y'] + 100); await pg.mouse.down()
        for i in range(10): await pg.mouse.move(bb['x'] + 40 + i * 20, bb['y'] + 60 + (i % 3) * 25)
        await pg.mouse.up()
        await shot('02-new-order-form')
        await pg.click('[data-act="f-review"]')
        await pg.wait_for_selector('#sheet [data-act="f-submit"]:not([disabled])', timeout=3000)
        await shot('03-review')
        await pg.click('#sheet [data-act="f-submit"]')
        await pg.wait_for_selector('.dhead .no', timeout=5000)
        no = (await pg.inner_text('.dhead .no')).strip()
        assert re.match(r'^DD-\d{4}-001$', no), no
        await pg.wait_for_selector('#sheet .sheet', timeout=3000)
        assert 'WhatsApp: Darshana' in await pg.inner_text('#sheet')
        await close_sheet()
        st = await pg.evaluate("Object.values(__fake.store).find(d => d.no)")
        assert st['status'] == 'review' and st['spec']['size'] == '16 inch' and st['factoryVisible'] is False, st
        assert 'client' not in st and 'price' not in st, 'client/price must not be in the factory-visible doc'
        pv = await pg.evaluate("Object.entries(__fake.store).find(([k]) => k.endsWith('/private/info'))[1]")
        assert pv['client']['name'] == 'Nitu Pansari' and pv['price']['est'] == 49790 and pv['ack']['signUrl'], pv
        assert len(pv['payments']) == 1
        assert len(st['media']) == 2, st['media']
        print(f'ok  order {no} submitted (client+price in private doc, signature saved, advance recorded)')
        await shot('04-order-store')
        await logout()

        # ---- 4. Darshana (admin) sends a query
        await login('darshana', 'darshana1')
        assert '1' in await pg.inner_text('#tabs')
        await pg.click('.ocard')
        await pg.wait_for_selector('[data-act="query-open"]')
        await pg.click('.alertbox [data-act="query-open"]')
        await pg.fill('#qr-text', 'Chain 16 inch hai ya 18 inch?')
        await pg.click('[data-act="query-do"]')
        await pg.wait_for_selector('#sheet a.wa', timeout=3000)
        await close_sheet()
        await pg.wait_for_function("document.querySelector('.dhead').innerText.includes('Query')")
        print('ok  admin sent a query')
        await logout()

        # ---- 5. Nishant replies and corrects the size
        await login('nishant', 'nishant1')
        await pg.click('.ocard')
        await pg.wait_for_selector('.alertbox.bad')
        await pg.click('.alertbox a[href^="#/edit/"]')
        await pg.wait_for_selector('#f-spec-size')
        assert await pg.input_value('#f-spec-size') == '16 inch'
        await pg.fill('#f-spec-size', '18 inch')
        await pg.click('[data-act="f-review"]')
        await pg.wait_for_selector('.dhead .no')
        await pg.click('.alertbox [data-act="reply-open"]')
        await pg.fill('#rp-text', '18 inch final, client se confirm kiya')
        await pg.click('[data-act="reply-do"]')
        await pg.wait_for_function("document.querySelector('.dhead').innerText.includes('Approval बाकी')")
        t = await text(); assert 'Size / Length: 16 inch → 18 inch' in t, t
        assert 'हिसाब (calculation) बदला' not in t, 'calc must not count as changed'
        print('ok  store edited size (diff logged) and replied')
        await logout()

        # ---- 6. Darshana approves
        await login('darshana', 'darshana1')
        await pg.click('.ocard')
        await pg.wait_for_selector('.alertbox [data-act="approve-open"]')
        await shot('05-order-admin-review')
        await pg.click('.alertbox [data-act="approve-open"]')
        await pg.wait_for_selector('#ap-due')
        await pg.fill('#ap-note', 'Light weight chain')
        await pg.click('[data-act="approve-do"]')
        await pg.wait_for_selector('#sheet a.wa', timeout=3000)
        assert 'Factory Raju' in await pg.inner_text('#sheet')
        await close_sheet()
        await pg.wait_for_function("document.querySelector('.dhead').innerText.includes('Factory में')")
        print('ok  admin approved -> factory')
        await logout()

        # ---- 7. factory: no client, no price; acknowledges; sends CAD
        await login('factory', 'factory1')
        tabs = await pg.inner_text('#tabs'); assert 'नया Order' not in tabs
        await pg.click('.ocard')
        await pg.wait_for_selector('.alertbox.ok [data-act="stage-quick"]')
        t = await text()
        for secret in ['Nitu', '9777365551', '49,790', '13,000', 'Est. Amount', 'Chain 16 inch hai ya 18']:
            assert secret not in t, 'factory can see ' + secret
        assert '18 inch' in t and 'drop' in t and 'Client ka reference' in t and 'Client ne design samjhaya' in t and 'Light weight chain' in t
        assert await pg.eval_on_selector_all('.gi audio', 'l => l.length') == 1
        await shot('06-order-factory-new')
        print('ok  factory sees product + photo + voice note, but no client / price / query')
        await pg.click('.alertbox.ok [data-act="stage-quick"]')
        await pg.wait_for_function("document.querySelector('#stickbar').innerText.includes('आगे')")
        await pg.click('#stickbar [data-act="stage-quick"]')   # -> CAD
        await pg.wait_for_timeout(200)
        await pg.click('#stickbar [data-act="stage-open"]')
        await pg.wait_for_selector('#st-chips')
        assert await pg.get_attribute('#st-chips [data-k="casting"]', 'disabled') is not None, 'casting must be blocked before CAD OK'
        await pg.click('#st-chips [data-k="cad_approval"]')
        await pg.set_input_files('#st-media input[data-pick="image"]', str(TMP / 'ref.png'))
        await pg.wait_for_function("document.querySelector('#st-media').innerText.includes('✓ Upload')")
        await pg.fill('#st-media input[data-desc]', 'CAD v1')
        await pg.click('[data-act="stage-do"]')
        await pg.wait_for_function("!document.querySelector('#sheet .sheet')")
        await pg.wait_for_function("document.body.innerText.includes('CAD approval का इंतज़ार')")
        print('ok  factory: received -> CAD -> sent CAD for approval (casting blocked)')
        await logout()

        # ---- 8. store approves CAD; admin edits after approval
        await login('nishant', 'nishant1')
        await pg.click('.ocard')
        await pg.wait_for_selector('[data-act="cad-ok"]')
        await pg.click('[data-act="cad-ok"]')
        await pg.wait_for_function("!document.querySelector('[data-act=\"cad-ok\"]')")
        print('ok  store gave CAD OK')
        await logout()
        await login('owner@gmail.com', 'owner123')
        await pg.click('.ocard')
        await pg.wait_for_selector('#stickbar a[href^="#/edit/"]')
        await pg.click('#stickbar a[href^="#/edit/"]')
        await pg.wait_for_selector('#f-spec-engraving')
        await pg.fill('#f-spec-engraving', 'N')
        await pg.click('[data-act="f-review"]')
        await pg.wait_for_selector('.dhead .no')
        st = await pg.evaluate("Object.values(__fake.store).find(d => d.no)")
        assert st['factoryAck'] is False and st['stage'] == 'casting', st
        print('ok  admin edited after approval -> factory alerted')
        await logout()

        # ---- 9. factory sees change, works, dispatches
        await login('factory', 'factory1')
        await pg.click('.ocard')
        await pg.wait_for_selector('[data-act="seen"]')
        assert 'Engraving: — → N' in await pg.inner_text('.alertbox.bad')
        await pg.click('[data-act="seen"]')
        await pg.wait_for_function("!document.querySelector('[data-act=\"seen\"]')")
        await pg.click('#stickbar [data-act="stage-open"]')
        await pg.click('#st-chips [data-k="ready"]')
        await pg.fill('#st-note', 'Gold 3.62g')
        await pg.click('[data-act="stage-do"]')
        await pg.wait_for_selector('#stickbar [data-act="dispatch-open"]')
        await pg.click('#stickbar [data-act="dispatch-open"]')
        await pg.click('#dp-mode [data-v="Courier"]')
        await pg.fill('#dp-ref', 'DTDC 123')
        await pg.click('[data-act="dispatch-do"]')
        await pg.wait_for_function("document.querySelector('.dhead').innerText.includes('Dispatched')")
        st = await pg.evaluate("Object.values(__fake.store).find(d => d.no)")
        assert st['dispatch']['mode'] == 'Courier' and st['dispatch']['ref'] == 'DTDC 123' and st['dispatch']['at'] > 0
        await shot('07-order-factory-dispatched')
        print('ok  factory: seen change -> ready -> dispatch punched')
        await logout()

        # ---- 10. store: received, payment, delivered
        await login('nishant', 'nishant1')
        await pg.click('.ocard')
        await pg.wait_for_selector('[data-act="recv"]')
        await pg.click('[data-act="recv"]')
        await pg.wait_for_selector('[data-act="deliv-open"]')
        await pg.click('#stickbar [data-act="pay-open"]')
        await pg.fill('#py-amt', '36790'); await pg.click('#py-mode [data-v="Cash"]')
        await pg.click('[data-act="pay-do"]')
        await pg.wait_for_function("!document.querySelector('#sheet .sheet') && document.body.innerText.includes('Cash')")
        t = await text(); assert 'बाकी\n₹0' in t and 'कुल मिला\n₹49,790' in t, t
        await shot('08-order-store-paid')
        await pg.click('[data-act="deliv-open"]')
        await pg.click('[data-act="deliv-do"]')
        await pg.wait_for_function("document.querySelector('.dhead').innerText.includes('Delivered')")
        print('ok  store: received, full payment, delivered')
        await pg.click('a[href="#/"]')
        await pg.wait_for_selector('[data-act="hist-load"]')
        await pg.click('[data-act="hist-load"]')
        await pg.wait_for_function("document.body.innerText.includes('पुराने Orders (1)')")
        await shot('09-home-history')
        print('ok  history list')
        await logout()

        # ---- 11. wrong password
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
