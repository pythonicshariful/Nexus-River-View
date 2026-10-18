# Android App — Build Prompt Pack

Give this file to an Android-capable coding assistant (Claude Code, Gemini in Android
Studio, or a fine-tuned Android model) together with `docs/API.md`. It is written as a
set of sequential prompts so the app can be built in reviewable stages.

---

## Prompt 0 — Project brief (paste into a new agent)

> You are building an Android client for **Nexus River View**, an accounting and
> property-receivables system for a real-estate developer in Bangladesh.
>
> The backend is a Flask API documented in `docs/API.md`, hosted at
> `https://accounts.pythonicshariful.tech/api/v1`.
>
> Build a native Android app in **Kotlin + Jetpack Compose**, following Material 3,
> using the architecture below. The app is for the company administrator and office
> staff — it is an internal operations tool, not a consumer app.
>
> Hard requirements:
> - Bearer-token auth; token in EncryptedSharedPreferences.
> - Every write action prompts for the admin password in a confirm sheet and sends it
>   as `X-Admin-Password`. Never store it.
> - Money is `BigDecimal` end to end; format with `NumberFormat` for `bn-BD` / `৳`.
> - The app must never compute debit/credit postings — it sends business fields and
>   displays what the server returns.
> - Offline: cache the last successful read responses in Room and show a banner when
>   serving stale data. All writes require connectivity.
> - All dates travel as `YYYY-MM-DD`; display as `dd MMM yyyy`.
>
> Architecture:
> - Kotlin 2.x, Compose, Material 3, Navigation Compose.
> - MVVM + Repository. Hilt for DI. Retrofit + OkHttp + kotlinx.serialization.
> - Room for cache. WorkManager for background dashboard refresh.
> - Coil for receipt images. Paging 3 for long lists.
> - Min SDK 26, target latest stable. R8 enabled in release.
>
> Package name: `tech.pythonicshariful.nrv`.

---

## Prompt 1 — Design system

> Create the Compose theme for the app, matching the web redesign.
>
> **Colors** — dark navigation rail, light data surfaces:
> - `navBg = #0A101F`, `navSurface = #111B30`, `navLine = #1C2740`
> - `canvas = #F4F6FA`, `surface = #FFFFFF`, `surfaceAlt = #F8FAFC`
> - `line = #E5E9F1`, `lineStrong = #D3DAE6`
> - `ink = #0F172A`, `inkSecondary = #334155`, `muted = #64748B`
> - `brand = #2563EB`, `brandDark = #1D4ED8`, `brandSoft = #EFF6FF`
> - `success = #059669`, `danger = #DC2626`, `warning = #D97706`, `info = #0284C7`
>
> **Typography**: Inter for body/labels, Outfit for money figures and headings.
> Money uses tabular figures (`FontFeature("tnum")`), right-aligned.
>
> **Shape**: 10dp for controls, 14dp for cards, 18dp for sheets.
> **Elevation**: near-flat — 1dp hairline borders instead of shadows.
>
> Build reusable composables:
> `StatCard(label, value, sublabel, tone, icon)`,
> `SectionHeader(eyebrow, title, actions)`,
> `DataTable(columns, rows, numericColumnIndices)`,
> `AmountText(amount, positive/negative/neutral)`,
> `StatusPill(text, tone)`,
> `ConfirmAdminSheet(title, onConfirm(password))`.
>
> No emoji as icons. Use Material Symbols / `androidx.compose.material.icons`.

---

## Prompt 2 — Networking & auth

> Implement the network layer against `docs/API.md`:
>
> 1. `ApiService` with Retrofit: all endpoints, `@Header("Authorization")` injected by
>    an OkHttp interceptor from the token store.
> 2. `AuthInterceptor` — adds bearer token; a second `AdminPasswordInterceptor` is not
>    used; the admin password is passed per-call from the confirm sheet.
> 3. `ApiResult<T>` sealed class: `Success`, `Error(code, message, field)`.
> 4. Parse the `{ data, meta }` and `{ error }` envelopes with a custom serializer.
> 5. Map status codes: 401 → clear token and navigate to login; 403
>    `admin_password_required` → reopen the confirm sheet; 409 → show conflict message.
> 6. Token storage in `EncryptedSharedPreferences` (`MasterKey` in Android Keystore).
> 7. `AuthRepository`: `login`, `me`, `refresh`, `logout`.
>
> Add an OkHttp `HttpLoggingInterceptor` limited to `BuildConfig.DEBUG`.

---

## Prompt 3 — Screens (build in this order)

> Each screen: `ViewModel` exposing `UiState` (`Loading`, `Content`, `Empty`, `Error`),
> pull-to-refresh, and a stale-data banner when served from Room cache.
>
> 1. **Login** — split-feel layout: brand block with app name and a tagline, username
>    field, password field with visibility toggle, primary "Sign in" button with loading
>    state. Map 401 to an inline error. Remember username only.
> 2. **Dashboard** — the six KPI stat cards in a 2-column grid (project value,
>    collected, due, overdue, bank balance, cash in hand), a 6-month cash-flow chart
>    (MPAndroidChart line chart, income green / expense red), and quick actions
>    (New Voucher, New Contra, Add Payment).
> 3. **Ledger hub** — the bottom navigation: Dashboard, Vouchers, Cash, Banks, More.
>    "More" opens a grouped list matching the web sidebar.
> 4. **Vouchers** — list with filter chips (All / Debit / Credit), search, date range,
>    and a floating action button for new voucher. Detail shows amounts, party/customer,
>    category and status.
> 5. **New Voucher** — form: type segmented control, date picker, customer or party
>    picker (searchable bottom sheet), total, amount paid, payment method, bank picker
>    when Bank, category, description. Show the computed due live. Confirm with the
>    admin sheet before `POST /vouchers`.
> 6. **Customers** — searchable list grouped by director, showing due amount as the
>    primary figure. Detail: profile, stat row (total, paid, due), installment progress
>    bars, transaction timeline, and "Record Payment".
> 7. **Record Payment** — amount keypad, source selector (Cash / Petty Cash / Bank),
>    optional installment picker, remarks, attach receipt photo (Coil + camera),
>    admin confirm. After success, show updated due immediately.
> 8. **Cash (petty cash)** — date-filtered list with running totals in a sticky header;
>    new entry sheet for Income/Expense.
> 9. **Banks** — account cards with balance, ledger screen with credit/debit rows and a
>    "new entry" sheet.
> 10. **Parties** — list with balance color coding (red = you owe, green = advance);
>     detail with ledger timeline and "Add Bill / Add Payment".
> 11. **Reports** — tabbed: Trial Balance (with a prominent balanced/unbalanced banner),
>     P&L, Balance Sheet, Cash & Bank Flow, Money Flow. Date range pickers. A share
>     button using `FileProvider` + the Print framework (`PdfDocument`) to export.
> 12. **HR** — employees list, attendance sheet (date, status chips, in/out time per
>     employee), leaves with approve/reject, salary sheet with "Generate" and
>     "Mark paid".
> 13. **Tasks** — today's todos with swipe-to-complete.
> 14. **Settings** — server URL (default the hosted one), about, sign out, and a
>     diagnostics screen showing the last API error.

---

## Prompt 4 — Data layer & offline

> - Room entities mirroring the API DTOs, with fields exactly as documented.
> - A `*RemoteMediator` or simple "write-through on success" cache: every successful
>   GET writes to Room; on network failure read the cached rows and set
>   `isStale = true`.
> - Writes are never queued. If offline, disable write buttons and show "Requires a
>   connection".
> - WorkManager: refresh `/dashboard` every 6 hours when on Wi-Fi, and on app start.
> - Store monetary values in Room as `TEXT` (BigDecimal), not `REAL`.

---

## Prompt 5 — Security & release checklist

> - `android:usesCleartextTraffic="false"`; HTTPS only.
> - No admin password in logs, saved state, or crash reports. Sanitize
>   `HttpLoggingInterceptor` to redact `X-Admin-Password` and `Authorization`.
> - Disable screenshots on sensitive screens (`FLAG_SECURE`) for Reports and
>   Settings.
> - ProGuard rules for kotlinx.serialization and Retrofit.
> - Sign release builds with the company keystore; store it outside the repo.
> - Play Store is optional — if distributing internally, ship an APK via the company
>   site and document the checksum.

---

## Prompt 6 — Tests

> - Unit tests for every ViewModel with a fake repository.
> - `MockWebServer` tests for the API client: success envelope, error envelope, 401,
>   403 `admin_password_required`, pagination meta.
> - A money-formatting test asserting `৳1,250,000.00` for `1250000`.
> - Compose UI tests for login, new voucher validation, and the admin confirm sheet.

---

## Acceptance criteria

The build is done when:

1. An admin can sign in and see a dashboard matching the server totals.
2. A payment recorded on the phone appears in the web app's customer ledger, voucher
   list and trial balance with balanced entries.
3. Every destructive action is gated by the admin password sheet.
4. Killing the network shows cached data with a clear stale banner, and writes are
   disabled rather than failing silently.
5. Amounts never show floating-point artefacts (e.g. `0.30000000000000004`).
6. Tokens live only in encrypted storage, and 401 returns the user to login cleanly.
