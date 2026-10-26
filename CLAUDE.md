# Deeva Orders — project notes for Claude

Made-to-order jewellery order system for **Deeva Diamonds** (lab-grown diamond store, VIP Road, Raipur). Owner: Mayuresh
Sisodiya (always "Sisodiya"; brand always "Deeva", never "Diva"). He talks in Hindi/Hinglish and is not a developer: he says
*what* should change, Claude does code, test and deploy, then explains in plain Hindi what changed and what he must do himself.
UI text is Hindi (Devanagari) mixed with common English words (Order, Approve, Factory, Stage, Dispatch, Payment).

**Completely separate from Team Kaam** (his task app): own GitHub repo, own Firebase project, own logins. Never share code
paths, Firebase projects or users between the two.

## The problem it solves

Before: store manager (Nishant) filled a paper "Custom Jewellery Order Form", then re-typed it into a WhatsApp message to
Darshana (owner, places orders with the factory), who re-sent it to the factory. Details got lost or changed on the way
(paper said 16 inch, WhatsApp said 18"). Now the order is entered once on the phone in front of the client, with
mandatory fields, and the same record goes to Darshana/Admin for approval and then to the factory, who updates stages.

## People & roles (users/{uid}.role)

| Role | Who | Can |
|---|---|---|
| `admin` | Mayuresh (first setup, real Gmail) — main admin | everything, all stores, every activity: approve → factory, query, edit any time, CAD OK, stage, dispatch, cancel/reopen, payments, final bill, Dashboard, Team, Stores, Deeva receipt signature |
| `subadmin` | Darshana — approvals are mainly hers | same as admin (`isAdmin()` = admin or subadmin), but cannot change an `admin` account or login, and cannot create admins |
| `store` | one manager per store (`users.storeId`), e.g. Nishant = VIP Road Raipur | only HIS store's orders: create, see client + price + payments, edit until approved, reply to queries, CAD OK / change, date/priority change any time, notes & media, payments + receipt photo, final bill, "Store पर मिल गया", Delivered, receipt PDF |
| `factory` | one factory person | only approved orders (`factoryVisible == true`), only product details + factory media + voice notes. **Never** client name/phone, price, payments, internal notes, queries. Updates stage, adds photos (CAD), dispatches (time punch) |

## Stores

`stores/{sid}` = `{name, city, address, phone, active, at}`. First setup creates the store "Raipur" (VIP Road address). Names are short ("Raipur", "Bilaspur", "Raipur A"); the
receipt prints "Deeva Diamonds — <store>".
Orders and their private doc carry `storeId` (+ `storeName` on the order). Admin can filter Orders and the Dashboard by store.
Team page: add store, one active store manager per store (UI blocks a second one), move a manager to another store.

## Order flow (orders/{id}.status)

`review` (store submitted) → `query` (admin asked; store edits + replies → back to `review`) → `factory` (approved; admin sets
`factoryDue` + `cadRequired`) → `dispatched` (factory punch) → `received` (at store) → `delivered`. `cancelled` from any active state (admin; can reopen).

Factory `stage` while `status == factory`: `new` → `received` → `cad` → `cad_approval` → `casting` → `filing` → `setting` →
`polish` → `qc` → `ready` → `dispatched`. If `cadRequired`, factory cannot go past `cad_approval` until store/admin sets `cad.ok`
("CAD OK" moves to `casting`; "बदलाव चाहिए" moves back to `cad`). Admin edits after approval set `factoryAck: false` → factory
sees a red "Order में बदलाव" box with the diff until it taps "देख लिया".

Order number: `DD-YYMM-NNN` (monthly counter `counters/{YYMM}`, incremented in the same Firestore transaction that creates
the order and its private doc; rules check `seq` against the counter with `getAfter`).

## Data model (Firestore)

| Path | Fields | Who |
|---|---|---|
| `config/admin` | `uid`, `at` | public get; created once at first setup |
| `users/{uid}` | `name`, `role`, `loginId`, `phone` (WhatsApp, 10 digits), `active`, `micLang`, `at`, `by`, `prevUid`/`replacedBy` | own get; active users read; admin writes; self may change `micLang` |
| `logins/{loginId}` | `email` (synthetic `<id>-<rand>@<projectId>.firebaseapp.com`), `uid` | public get (login lookup); admin list/write |
| `counters/{YYMM}` | `n` | staff |
| `stores/{sid}` | see Stores | active users read; admin writes |
| `config/brand` | `signData` (PNG data URL of the authorised signature), `signName` | active users read; admin writes |
| `pushTokens/{token}` | `uid, role, storeId, platform ('web'/'android'), at` | own create/delete; only the notification server reads |
| `orders/{id}` | `no, ym, seq, orderDay, createdAt, createdBy, createdByName, storeId, storeName, status, factoryVisible, stage, stageAt{stage: ms}, priority, deliveryDay, factoryDue, cadRequired, cad{ok,by,at,note}, factoryNote, factoryAck, factoryAckAt, approvedAt, approvedBy, query{open,text,by,at,reply,replyAt}, dispatch{at,by,byName,mode,ref,note}, received{at,by}, delivered{at,by}, cancel{at,by,reason}, spec{jtype, jtypeOther, qty, metalColor, purity, size, engraving, design, dia1Ct (or 'NA'), dia1Pcs, dia1Shape, dia1Color, dia1Clarity, dia1Cut, dia1Cert, dia2Ct, dia2Pcs, dia2Shape, dia2Color, dia2Clarity, gem{1,2}{Type, Color, Shape, Ct, Pcs}, stoneNote}, media{id: {kind image/video/audio, url, path, desc, voiceUrl?/voicePath? (voice note recorded for THIS photo/video), by, byName, at, size, stage?, deleted?}}, dispatch also has goldWt, diaCt, edited{spec_size: ms…}, log{key: {at, by, name, role, type, text}}, updatedAt, updatedBy` | staff; factory only when `factoryVisible` |
| `orders/{id}/private/info` | `storeId`, `client{name, phone, city}`, `price{est (= amount agreed with client), goldRateBooked yes/no, goldRate, calc{goldWt, goldRate, diaRate, dia2Rate, gemAmt, making (₹/g), other, gst + computed gold, dia, dia2, mk, gem, oth, value, gstAmt, final}, final (final bill), finalCalc}`, `payments{key: {amount, mode, day, note, receiptUrl?, by, name, at}}`, `internalNote`, `media{…}` (store-only media; receipts have `receipt: true`), `ack{accepted, remote, at, signData (PNG data URL), terms}`, `log{…}` (price/payment/client changes) | admin + that store's manager only |

Maps (not arrays) for media/payments/log so concurrent writers never overwrite each other; the adapter flattens nested
objects into dot paths on `update`. Media are soft-deleted (`deleted: true`).

Storage: `orders/{orderId}/{mediaId}.{ext}` (any active user reads; image/video/audio < 300 MB) and
`private/{orderId}/signature-*.png` (staff only). Images are compressed in the browser (max 1800 px, JPEG 0.84).

## Files

- `web/index.html` — the whole app (HTML + CSS + 2 scripts). Script 1: `window.DO_CONFIG` (Firebase web config, public) +
  adapter → `window.DO_BACKEND` (`auth`, `db`, `storage`). **The app only talks to `DO_BACKEND`.** Firebase compat SDK
  10.12.2 between `<!--FIREBASE-SDK-->` markers (the test harness swaps them for the fake). Script 2: the app — state `S`,
  hash routes (`#/`, `#/new`, `#/o/<id>`, `#/edit/<id>`, `#/team`, `#/account`), `render()` → `doRender()`, `patch()` keeps
  typed text/focus, one delegated click handler on `data-act`, bottom sheets (`openSheet`). The order form is rendered once
  per visit (`renderForm`), values live in `F`, a draft is kept in localStorage `do.draft`.
  `makePicker()` = photo/video/voice-note uploader (MediaRecorder for voice notes). `micStart()` = speech-to-text on every
  text field (Web Speech API in Chrome; in the APK `DeevaApp.listen()` → Google voice typing → `window.__doSpeech`).
- `web/config.js` — `self.DO_CONFIG` (Firebase web config + `vapidKey`), shared by the page and `sw.js`.
- `web/sw.js` (app-shell cache, never touches Firebase traffic; imports `config.js` + firebase-messaging for closed-app
  notifications), `web/manifest.webmanifest`, `web/icons/*` (from the official Deeva logo: gold mark on Deeva green).
- Receipt PDF: `receiptHtml()` builds an A4 page (logo, client, store, product rows, estimate/final bill, payments, terms,
  client signature, drawn Deeva seal + authorised signature) → html2canvas 1.4.1 + jsPDF 2.5.1 (cdnjs, loaded on demand) →
  `sharePdf()`: APK `DeevaApp.sharePdf(base64)` (Downloads + share sheet), else Web Share with file, else download.
- Activity (`#/activity`, admin + sub admin): every log entry of every order (main + private logs) newest first,
  filters store / who (Store, Admin/Sub Admin, Factory, Payments) / search; uses the dashboard load + live open orders.
  Store managers are shown as "Name · Store" (`personName()`), also inside log entries.
- Dashboard (`#/dash`, admin + sub admin): loads all orders + `collectionGroup('private')`; KPI tiles, 3 SVG line charts
  (orders / avg making days approve→dispatch / business ₹ per month, hover crosshair + table view), pipeline bars,
  store-wise table, top items. Filters: store, 6/12 months/all. Chart colours `--chart` (#1d7f4b light, #bf8a2a dark).
- `functions/index.js` — notification server (Node 22, 2nd gen, asia-south1): `orderCreated` → admins; `orderUpdated` →
  query → store, reply → admins, approved → factory + store, CAD approval → admins + store, CAD OK/change → factory,
  `factoryAck` false (edit / date / priority) → factory, factory notes → admins + store, staff notes → factory,
  dispatched → admins + store, delivered → admins. Never sends client name / phone / price.
- `android/` — thin WebView shell (AGP 8.5.2, Gradle 8.9 in CI, firebase-messaging; the google-services plugin is applied
  only when `android/app/google-services.json` exists). `MainActivity.java` loads `APP_URL`, bridge
  `window.DeevaApp`: `isApp, isForeground, notifyUser, copy, listen(lang), sharePdf(b64, name, text), requestPushToken() → window.__doPushToken, retry`; file chooser with camera; grants mic to
  the page for voice notes; Android back closes open sheets via `window.__doBack()`. Web changes reach APK users without a new APK.
- `firestore.rules`, `storage.rules`, `firestore.indexes.json` (factoryVisible + status index; the app falls back to a
  one-field query while the index is missing), `firebase.json`, `.firebaserc`.
- `.github/workflows/pages.yml` (site), `apk.yml` (APK release, needs secrets `DO_KEYSTORE_B64` / `DO_KEYSTORE_PASS`),
  `firebase.yml` (rules + storage rules + indexes + notification functions, needs secret `FIREBASE_SERVICE_ACCOUNT` with
  Owner role and the Blaze plan; without it the owner pastes rules in the console and there are no closed-app notifications).
- `tools/make_demo.py` — builds the fake-data demo page published as a claude.ai artifact.
- `tools/fake-backend.js` + `tools/test_flow.py` — in-memory fake + Playwright end-to-end test of the whole flow
  (setup → logins → order with photo + voice note + calculator + signature → query → reply/edit → approve → factory view
  without client/price → CAD → admin edit alert → dispatch → payment → delivered). Run `python3 tools/test_flow.py [shots_dir]` → `PASS`.

## How to make a change

1. Attach the repo (`add_repo deevadiamonds/deeva-orders`, push), clone, read this file.
2. Edit `web/index.html` (+ rules if data/permissions change; `android/` only for shell changes). Keep UI and rules in sync,
   Hindi copy short, phone width 400 px without sideways scroll, light + dark tokens.
3. Run `python3 tools/test_flow.py` — extend it for new behaviour. Must print `PASS`.
4. Commit, push to `main`, watch the Actions run. Tell the owner in Hindi what changed (the app updates itself on reopen).
