import asyncio
import os
import logging
from datetime import timedelta
from sqlalchemy import select
from ..db import transaction, now, stamp, dt
from ..models import Job, Order, Incident, Gateway, Payment, Refund
from ..engine import priority
from .core import (
    settings,
    schedule,
    execute,
    emit,
    log,
    resolve,
    bump,
    notification,
    score_action,
)

logger = logging.getLogger(__name__)


def tick():
    with transaction() as s:
        for gw in s.scalars(select(Gateway)):
            gw.errors = [t for t in gw.errors if dt(t) > now() - timedelta(minutes=1)]
            gw.last_errors_1min = len(gw.errors)
            if (
                gw.circuit_state == "OPEN"
                and gw.opened_at
                and (now() - dt(gw.opened_at)).total_seconds() >= 30
            ):
                gw.circuit_state, gw.probe_claimed = "HALF_OPEN", False
                emit(
                    s,
                    "gateway_circuit_changed",
                    data={"gateway": gw.gateway_name, "state": "HALF_OPEN"},
                )
        for job in s.scalars(
            select(Job)
            .where(Job.status == "PENDING", Job.due_at <= stamp())
            .order_by(Job.due_at)
            .limit(50)
        ):
            order = s.get(Order, job.order_id) if job.order_id else None
            inc = s.get(Incident, job.incident_id) if job.incident_id else None
            if job.kind in ("RETRY", "AUTO"):
                if (
                    not order
                    or not inc
                    or order.version != job.expected_version
                    or inc.status == "RESOLVED"
                ):
                    job.status, job.result = "CANCELLED", {
                        "reason": "Stale entity version or resolved incident"
                    }
                    continue
                job.status = "RUNNING"
                action = job.payload.get("action", "RETRY")
                ok, message = execute(s, order, inc, action, "ENGINE", scheduled=True)
                job.status, job.result = ("DONE" if ok else "FAILED"), {
                    "message": message
                }
            elif job.kind == "REFUND_SETTLE":
                refund = s.scalar(select(Refund).where(Refund.order_id == order.id))
                if refund and refund.status == "PENDING":
                    before = order.status
                    refund.status, refund.settled_at = "COMPLETED", stamp()
                    order.status = "REFUNDED"
                    bump(order, inc)
                    resolve(
                        s,
                        order,
                        inc,
                        "SIMULATED_SETTLEMENT",
                        "Your simulated refund has settled. No real money moved.",
                    )
                    log(
                        s,
                        order,
                        inc,
                        "REFUND_SETTLED",
                        "SIMULATED_SETTLEMENT",
                        before,
                        "Local settlement confirmed once",
                    )
                    emit(s, "order_updated", order, inc)
                job.status, job.result = "DONE", {
                    "message": "Simulated settlement processed"
                }
        config = settings(s)
        for order in s.scalars(
            select(Order).where(
                Order.status.not_in(["CANCELLED", "REFUNDED"]),
                Order.fulfilment != "DELIVERED",
            )
        ):
            created, promised = dt(order.created_at), dt(order.promised_by)
            alert_at = created + (promised - created) * config["alert_fraction"]
            inc = s.scalar(
                select(Incident).where(
                    Incident.order_id == order.id, Incident.status != "RESOLVED"
                )
            )
            # Periodically detect a genuinely stuck local order, not just booking-time exceptions.
            if (
                not inc
                and order.status in ("PLACED", "PAYMENT_PENDING")
                and (now() - created).total_seconds() >= 120
            ):
                from .core import open_incident

                payment = s.scalar(select(Payment).where(Payment.order_id == order.id))
                inc = open_incident(
                    s,
                    order,
                    (
                        "UNMATCHED_DEBIT"
                        if payment.status == "DEBIT_UNKNOWN"
                        else "API_TIMEOUT"
                    ),
                )
                bump(order, inc)
            if now() >= alert_at:
                from ..models import Notification

                exists = s.scalar(
                    select(Notification).where(
                        Notification.order_id == order.id,
                        Notification.kind == "DEADLINE_WARNING",
                    )
                )
                if not exists:
                    late = now() >= promised
                    notification(
                        s,
                        order,
                        "DEADLINE_WARNING",
                        (
                            "Delivery deadline has passed; this warning was recorded late after restart or monitoring delay."
                            if late
                            else "Your delivery deadline is approaching. Our local demo operations team has been alerted."
                        ),
                        late,
                    )
                    bump(order, inc)
                    log(
                        s,
                        order,
                        inc,
                        "DEADLINE_WARNING",
                        "MONITOR",
                        order.status,
                        "Late warning" if late else "Pre-deadline warning",
                    )
                    emit(s, "order_updated", order, inc)
            if inc:
                urgency, reasons = priority.assign(order, inc.error_type, config)
                if urgency == "P1" and inc.priority != "P1":
                    inc.priority = order.priority = "P1"
                    bump(order, inc)
                    payment = s.scalar(
                        select(Payment).where(Payment.order_id == order.id)
                    )
                    score, mode = score_action(
                        order, inc, inc.suggested_action, config, payment
                    )
                    inc.risk_score, inc.risk_tier, inc.risk_breakdown, inc.decision = (
                        score["score"],
                        score["tier"],
                        score,
                        mode,
                    )
                    inc.explanation = {**inc.explanation, "priority_reasons": reasons}
                    # Stop automation if a newly close deadline changes its handling policy.
                    if mode != "AUTO":
                        from .core import cancel_jobs

                        cancel_jobs(s, order)
                        order.status = (
                            "MANUAL_REVIEW" if mode == "MANUAL" else "WAITING_APPROVAL"
                        )
                    emit(s, "risk_scored", order, inc, score)


async def run():
    while True:
        try:
            await asyncio.to_thread(tick)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Persistent monitoring/recovery tick failed")
        await asyncio.sleep(max(0.4, float(os.getenv("WORKER_POLL_SECONDS", "0.4"))))
