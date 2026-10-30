# Architecture, state and operational contract

One Uvicorn worker serves synchronous FastAPI API handlers, native asynchronous WebSockets, one persistent-job/deadline loop and optional asynchronous training. SQLAlchemy uses SQLite WAL, foreign keys, a 30-second busy timeout and **BEGIN IMMEDIATE** for every mutation. SQLite serializes booking, operator, worker, stock and refund effects. No Redis/Celery/cloud worker is needed.

## Booking and processing

Validated request → idempotency lookup → validate catalogue/stock → reserve units → allocate sequence → consume override (if any) → simulate service response → detect signals → XGBoost class/failure predictions and Isolation Forest → moving-average forecast → highest rule priority → candidate action → action-specific risk → restricted decision → persistent recovery job or operator queue → playbook explanation → audit/event rows → commit.

Idempotency scopes include the customer session and operation. Reusing a key with different input returns 409. Order creation, customer acceptance, operator actions, notes and fulfilment use persisted response records. Refunds additionally have a unique order constraint, as do payments. The demo endpoint has its own outer idempotency record so changing block position cannot change a duplicate demo request's generated input.

Sequence allocation and stock reservation share the same transaction. Validation failures, insufficient stock and duplicates consume no number and do not consume a forced error. Default `position = ((booking_seq - 1) % 5) + 1`. Default failing positions `[2,4,5]` produce exactly three **initial** failures per block; later automatic recovery does not alter that initial result. Rotation traverses all ten incident types. Seeded weighted selection is deterministic in `seed + booking_seq`. Explicit error overrides take precedence, including when the simulator is disabled, and may break the default count; they are consumed once and marked on the order/audit. COD converts impossible unmatched-debit/double-charge fixture signals into a known no-debit payment-decline workflow.

## Separate state dimensions

| Dimension | States and meaning |
|---|---|
| Order | PLACED, PAYMENT_PENDING, CONFIRMED, FAILED, DELAYED, AUTO_FIXING, WAITING_APPROVAL, MANUAL_REVIEW, RESOLVED, CANCELLED, REFUNDED |
| Fulfilment | UNFULFILLED → PACKED → OUT_FOR_DELIVERY → DELIVERED |
| Payment | NOT_REQUIRED (COD), DECLINED, NOT_DEBITED, DEBIT_UNKNOWN, CAPTURED |
| Refund | No record → PENDING → COMPLETED |
| Incident | OPEN, ESCALATED, REFUND_PENDING, RESOLVED |
| Recovery job | PENDING → RUNNING → DONE / FAILED / CANCELLED |

The executable order-transition graph is in `backend/state.py`. A SQLAlchemy before-flush invariant rejects unknown states and illegal transitions. Every service routes transitions through authenticated, validated workflows. PLACED can enter payment/triage/confirmed states. Recovery, approval and manual states may transition among review/recovery/payment/confirmation or cancel when prerequisites permit. CONFIRMED/RESOLVED may re-enter review for a newly detected issue. **CANCELLED only transitions to REFUNDED; REFUNDED is terminal.** Refund requests move orders to CANCELLED while the refund and incident remain pending. Confirmed simulated settlement moves the refund to COMPLETED, order to REFUNDED and incident to RESOLVED.

Fulfilment advances exactly one stage, only for confirmed/resolved orders with the matching version. Recovery resolves an incident to a confirmed order and leaves fulfilment alone. Delivery records an actual timestamp for simulated delivery-duration history. Delivery does not imply a second stock deduction: reservation units were already deducted at booking. Cancellation/refund releases reserved stock once. Delivered units are consumed rather than released. Medicines and infant formula cannot be substituted.

## Action prerequisites and concurrency

Action lists are calculated server-side with an enabled flag and reason. Submission rechecks current state, selected-action risk, model confidence, explicit restrictions and entity version in the same write transaction. Manual incidents cannot use the approve endpoint. Direct explicit operator execution is the reviewed manual path. REFUND and CANCEL require the confirmation flag and an operator actor. Unknown debits cannot switch gateways, generate a new payment or cancel until reconciliation. A refund requires a captured debit and no prior refund. COD cannot receive a refund. CHECK_PAYMENT only reconciles; a separate CONFIRM_ORDER or confirmed REFUND is required. NOTIFY_CUSTOMER/ESCALATE never resolve the fault.

Store reassignment uses a clearly labelled local same-item backup-hub fixture and always requires at least operator approval, even if numeric risk is low. Equal-price grocery substitutes are available only between PROD-109 and PROD-120, and acceptance rechecks stock and price atomically. The original reservation is released and the accepted substitute reserved. A slot/address proposal is also pending until accepted; the address adapter only looks up the explicit 560039 → 560038 demo pickup desk. It never guesses a residence.

Operator recovery changes cancel pending stale jobs and increment order/incident versions. Workers compare expected order version before executing. Each retry increments attempt_count, never booking_seq, and records its outcome. Persistent due times implement **1s, 2s, 4s** waits with a maximum of three attempts. Exhaustion escalates and raises priority to P1. The UI's retry-failure fixture is explicit local simulation input, not a model output.

## Circuit breaker

Gateway errors are stored as UTC timestamps. Five technical failures in a rolling 60-second window open the circuit. OPEN blocks service attempts. At 30 seconds, the monitor makes the circuit HALF_OPEN; one transaction can claim its controlled probe. Success closes and clears error history; failure reopens with a new cooldown. Simulator controls never cosmetically toggle real connectivity. The gateway screen's probe buttons are explicitly local demo probes and only work in HALF_OPEN. Latency/success rate are unavailable because there is no real provider telemetry.

## Realtime and restart

Events are durable rows in the same transaction as entities. Socket readers only see committed rows. Each has id, UTC timestamp, entity version, order/incident IDs and event type. Console sockets require a live operator session and an allowed Origin. Order sockets require an unguessable tracking token and allowed Origin. Customer events contain only safe order invalidations; internal scores, explanation details and incident IDs are removed.

On every connection, `snapshot_required` establishes a current cursor and prompts HTTP refetch. Clients reconnect using exponential backoff, ignore duplicate IDs and older entity versions, and replace snapshots rather than append duplicate rows. Browser stream indicators come from socket lifecycle. Periodic HTTP snapshots also refresh listings. Persistent pending jobs, deadlines, sequence and circuit state survive restart. Interrupted training is marked FAILED at next startup; previous usable artifacts remain intact. Training jobs are not silently reported as completed.

## Forecasts and deadlines

Delivery baseline = arithmetic moving average of the last 20 completed simulated delivery durations, once at least five exist. Until then it is an explicitly labelled **35-minute fallback**. Error penalties in `engine/forecaster.py` range from 2 to 16 minutes and are documented local assumptions. Predicted delay = max(0, baseline + penalty − promise duration). Customer tracking drops the unresolved-error penalty after resolution. This delivery estimate is separate from incident-repair time, which is unavailable until measured resolution.

Every 0.4-second monitoring tick compares persistent created/promised timestamps with `created_at + alert_fraction × (promised_by − created_at)`. Default fraction .70 yields minute 28 of a 40-minute promise. Notification uniqueness `(order_id, kind)` deduplicates deadline warnings. A warning recorded after the deadline has `late=true` and says it was late; the system does not claim an earlier notification. Close deadlines promote open incidents to P1 and recalculate policy, stopping automation if it no longer qualifies. New-slot acceptance changes the active promised timestamp; the warning remains deduplicated once per order.

## Local-demo access

Customer browsers generate a cryptographically random cookie session shared across localhost ports. Customer APIs require that private session or a per-order tracking token; operator routes require a random expiring bearer token obtained with the configured local password. Cookies are JS-readable to support this simple local demo. The switcher grants no privileges. Use only trusted localhost clients; this is not production authentication or a network-facing deployment design. CORS and socket Origins are allowlisted; the backend binds 127.0.0.1 by default. No secrets are embedded in bundles. Request schemas reject supplied totals and unknown checkout fields.
