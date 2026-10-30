# Verification evidence

Verified locally on **30 October 2026** with Windows, Python **3.11.15**, Node **24.14.0**, Vite **7.3.7**, CPU-only XGBoost and Playwright Chromium **156**. Tests use isolated databases and never reset normal startup data.

The verified story is: customer product selection → validated checkout → transactional booking and simulator → persistent incidents/models/risk/jobs → live operator investigation → reviewed recovery/refund → customer updates/acceptance → audit/history/analytics.

## Results

| Check | Result | Evidence |
|---|---|---|
| Backend tests | **54 passed**, 12.66 seconds | `pytest-results.xml` |
| TypeScript | Both applications passed | Result recorded in this verification report; regenerate with `npm run typecheck` |
| Production builds | Both applications passed | Result recorded in this verification report; regenerate with `npm run build` |
| Playwright customer/operator flow and reference captures | **2 passed**, 25.3 seconds | `browser-results.json` |
| Actual backend process restart | Passed | `restart-results.json` |
| Windows startup | Three hidden services launched through `scripts/start.ps1`; health and both app URLs served | `work/logs` in the running workspace; URLs below |
| Separate demo-data command | Passed, fresh isolated path; refuses overwrite by design | `scripts/demo_data.py` |
| Model training/loading/prediction | Passed; background browser-triggered training finished DONE | `model-evaluation.json`, `MODEL_EVALUATION.md`, backend model tests |
| Desktop/mobile appearance | Inspected against supplied HTML | Local `docs/screenshots/`, reproducible with browser tests |

The only backend test warning is a non-failing upstream Starlette/httpx deprecation notice. Browser test logs include Node colour-environment/npm notices; final app assertions found **zero console errors, zero uncaught page errors, and zero requests to external hosts** during normal app operation. The reference HTML screenshot test separately allows its original CDNs.

Generated `.log` files and screenshots remain local and are excluded from current version control. Structured test reports, evaluation results and this verification record are retained. After anonymization, the revised suite passed 60 backend tests in 15.12 seconds and both browser tests in 27.2 seconds. The XML report above records the original 54-test run. See `DEMO_PRIVACY.md` for the screenshot-publication restriction.

## Backend coverage

| Requirement | Verified behaviour |
|---|---|
| Default twenty bookings | Exactly 12 initial failures, positions 2/4/5 in each block; initial outcome retained |
| Concurrent bookings | Twenty concurrent bookings have unique IDs and sequence 1–20; same-key concurrent submissions create one order |
| Validation/idempotency | Invalid fields, supplied total, insufficient stock and duplicate requests consume no extra sequence/override |
| Ten incident types | All ten enter their matching playbook workflow; concrete service-handler tests cover retries, token refresh, store transfer, rider, payment, address and stock acceptance |
| Exact risk/policy | Weighted contributions agree with total; 0.70, 0.90, 30 and 60 boundary tests include values just below/above; action changes recalculate no_undo |
| Critical cart | Mixed insulin/grocery cart remains P1 after recovery; medicines/infant substitutions disabled |
| Recovery scheduling | Persistent nonblocking retry jobs run; 1s/2s/4s scheduling and maximum three attempts; exhaustion raises P1 and escalates |
| Gateway circuit | Fifth rolling-minute failure opens; 30-second cooldown permits half-open probe; success closes and failure reopens |
| Unknown payment | Cannot gateway-switch/recharge/refund prematurely; reconciliation is separate from confirmation; repeated effects remain idempotent |
| Refund | Request stays PENDING with incident REFUND_PENDING; settlement changes to COMPLETED/REFUNDED; COD blocked; stock released once |
| Approval/AI/operator races | Same-key repeated approvals log one effect; stale operator and AI recovery transactions cannot duplicate resolution/payment effects |
| Offers/notifications | Notify/escalate/offer do not resolve underlying faults; customer acceptance checks stock/price; a new slot alone cannot fix stock/address errors |
| Stock concurrency | One remaining unit allows one booking, seven competing requests fail; stock stays nonnegative; cancellation release idempotent |
| Restart | Persistent pending job resumes; counter/stock/payment/operator session survive actual process restart; both browser sockets reconnect and snapshot |
| Deadlines | Timestamp-driven pre-deadline warning, deduplication across repeated ticks/reinitialisation, late-after-deadline warning labelled late |
| Forecast | Uses five measured completed simulated-delivery durations; fewer than five uses explicit fallback |
| Access | Operator endpoints reject unauthenticated requests; another customer session cannot read a private order; customer WebSocket strips internal risk data |
| History/CSV | Matching server-side filters yield the same nonempty result set in JSON and CSV |
| Feedback/models | Preferences remain separate from ground truth; training yields measured artifacts and predictions; deliberate training failure preserves previous usable pointer |
| State transitions | Cannot skip delivery stages; incident resolution leaves UNFULFILLED; server flush invariants validate order/fulfilment transitions |

## Browser walkthrough actually exercised

Five ShopEase checkouts (noncritical combo, combo, combo, insulin, combo) generated success/timeout/success/unmatched-debit/stock outcomes in one five-booking block. Sentinel updated in a second tab without refresh. Timeout resolved through the engine's actual recovery job, preserving UNFULFILLED. Insulin required manual CHECK_PAYMENT; payment-attempt count remained one. Confirmed REFUND showed PENDING in ShopEase before the simulated settlement marked COMPLETED. Stock substitute remained unresolved until ShopEase accepted the equal-price change. Both applications agreed on the resulting state.

The test visited Orders, Resolution History, Gateway Health, Analytics and Settings; downloaded a real CSV; started and waited for an actual background retraining job; checked that cart quantity returned to zero; blocked external network requests during normal operation; and checked document width at 390×844. Desktop screenshots use 1440×1000. A separate reference test captured the original storefront and console at both sizes.

Actual process-restart verification starts a fresh isolated backend, books an automatic timeout with two simulated retry failures, terminates and starts the backend again against the same SQLite file, observes reconnecting/live in both tabs, and waits for recovery. It confirms attempt_count=3, payment attempts=1, next booking sequence=2, reserved product stock=99, and fulfilment=UNFULFILLED. See `restart-results.json`.

## Visual inspection

Inspected the original and implementation storefront/dashboard, checkout, incident detail, refund confirmation, pending-refund customer view, acceptance view, resolution history, and mobile tracking/incident views. The navy/gold palette, Inter typography, three-column product catalogue, white cards/borders, operator sidebar, KPI hierarchy, detail/risk/audit layout and convenience switcher are retained. Mobile navigation becomes horizontally scrollable; cards stack and tables scroll inside their containers.

An initial browser run found 403 responses for fonts outside Vite's frontend folder. The allowlist now includes only each frontend, shared source and installed dependencies. Final runs load local Inter fonts, have no external asset dependency, and report no browser errors. A restart check was rerun after development hot-reload activity had stopped; the clean actual-process restart passed.

## Reproduce

From the project root:

```powershell
.\scripts\test.ps1
npm run typecheck
# With an empty isolated DB on 8000 and apps on 5173/5174:
npm run test:browser
# Stop that backend, leave the two frontend servers running:
node scripts\restart_verification.mjs
```

Normal app URLs: ShopEase `http://localhost:5173`, Sentinel `http://localhost:5174`, backend health `http://localhost:8000/api/health`. The verified Windows launcher is `scripts/start.ps1`. Live optional Gemini, real external providers, other browser engines and production deployment were not tested; see `LIMITATIONS.md`.
