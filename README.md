# OrderFlow Sentinel + ShopEase

Two local React applications share a FastAPI/SQLite backend. The supplied navy/gold HTML is preserved in `docs/reference.html`; the applications use reusable React components, bundled Inter fonts, local SVG icons, installed Tailwind CSS and Recharts.

Everything involving payments, refunds, stores, inventory partners, riders, notifications and cold-chain delivery is a **local simulation**. No real charge, SMS, delivery or external paging service is connected. No GPU, cloud service, API key or paid service is required.

## Start on Windows

Requirements: Python **3.11**, Node.js **20.19+ or 22.12+** (verified here with 24.14), npm, and PowerShell. `uv` is optional. Install dependencies once:

```powershell
cd "<your path>\orderflow-sentinel"
.\scripts\setup.ps1
.\scripts\start.ps1
```

If the machine blocks local PowerShell scripts, run the manual commands below instead of changing system policy. Initial dependency installation needs internet access; normal operation after setup works offline. Optional explanation generation is disabled without both Gemini environment variables.

Open these exact **localhost** URLs, in independent tabs in the same browser profile:

| Application | URL |
|---|---|
| ShopEase | [http://localhost:5173](http://localhost:5173) |
| Sentinel Console | [http://localhost:5174](http://localhost:5174) |
| Backend health | [http://localhost:8000/api/health](http://localhost:8000/api/health) |
| Interactive API docs | [http://localhost:8000/docs](http://localhost:8000/docs) |

Set a private `OPERATOR_PASSWORD` in a root `.env` copied from `.env.example`. If it is unset locally, startup generates a credential in the ignored `backend/data/operator-password.local` file; read it on your machine to sign in. Hosted startup requires the private environment variable. Console login creates a random, persistent 12-hour bearer session. The visual switcher is a convenience link, not authentication. Keep one backend worker and one instance of the backend. Never publish credentials or paste them into chat.

`start.ps1` starts hidden service processes, prints URLs, writes logs into `work/logs`, and keeps the parent PowerShell session open. Ctrl+C stops its child services. It refuses occupied ports. **Normal startup preserves the database and booking sequence.**

Manual startup, in three terminals from the project root:

```powershell
# Terminal 1
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1

# Terminal 2
npm run dev:shop

# Terminal 3
npm run dev:console
```

Manual setup without uv:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm ci --no-bin-links
.\.venv\Scripts\python.exe -m backend.train.train_models
```

Explicit Node entrypoints in npm scripts avoid Windows symlink/admin requirements. Python dependencies are fully pinned in `backend/requirements.txt`; `requirements.in` records direct dependency ranges. Frontend versions are pinned by `package-lock.json`.

## Use the applications

ShopEase has 20 database-backed products, search, categories, cart, validated checkout, a simulated payment choice, private My Orders, live tracking, and customer acceptance of proposed changes. Prices are integer paise; submitted totals are not accepted. A successful accepted booking clears the cart even if the initial service result is a failure requiring recovery.

Sentinel has database-derived KPIs, initial-versus-recovered outcomes, P1-first incident sorting, candidate-specific risk, real model outputs, notes attached to actions, a chronological audit, feedback, persisted jobs, filtered resolution history/CSV, gateway circuits, analytics, settings and actual background retraining. The Orders screen advances simulated fulfilment one stage at a time. Incident resolution never marks a parcel delivered.

Default bookings **1 and 3 succeed; 2, 4 and 5 fail initially** in each repeating block. The persistent sequence is allocated atomically only for validated, stock-reservable bookings. Repeating an idempotency key returns the original result. Recovery attempts do not consume booking numbers. All ten errors rotate across failing bookings; weighted selection, simulator disable, failing-position selection and explicit one-time overrides are supported.

The console demo modal uses the same booking service. Both tabs share a private localhost customer-session cookie so console-created demo orders appear in ShopEase. Do not mix `localhost` and `127.0.0.1` in browser URLs; they are different cookie hosts and the configured CORS/socket origins use localhost.

## Five-order judge demonstration

Use a separate database; never reset normal data:

```powershell
# Stop an existing backend before switching databases.
.\.venv\Scripts\python.exe scripts\demo_data.py
.\scripts\start.ps1 -Demo
```

The data command refuses to overwrite an existing demo file. For another fresh run, supply a different `--database backend/data/judge-2.db` path and set `DATABASE_URL=sqlite:///backend/data/judge-2.db` in the backend terminal. `start.ps1 -Demo` reuses `judge-demo.db`; it never clears it. See `docs/JUDGE_DEMO.md` for exact inputs and recovery steps. `--book-five` creates labelled scripted demo bookings for inspection; it is optional and unsuitable if you want to place the five bookings interactively.

## Verification

```powershell
.\scripts\test.ps1
npm run typecheck
# With fresh isolated backend and both Vite apps running:
node node_modules\@playwright\test\cli.js install chromium
npm run test:browser
```

The browser test requires an empty dedicated database (next sequence 1); it does not reset data. It places five real customer bookings, watches the console in a second tab, executes reconciliation/refund and substitute acceptance, visits all screens, downloads CSV, runs actual retraining, checks browser errors, and captures desktop/mobile screenshots. `scripts/restart_verification.mjs` provides a separate process-restart check. See `docs/VERIFICATION.md` for measured results and commands used in this workspace.

## Models and boundaries

Isolation Forest and two XGBoost models train on approximately 5,000 reproducible synthetic observations, with separate train/validation/test sets. Before training, the engine uses a labelled conservative rule fallback with unavailable probabilities and worst-case policy uncertainty. Model artifacts, feature schemas, seeds, measured metrics and version pointers live in `backend/data/models`. Failed training preserves the previous usable pointer. Operator approvals are preferences, **not verified outcome labels**, and are excluded from training.

The synthetic failure target is an initial service fault remaining unresolved **five minutes after observation**, assuming the synthetic normal recovery policy. Class confidence is the maximum predicted error-class probability, not a guarantee that an action is safe. See `docs/MODEL_EVALUATION.md` and the generated JSON reports.

The app is a laptop demonstration, not a production commerce platform. Access boundaries assume a trusted local machine. There is no production identity provider, HTTPS deployment, external provider integration, independently verified real-world training data, or production-scale queue. Gemini explanation prose is optional and cannot select or execute actions; it receives no customer phone/address. See `docs/LIMITATIONS.md`.

## Project map

```text
backend/                 FastAPI, SQLAlchemy tables, validation, monitoring
  engine/                Detection, models, forecast, priority, risk, policy
  services/              Atomic booking, recovery worker, simulated adapters
  data/playbook.json     Ten exact-lookup incident playbooks
  train/                 Reproducible CPU-only model training
  tests/                 Backend, concurrency, payments, models and state tests
shop-frontend/           Customer React + Vite + TypeScript application
console-frontend/        Operator React + Vite + TypeScript application
shared/                  Design tokens, components, API hooks and types
tests/browser/           Playwright application and reference checks
scripts/                 Windows setup/start/test and separate demo commands
docs/                    Architecture, demo, evaluation, structured evidence
```
