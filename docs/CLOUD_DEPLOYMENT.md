# Cloud deployment

The hosted configuration serves both built React applications from one FastAPI process:

- `/shop/`: ShopEase
- `/console/`: Sentinel Console
- `/api/health`: readiness
- `/ws/console` and `/ws/order/{id}`: native secure WebSockets

`Dockerfile` builds both TypeScript applications using their correct URL base paths, installs the CPU-only Linux XGBoost package, and starts one Uvicorn worker on `0.0.0.0:$PORT`. Runtime images exclude source-control metadata, secrets, customer databases, logs, dependencies from the host, and test artifacts.

Local Windows startup continues to use SQLite by default. A hosted PostgreSQL URL in `DATABASE_URL` selects psycopg and PostgreSQL transaction-level advisory locking, preserving the same serialized booking/payment/recovery contract. Tables and seed products are created idempotently at startup. Existing data is never reset.

Runtime configuration:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Private PostgreSQL connection string, supplied only as a hosting secret |
| `OPERATOR_PASSWORD` | Private operator credential; required in production |
| `ENVIRONMENT` | `production` |
| `WORKER_POLL_SECONDS` | Hosted monitor interval, e.g. 2 seconds |
| `RENDER_EXTERNAL_URL` | Render-provided HTTPS origin, automatically allowed for HTTP and WebSockets |

Frontends use same-origin API and secure WebSocket URLs in production. Switcher links navigate between `/shop/` and `/console/`; the customer session cookie is shared. Local development still uses its original three ports.

Training jobs save successful model bundles, reports and active-version metadata in the persistent database. On restart the last successful artifact is restored before recovery starts, so ephemeral container storage does not erase retrained models. Shipped baseline models remain available before the first retraining.

Render Free can sleep when idle and has resource/usage limits. Deadline monitoring pauses while the process is asleep; restart-safe jobs resume, and warnings after the deadline are marked late. Free hosting is for the demonstration, not an always-on operational SLA. Durable records are held separately in the approved free Neon database. No paid plan or real payment/SMS/delivery integration is enabled.

Retrieve the production operator credential from the service's private environment settings in the Render Dashboard. Do not put it in Git, client bundles, screenshots or chat.

## Pre-deployment verification

The revised backend suite passed 60 tests, including anonymous-contact validation. Both frontend production builds passed. A same-origin production preview verified private operator login, both applications, live sockets, actual timeout recovery, mobile width and zero console errors (`production-preview-verification.json`). The full browser and process-restart checks also passed after contact anonymization; see `DEMO_PRIVACY.md`.

The newly created cloud database passed isolated-schema checks for twenty bookings with exactly twelve initial failures, concurrent booking sequences, idempotency, operator approval, filtered CSV/date queries, reconciliation, pending/completed refunds and restart sequence persistence (`cloud-postgres-verification.json`). No application customer schema was reset during these checks.

These are pre-deployment results, not a claim that a public service is live. Hosting is verified only after its deploy reaches the live state and the public URLs pass the same browser flow.
