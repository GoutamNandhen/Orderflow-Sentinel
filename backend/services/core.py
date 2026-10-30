import hashlib
import json
import secrets
import uuid
from datetime import timedelta
from sqlalchemy import select
from fastapi import HTTPException
from ..db import Base, engine, transaction, now, stamp, dt, DATA
from ..models import (
    Product,
    Setting,
    Order,
    Incident,
    Payment,
    Refund,
    ActionLog,
    Feedback,
    Gateway,
    Job,
    Event,
    Idempotency,
    Notification,
    ModelArtifact,
)
from ..schemas import Settings
from ..simulator import choose
from ..engine import (
    classifier,
    priority,
    risk,
    decider,
    forecaster,
    detector,
    explainer,
    actions,
)
from . import adapters

PLAYBOOK_PATH = DATA / "playbook.json"


def uid(prefix):
    return prefix + "-" + uuid.uuid4().hex[:16]


def serial(obj):
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def settings(s):
    return s.get(Setting, "config").value.copy()


def playbook():
    return json.loads(PLAYBOOK_PATH.read_text(encoding="utf-8"))


def initialize():
    Base.metadata.create_all(engine)
    with transaction() as s:
        active_model = s.get(Setting, "active_model_version")
        if active_model:
            artifact = s.get(ModelArtifact, active_model.value["version"])
            if artifact:
                model_dir = DATA / "models"
                model_dir.mkdir(exist_ok=True)
                (model_dir / f"{artifact.version}.joblib").write_bytes(artifact.bundle)
                (model_dir / f"{artifact.version}.json").write_text(
                    json.dumps(artifact.report), encoding="utf-8"
                )
                (model_dir / "current.txt").write_text(
                    artifact.version, encoding="utf-8"
                )
        if not s.get(Setting, "config"):
            s.add(Setting(key="config", value=Settings().model_dump()))
            s.add(Setting(key="sequence", value={"next": 1}))
        for name in ("DemoPay Primary", "DemoPay Backup", "DemoShip"):
            if not s.get(Gateway, name):
                s.add(Gateway(gateway_name=name))
        from .seed import PRODUCTS

        for product in PRODUCTS:
            if not s.get(Product, product["id"]):
                s.add(Product(**product))
        # A process crash during training is reported, never presented as success.
        for job in s.scalars(
            select(Job).where(Job.kind == "TRAIN", Job.status == "RUNNING")
        ):
            job.status, job.result = "FAILED", {
                "error": "Backend restarted during training; previous model preserved"
            }


def emit(s, type_, order=None, incident=None, data=None):
    s.add(
        Event(
            type=type_,
            order_id=order.id if order else None,
            incident_id=incident.id if incident else None,
            entity_version=order.version if order else 1,
            data=data or {},
        )
    )


def bump(order, incident=None):
    order.version += 1
    order.updated_at = stamp()
    if incident:
        incident.version += 1


def log(s, order, incident, action, actor, before, result, note=""):
    s.add(
        ActionLog(
            order_id=order.id,
            incident_id=incident.id if incident else None,
            action=action,
            done_by=actor,
            before_status=before,
            after_status=order.status,
            attempt_no=order.attempt_count,
            result=result,
            note=note,
        )
    )


def notification(s, order, kind, message, late=False):
    if not s.scalar(
        select(Notification).where(
            Notification.order_id == order.id, Notification.kind == kind
        )
    ):
        s.add(Notification(order_id=order.id, kind=kind, message=message, late=late))
        order.customer_message = message


def remember(s, scope, key, body, callback):
    if not key or not 8 <= len(key) <= 200:
        raise HTTPException(422, "Idempotency-Key must contain 8–200 characters")
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    storage_key = scope + ":" + key
    previous = s.get(Idempotency, storage_key)
    if previous:
        if previous.digest != digest:
            raise HTTPException(409, "Idempotency key was used with different input")
        return previous.response
    response = callback()
    s.flush()
    s.add(Idempotency(key=storage_key, digest=digest, response=response))
    return response


def circuit_error(s, name):
    gw = s.get(Gateway, name)
    cutoff = now() - timedelta(minutes=1)
    gw.errors = [t for t in gw.errors if dt(t) > cutoff] + [stamp()]
    gw.last_errors_1min = len(gw.errors)
    if len(gw.errors) >= 5 or gw.circuit_state == "HALF_OPEN":
        changed = gw.circuit_state != "OPEN"
        gw.circuit_state, gw.opened_at, gw.probe_claimed = "OPEN", stamp(), False
        if changed:
            emit(s, "gateway_circuit_changed", data={"gateway": name, "state": "OPEN"})
    gw.updated_at = stamp()


def gateway_available(s, name, probe=False):
    gw = s.get(Gateway, name)
    if gw.circuit_state == "OPEN":
        return False
    if gw.circuit_state == "HALF_OPEN":
        if not probe or gw.probe_claimed:
            return False
        gw.probe_claimed = True
    return True


def gateway_success(s, name):
    gw = s.get(Gateway, name)
    if gw.circuit_state == "HALF_OPEN":
        gw.circuit_state, gw.probe_claimed, gw.errors, gw.last_errors_1min = (
            "CLOSED",
            False,
            [],
            0,
        )
        gw.updated_at = stamp()
        emit(s, "gateway_circuit_changed", data={"gateway": name, "state": "CLOSED"})


def schedule(s, order, incident, kind="RETRY", seconds=1, payload=None):
    job = Job(
        id=uid("JOB"),
        kind=kind,
        order_id=order.id,
        incident_id=incident.id if incident else None,
        due_at=stamp(now() + timedelta(seconds=seconds)),
        expected_version=order.version,
        payload=payload or {},
    )
    s.add(job)
    return job


def score_action(order, incident, action, config, payment):
    output = risk.calculate(
        incident.priority,
        incident.confidence,
        order.amount,
        action,
        payment.status in ("CAPTURED", "DEBIT_UNKNOWN"),
    )
    mode = decider.decide(
        incident.confidence, output["score"], action, config, incident.error_type
    )
    if action == "REASSIGN_STORE" and mode == "AUTO":
        mode = "ONE_CLICK"  # Explicit store-transfer restriction independent of model confidence.
    return output, mode


def open_incident(s, order, error_type):
    entry = playbook()[error_type]
    payment = s.scalar(select(Payment).where(Payment.order_id == order.id))
    gw = s.get(Gateway, order.gateway)
    output = classifier.predict(
        order,
        error_type,
        gw.last_errors_1min,
        min(s.get(Product, i["product_id"]).stock for i in order.items),
    )
    urgency, reasons = priority.assign(order, error_type, settings(s))
    order.priority = urgency
    forecast = forecaster.forecast(s, order, error_type)
    action = entry["candidate_actions"][0]
    # A COD booking cannot have a debit; reconcile as a payment failure instead.
    if (
        action in ("CHECK_PAYMENT", "SEND_PAYMENT_LINK")
        and payment.status == "NOT_REQUIRED"
    ):
        action = "CONFIRM_ORDER"
    inc = Incident(
        id=uid("INC"),
        order_id=order.id,
        error_code=error_type,
        error_type=error_type,
        message=entry["explanation"],
        anomaly_score=output["anomaly_raw"],
        xgb_fail_prob=output["failure_probability"],
        xgb_error_class=output["error_class"],
        predicted_delay_min=forecast["delay_minutes"],
        confidence=output["policy_confidence"],
        priority=urgency,
        suggested_action=action,
        risk_score=0,
        risk_tier="LOW",
        decision="MANUAL",
        model_output=output,
        forecast=forecast,
        risk_breakdown={},
        explanation={},
    )
    risk_output, mode = score_action(order, inc, action, settings(s), payment)
    inc.risk_score, inc.risk_tier, inc.risk_breakdown, inc.decision = (
        risk_output["score"],
        risk_output["tier"],
        risk_output,
        mode,
    )
    inc.explanation = {
        **explainer.explain(entry, urgency, mode, action, inc.risk_score),
        "priority_reasons": reasons,
        "signals": detector.detect(
            error_type,
            6000 if error_type == "API_TIMEOUT" else 1200,
            classifier.HTTP[error_type],
            unmatched_debit=payment.status == "DEBIT_UNKNOWN",
        ),
    }
    order.status = {
        "AUTO": "AUTO_FIXING",
        "ONE_CLICK": "WAITING_APPROVAL",
        "MANUAL": "MANUAL_REVIEW",
    }[mode]
    order.customer_message = entry["customer_message"]
    s.add(inc)
    s.flush()
    log(
        s,
        order,
        inc,
        "DETECT",
        "ENGINE",
        "PLACED",
        f'{error_type}; {mode}; {output["source"]}',
    )
    emit(s, "incident_opened", order, inc, {"priority": urgency})
    emit(s, "risk_scored", order, inc, risk_output)
    if mode == "AUTO":
        schedule(s, order, inc, kind="AUTO", seconds=1, payload={"action": action})
    return inc


def book(s, request, customer_session, key, profile="normal", explicit_error=None):
    body = request.model_dump()
    scope = "booking:" + customer_session

    def create():
        quantities = {}
        for item in request.items:
            quantities[item.product_id] = quantities.get(item.product_id, 0) + item.qty
        items = []
        for product_id, qty in quantities.items():
            product = s.get(Product, product_id)
            if not product or qty > 20:
                raise HTTPException(422, "Unknown product or excessive quantity")
            if product.stock < qty:
                raise HTTPException(409, f"Insufficient stock for {product.name}")
            items.append(
                {
                    "product_id": product.id,
                    "name": product.name,
                    "category": product.category,
                    "price": product.price,
                    "qty": qty,
                    "is_critical": product.is_critical,
                }
            )
        counter = s.get(Setting, "sequence")
        seq = counter.value["next"]
        config = settings(s)
        error_type, override = choose(seq, config)
        if profile == "judge":
            position = ((seq - 1) % 5) + 1
            error_type = {
                2: "API_TIMEOUT",
                4: "UNMATCHED_DEBIT",
                5: "OUT_OF_STOCK",
            }.get(position)
            override = True
        if explicit_error:
            error_type, override = explicit_error, True
        if request.payment_method == "COD" and error_type in (
            "UNMATCHED_DEBIT",
            "DUPLICATE_ORDER",
        ):
            error_type = "PAYMENT_DECLINED"
        counter.value = {"next": seq + 1}
        if config["force_error"]:
            config["force_error"] = None
            s.get(Setting, "config").value = config
        for item in items:
            s.get(Product, item["product_id"]).stock -= item["qty"]
        order = Order(
            id=f"ORD-{seq:06d}",
            customer_session=customer_session,
            tracking_token=secrets.token_urlsafe(32),
            user_name=request.user_name,
            phone=request.phone,
            address=request.address,
            pincode=request.pincode,
            items=items,
            amount=sum(i["price"] * i["qty"] for i in items),
            payment_method=request.payment_method,
            category=(
                items[0]["category"]
                if len({i["category"] for i in items}) == 1
                else "Mixed"
            ),
            priority="P3",
            status="PLACED",
            booking_seq=seq,
            promised_by=stamp(now() + timedelta(minutes=request.promise_minutes)),
            created_at=stamp(),
            version=1,
            attempt_count=0,
            initial_failed=bool(error_type),
            simulator_override=override,
            profile=profile,
            recovery_failures=(
                3 if profile == "exhaustion" else config["retry_failures"]
            ),
        )
        if error_type in (
            "API_TIMEOUT",
            "RATE_LIMIT",
            "TOKEN_EXPIRED",
            "OUT_OF_STOCK",
            "STORE_CLOSED",
            "RIDER_LATE",
            "ADDRESS_REJECTED",
        ):
            order.gateway = "DemoShip"
        s.add(order)
        s.flush()
        payment = Payment(
            id=uid("PAY"),
            order_id=order.id,
            amount=order.amount,
            status=adapters.payment_result(error_type, request.payment_method),
        )
        s.add(payment)
        s.flush()
        order.priority = priority.assign(order, error_type, config)[0]
        if error_type:
            if error_type in ("API_TIMEOUT", "RATE_LIMIT", "TOKEN_EXPIRED"):
                circuit_error(s, order.gateway)
            open_incident(s, order, error_type)
        else:
            order.status = "CONFIRMED"
        log(
            s,
            order,
            None,
            "BOOK",
            "CUSTOMER" if profile == "normal" else "DEMO",
            "NONE",
            "Initial failure" if error_type else "Initial success",
            "Explicit simulator override" if override else "Default configured pattern",
        )
        emit(s, "order_created", order)
        return order_view(s, order, customer=True, include_token=True)

    return remember(
        s,
        scope,
        key,
        {**body, "profile": profile, "explicit_error": explicit_error},
        create,
    )


def release_stock(s, order):
    if order.reservation_active:
        for item in order.items:
            s.get(Product, item["product_id"]).stock += item["qty"]
        order.reservation_active = False


def cancel_jobs(s, order):
    for job in s.scalars(
        select(Job).where(
            Job.order_id == order.id,
            Job.status == "PENDING",
            Job.kind.in_(["RETRY", "AUTO"]),
        )
    ):
        job.status, job.result = "CANCELLED", {
            "reason": "Superseded by a newer operator/customer action"
        }


def resolve(s, order, inc, actor, message=None):
    inc.status, inc.resolved_at, inc.resolved_by = "RESOLVED", stamp(), actor
    inc.time_to_fix_sec = max(0, (now() - dt(inc.detected_at)).total_seconds())
    order.status = (
        "CONFIRMED" if order.status not in ("CANCELLED", "REFUNDED") else order.status
    )
    order.customer_message = (
        message
        or "The order issue has been resolved. Your order is confirmed; delivery is still pending."
    )
    order.pending_offer = None
    emit(s, "incident_resolved", order, inc)


def execute(s, order, inc, action, actor, note="", confirmed=False, scheduled=False):
    before = order.status
    payment = s.scalar(select(Payment).where(Payment.order_id == order.id))
    refund = s.scalar(select(Refund).where(Refund.order_id == order.id))
    available = actions.applicability(s, inc, order, payment, refund, playbook())
    if not available[action]["enabled"]:
        return False, available[action]["reason"]
    if action in ("REFUND", "CANCEL") and (not confirmed or actor == "ENGINE"):
        return False, "Explicit operator confirmation is required"
    cancel_jobs(s, order)
    bump(order, inc)
    score, mode = score_action(order, inc, action, settings(s), payment)
    inc.risk_breakdown, inc.risk_score, inc.risk_tier = (
        score,
        score["score"],
        score["tier"],
    )
    result = ""
    if action == "RETRY":
        order.attempt_count += 1
        if not gateway_available(s, order.gateway, probe=True):
            success = False
            result = "Gateway circuit blocks recovery attempt"
        else:
            success = adapters.retry_result(order)
            if success:
                gateway_success(s, order.gateway)
            else:
                circuit_error(s, order.gateway)
        if success:
            resolve(s, order, inc, actor)
            result = "Simulated idempotent service retry succeeded; no additional payment charge"
        elif order.attempt_count < 3:
            order.status = "AUTO_FIXING"
            schedule(s, order, inc, seconds=2**order.attempt_count)
            result = result or "Simulated retry failed; persistent retry scheduled"
        else:
            order.status, inc.status, inc.decision = (
                "MANUAL_REVIEW",
                "ESCALATED",
                "MANUAL",
            )
            order.priority = inc.priority = "P1"
            result = "Three attempts exhausted; escalated to local operator queue"
    elif action == "REFRESH_TOKEN":
        resolve(
            s,
            order,
            inc,
            actor,
            "The simulated service token was refreshed. Your order is confirmed.",
        )
        result = "Local service token refreshed; no customer credentials used"
    elif action == "CHECK_PAYMENT":
        # Local simulated ledger contains one captured debit, not a new charge.
        if payment.status == "DEBIT_UNKNOWN":
            payment.status, payment.reconciled = "CAPTURED", True
        result = "Local debit reconciled as captured. Choose CONFIRM_ORDER or confirmed REFUND; incident remains open."
        order.status = "MANUAL_REVIEW"
        order.customer_message = "Your simulated payment is verified. Our operator is confirming fulfilment or arranging a refund."
    elif action == "SWITCH_GATEWAY":
        if not gateway_available(s, "DemoPay Backup", probe=True):
            result = "Backup circuit unavailable; no payment attempted"
        else:
            order.gateway = "DemoPay Backup"
            payment.status, payment.attempt_count = (
                "CAPTURED",
                payment.attempt_count + 1,
            )
            gateway_success(s, order.gateway)
            resolve(s, order, inc, actor)
            result = (
                "One simulated payment captured by healthy backup after known decline"
            )
    elif action == "SEND_PAYMENT_LINK":
        order.pending_offer = {
            "kind": "PAYMENT",
            "message": "Accept to simulate a new payment after the known bank decline.",
        }
        order.status = "PAYMENT_PENDING"
        result = (
            "In-app simulated payment link awaiting customer acceptance; no SMS sent"
        )
    elif action == "CONFIRM_ORDER":
        resolve(s, order, inc, actor)
        result = (
            "Order confirmed against captured payment or COD; fulfilment not advanced"
        )
    elif action == "REFUND":
        s.add(Refund(id=uid("REF"), order_id=order.id, amount=order.amount))
        order.status, inc.status = "CANCELLED", "REFUND_PENDING"
        release_stock(s, order)
        schedule(s, order, inc, kind="REFUND_SETTLE", seconds=5)
        order.customer_message = "Your simulated refund was requested and is pending settlement. This is not a completed refund."
        result = "Refund requested once; simulated settlement pending"
    elif action == "CANCEL":
        order.status = "CANCELLED"
        release_stock(s, order)
        resolve(s, order, inc, actor, "The order was cancelled. No debit was captured.")
        result = "Uncharged order cancelled; stock reservation released"
    elif action == "REASSIGN_STORE":
        store = adapters.backup_store(order)
        if store["same_items_available"]:
            resolve(
                s,
                order,
                inc,
                actor,
                f'Your order is confirmed with {store["name"]}; the same items will be fulfilled in this simulation.',
            )
        result = "Same items verified by local backup-hub fixture; reserved units transferred"
    elif action in ("OFFER_SUBSTITUTE", "NEW_SLOT", "CORRECT_ADDRESS"):
        if action == "OFFER_SUBSTITUTE":
            target = (
                "PROD-120" if order.items[0]["product_id"] == "PROD-109" else "PROD-109"
            )
            product = s.get(Product, target)
            if product.stock < order.items[0]["qty"]:
                return False, "Verified substitute no longer has sufficient stock"
            order.pending_offer = {
                "kind": "SUBSTITUTE",
                "product_id": target,
                "message": f"Equal-price substitute: {product.name}. Accept before inventory or items change.",
            }
        elif action == "NEW_SLOT":
            order.pending_offer = {
                "kind": "SLOT",
                "promised_by": stamp(now() + timedelta(minutes=60)),
                "message": "Accept a new delivery promise of 60 minutes from this offer.",
            }
        else:
            order.pending_offer = {
                "kind": "ADDRESS",
                **adapters.ADDRESS_LOOKUP[order.pincode],
                "message": "Explicit local demo pickup address correction. Accept this address before dispatch.",
            }
        order.status = "WAITING_APPROVAL"
        result = "Customer acceptance pending; underlying incident remains open"
    elif action == "PRIORITY_RIDER":
        resolve(
            s,
            order,
            inc,
            actor,
            "A simulated priority rider was assigned. Delivery remains pending.",
        )
        result = "Local priority-rider fixture assigned; parcel not marked delivered"
    elif action == "NOTIFY_CUSTOMER":
        notification(
            s,
            order,
            f"OPERATOR-{inc.id}-{order.version}",
            "Our local operations team is investigating your order. No external SMS was sent.",
        )
        result = "In-app notification recorded; underlying fault remains open"
    elif action == "ESCALATE":
        order.status, inc.status, inc.decision = "MANUAL_REVIEW", "ESCALATED", "MANUAL"
        result = (
            "Escalation recorded in local operator queue; no external paging service"
        )
    payment.updated_at = stamp()
    if order.attempt_count >= 3:
        order.priority = inc.priority = "P1"
        updated, _ = score_action(order, inc, action, settings(s), payment)
        inc.risk_breakdown, inc.risk_score, inc.risk_tier = (
            updated,
            updated["score"],
            updated["tier"],
        )
    log(s, order, inc, action, actor, before, result, note)
    emit(
        s,
        "auto_action" if actor == "ENGINE" else "action_done",
        order,
        inc,
        {"action": action, "result": result},
    )
    emit(s, "order_updated", order, inc)
    return True, result


def customer_access(order, session_token=None, tracking_token=None):
    return order and (
        (
            session_token
            and secrets.compare_digest(order.customer_session, session_token)
        )
        or (
            tracking_token
            and secrets.compare_digest(order.tracking_token, tracking_token)
        )
    )


def order_view(s, order, customer=False, include_token=False):
    out = serial(order)
    for key in ("customer_session", "tracking_token", "recovery_failures"):
        out.pop(key, None)
    if include_token:
        out["tracking_token"] = order.tracking_token
    payment = s.scalar(select(Payment).where(Payment.order_id == order.id))
    refund = s.scalar(select(Refund).where(Refund.order_id == order.id))
    incident = s.scalar(
        select(Incident)
        .where(Incident.order_id == order.id)
        .order_by(Incident.detected_at.desc())
    )
    out["payment"] = serial(payment) if payment else None
    out["refund"] = serial(refund) if refund else None
    out["forecast"] = (
        incident.forecast
        if incident and incident.status != "RESOLVED"
        else forecaster.forecast(s, order, None)
    )
    out["notifications"] = [
        serial(n)
        for n in s.scalars(
            select(Notification)
            .where(Notification.order_id == order.id)
            .order_by(Notification.id.desc())
        )
    ]
    out["incident_id"] = incident.id if incident else None
    out["incident_status"] = incident.status if incident else None
    if customer:
        out.pop("gateway", None)
        out.pop("profile", None)
        out.pop("incident_id", None)
    return out


def incident_view(s, inc, detail=False):
    out = serial(inc)
    order = s.get(Order, inc.order_id)
    out["order"] = order_view(s, order)
    if detail:
        payment = s.scalar(select(Payment).where(Payment.order_id == order.id))
        refund = s.scalar(select(Refund).where(Refund.order_id == order.id))
        out["actions"] = actions.applicability(
            s, inc, order, payment, refund, playbook()
        )
        out["action_scores"] = {
            a: dict(
                zip(
                    ("risk", "decision"),
                    score_action(order, inc, a, settings(s), payment),
                )
            )
            for a in out["actions"]
        }
        out["audit"] = [
            serial(a)
            for a in s.scalars(
                select(ActionLog)
                .where(ActionLog.order_id == order.id)
                .order_by(ActionLog.id)
            )
        ]
        out["feedback"] = [
            serial(f)
            for f in s.scalars(select(Feedback).where(Feedback.incident_id == inc.id))
        ]
        out["jobs"] = [
            serial(j)
            for j in s.scalars(
                select(Job).where(Job.order_id == order.id).order_by(Job.due_at.desc())
            )
        ]
        out["playbook"] = playbook()[inc.error_type]
    return out
