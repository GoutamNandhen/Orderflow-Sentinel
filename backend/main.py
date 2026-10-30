import asyncio
import csv
import io
import json
import os
import secrets
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from fastapi import (
    FastAPI,
    Depends,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import select, func, or_, case
from sqlalchemy.orm import Session
from .db import engine, transaction, now, stamp, dt, ROOT
from .models import (
    Product,
    Order,
    Incident,
    Setting,
    Payment,
    Refund,
    ActionLog,
    Feedback,
    Gateway,
    Event,
    Job,
    OperatorSession,
    ModelArtifact,
)
from .schemas import (
    Booking,
    Settings,
    ActionRequest,
    Acceptance,
    DemoRequest,
    Login,
    NoteRequest,
)
from .services import core, worker
from .engine import classifier
from . import state  # Register server-side transition invariants.
from .auth import operator_password


@asynccontextmanager
async def lifespan(app):
    operator_password()
    core.initialize()
    task = asyncio.create_task(worker.run())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="OrderFlow Sentinel · Local Simulation", lifespan=lifespan)
origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:5174"
).split(",")
if os.getenv("RENDER_EXTERNAL_URL"):
    origins.append(os.environ["RENDER_EXTERNAL_URL"].rstrip("/"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Idempotency-Key",
        "X-Customer-Session",
    ],
)


def session():
    with Session(engine) as s:
        yield s


def valid_operator(token, s):
    record = s.get(OperatorSession, token or "")
    return record and dt(record.expires_at) > now()


def operator(authorization: str = Header(default=""), s=Depends(session)):
    token = authorization.removeprefix("Bearer ")
    if not valid_operator(token, s):
        raise HTTPException(401, "Operator sign-in required")
    return "OPERATOR"


def customer(x_customer_session: str = Header(default="")):
    if len(x_customer_session) < 32 or len(x_customer_session) > 200:
        raise HTTPException(
            401, "A private customer session token of 32–200 characters is required"
        )
    return x_customer_session


def get_order(s, order_id):
    order = s.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


def get_incident(s, incident_id):
    inc = s.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    return inc


@app.get("/api/health")
def health(s=Depends(session)):
    s.execute(select(1))
    model = classifier.current()
    return {
        "status": "ok",
        "timestamp": stamp(),
        "simulation": True,
        "model": model["version"] if model else "rule fallback",
        "worker": "single process; one uvicorn worker required",
    }


@app.post("/api/console/login")
def login(body: Login):
    if not secrets.compare_digest(body.password, operator_password()):
        raise HTTPException(401, "Incorrect local operator password")
    with transaction() as s:
        token = secrets.token_urlsafe(40)
        s.add(
            OperatorSession(token=token, expires_at=stamp(now() + timedelta(hours=12)))
        )
    return {"token": token}


@app.get("/api/products")
def products(s=Depends(session)):
    return [core.serial(p) for p in s.scalars(select(Product).order_by(Product.id))]


@app.get("/api/demo/status")
def demo_status(s=Depends(session)):
    config = core.settings(s)
    seq = s.get(Setting, "sequence").value["next"]
    return {
        "next_sequence": seq,
        "position": ((seq - 1) % 5) + 1,
        "enabled": config["enabled"],
        "failing_positions": config["failing_positions"],
        "forced_override_pending": bool(config["force_error"]),
    }


@app.post("/api/orders", status_code=201)
def create_order(
    body: Booking, identity=Depends(customer), idempotency_key: str = Header(default="")
):
    with transaction() as s:
        return core.book(s, body, identity, idempotency_key)


@app.get("/api/orders")
def my_orders(
    identity=Depends(customer),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    s=Depends(session),
):
    query = select(Order).where(Order.customer_session == identity)
    return {
        "total": s.scalar(select(func.count()).select_from(query.subquery())),
        "items": [
            core.order_view(s, o, True, True)
            for o in s.scalars(
                query.order_by(Order.booking_seq.desc()).offset(offset).limit(limit)
            )
        ],
    }


@app.get("/api/orders/{order_id}")
def order_detail(
    order_id: str,
    token: str = "",
    x_customer_session: str = Header(default=""),
    s=Depends(session),
):
    order = s.get(Order, order_id)
    if not core.customer_access(order, x_customer_session, token):
        raise HTTPException(404, "Order not found for this customer")
    return core.order_view(s, order, True)


@app.post("/api/orders/{order_id}/accept")
def accept(
    order_id: str,
    body: Acceptance,
    identity=Depends(customer),
    idempotency_key: str = Header(default=""),
):
    with transaction() as s:
        order = get_order(s, order_id)
        if not core.customer_access(order, identity):
            raise HTTPException(404, "Order not found")

        def apply():
            if order.version != body.expected_version or not order.pending_offer:
                raise HTTPException(
                    409, "Offer changed or is no longer pending; refresh"
                )
            offer = order.pending_offer
            inc = s.scalar(
                select(Incident).where(
                    Incident.order_id == order.id, Incident.status != "RESOLVED"
                )
            )
            before = order.status
            core.cancel_jobs(s, order)
            core.bump(order, inc)
            if body.accept:
                if offer["kind"] == "SUBSTITUTE":
                    product = s.get(Product, offer["product_id"])
                    qty = order.items[0]["qty"]
                    if (
                        product.stock < qty
                        or product.price != order.items[0]["price"]
                        or product.is_critical
                    ):
                        raise HTTPException(
                            409, "Equal-price noncritical substitute unavailable"
                        )
                    core.release_stock(s, order)
                    product.stock -= qty
                    order.reservation_active = True
                    order.items = [
                        dict(
                            product_id=product.id,
                            name=product.name,
                            category=product.category,
                            price=product.price,
                            qty=qty,
                            is_critical=product.is_critical,
                        )
                    ]
                elif offer["kind"] == "ADDRESS":
                    order.address, order.pincode = offer["address"], offer["pincode"]
                elif offer["kind"] == "SLOT":
                    order.promised_by = offer["promised_by"]
                elif offer["kind"] == "PAYMENT":
                    payment = s.scalar(
                        select(Payment).where(Payment.order_id == order.id)
                    )
                    if payment.status not in ("DECLINED", "NOT_DEBITED"):
                        raise HTTPException(
                            409,
                            "Payment is already captured or uncertain; cannot charge",
                        )
                    payment.status, payment.attempt_count = (
                        "CAPTURED",
                        payment.attempt_count + 1,
                    )
                if offer["kind"] == "SLOT" and inc.error_type != "RIDER_LATE":
                    order.pending_offer = None
                    order.status, inc.decision = "MANUAL_REVIEW", "MANUAL"
                    order.customer_message = "Your new slot was accepted. The original stock, store or address issue still requires review."
                else:
                    core.resolve(
                        s,
                        order,
                        inc,
                        "CUSTOMER_ACCEPTANCE",
                        "Your accepted change has been applied. Order confirmed; delivery is pending.",
                    )
            else:
                order.pending_offer, order.status, inc.decision = (
                    None,
                    "MANUAL_REVIEW",
                    "MANUAL",
                )
                order.customer_message = "You declined the proposed change. The local operator team will review the order."
            core.log(
                s,
                order,
                inc,
                "ACCEPT" if body.accept else "DECLINE",
                "CUSTOMER",
                before,
                f'{offer["kind"]} offer processed',
            )
            core.emit(s, "order_updated", order, inc)
            return core.order_view(s, order, True)

        return core.remember(
            s, "accept:" + identity, idempotency_key, body.model_dump(), apply
        )


def incident_query(
    q="",
    priority="",
    risk="",
    decision="",
    status="",
    error_type="",
    actor="",
    since="",
    until="",
):
    query = select(Incident).join(Order, Order.id == Incident.order_id)
    if q:
        safe = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(
            or_(
                Incident.order_id.ilike(f"%{safe}%", escape="\\"),
                Incident.error_type.ilike(f"%{safe}%", escape="\\"),
                Incident.message.ilike(f"%{safe}%", escape="\\"),
                Order.user_name.ilike(f"%{safe}%", escape="\\"),
            )
        )
    for col, value in [
        (Incident.priority, priority),
        (Incident.risk_tier, risk),
        (Incident.decision, decision),
        (Incident.error_type, error_type),
        (Incident.resolved_by, actor),
    ]:
        if value:
            query = query.where(col == value)
    if status:
        query = query.where(
            Incident.status != "RESOLVED"
            if status == "OPEN"
            else Incident.status == status
        )
    if since:
        try:
            dt(since)
        except ValueError:
            raise HTTPException(422, "Invalid since timestamp")
        if engine.dialect.name == "postgresql":
            from sqlalchemy import cast, DateTime

            query = query.where(
                cast(Incident.detected_at, DateTime(timezone=True)) >= dt(since)
            )
        else:
            query = query.where(
                func.julianday(Incident.detected_at) >= func.julianday(since)
            )
    if until:
        try:
            dt(until)
        except ValueError:
            raise HTTPException(422, "Invalid until timestamp")
        if engine.dialect.name == "postgresql":
            from sqlalchemy import cast, DateTime

            query = query.where(
                cast(Incident.detected_at, DateTime(timezone=True)) <= dt(until)
            )
        else:
            query = query.where(
                func.julianday(Incident.detected_at) <= func.julianday(until)
            )
    return query


@app.get("/api/console/incidents", dependencies=[Depends(operator)])
def incidents(
    q: str = Query("", max_length=100),
    priority: str = "",
    risk: str = "",
    decision: str = "",
    status: str = "",
    error_type: str = "",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    s=Depends(session),
):
    query = incident_query(q, priority, risk, decision, status, error_type)
    total = s.scalar(select(func.count()).select_from(query.subquery()))
    query = (
        query.order_by(
            Incident.priority, Incident.risk_score.desc(), Incident.detected_at.desc()
        )
        .limit(limit)
        .offset(offset)
    )
    return {
        "total": total,
        "items": [core.incident_view(s, i) for i in s.scalars(query)],
    }


@app.get("/api/console/incidents/{incident_id}", dependencies=[Depends(operator)])
def incident_detail(incident_id: str, s=Depends(session)):
    return core.incident_view(s, get_incident(s, incident_id), True)


def operate(incident_id, body, key, endpoint):
    with transaction() as s:
        inc = get_incident(s, incident_id)
        order = get_order(s, inc.order_id)

        def apply():
            if inc.version != body.expected_version:
                raise HTTPException(409, "Incident changed; refresh before acting")
            if inc.status == "RESOLVED":
                raise HTTPException(409, "Incident already resolved")
            if endpoint == "approve" and (
                inc.decision == "MANUAL" or body.action != inc.suggested_action
            ):
                raise HTTPException(
                    409,
                    "Manual policy cannot use one-click approval; use an explicit reviewed action",
                )
            if endpoint == "reject":
                core.cancel_jobs(s, order)
                core.bump(order, inc)
                before = order.status
                inc.decision, order.status = "MANUAL", "MANUAL_REVIEW"
                result = "Suggestion rejected; explicit operator handling required"
                core.log(s, order, inc, "REJECT", "OPERATOR", before, result, body.note)
                core.emit(s, "action_done", order, inc)
                ok = True
            else:
                # Recalculate at submission time; confidence never authorizes financial effects alone.
                payment = s.scalar(select(Payment).where(Payment.order_id == order.id))
                score, mode = core.score_action(
                    order, inc, body.action, core.settings(s), payment
                )
                if endpoint == "approve" and mode == "MANUAL":
                    raise HTTPException(
                        409, "Selected action now requires manual review"
                    )
                ok, result = core.execute(
                    s, order, inc, body.action, "OPERATOR", body.note, body.confirmed
                )
                if not ok:
                    core.log(
                        s,
                        order,
                        inc,
                        body.action,
                        "OPERATOR",
                        order.status,
                        "REJECTED: " + result,
                        body.note,
                    )
            if ok:
                s.add(
                    Feedback(
                        incident_id=inc.id,
                        operator_decision=(
                            "REJECTED"
                            if endpoint == "reject"
                            else "APPROVED" if endpoint == "approve" else "CHANGED"
                        ),
                        chosen_action=body.action,
                        comment=body.note,
                    )
                )
            s.flush()
            return {
                "ok": ok,
                "message": result,
                "incident": core.incident_view(s, inc, True),
            }

        return core.remember(
            s, f"{endpoint}:{incident_id}", key, body.model_dump(), apply
        )


@app.post(
    "/api/console/incidents/{incident_id}/approve", dependencies=[Depends(operator)]
)
def approve(
    incident_id: str, body: ActionRequest, idempotency_key: str = Header(default="")
):
    return operate(incident_id, body, idempotency_key, "approve")


@app.post(
    "/api/console/incidents/{incident_id}/action", dependencies=[Depends(operator)]
)
def action(
    incident_id: str, body: ActionRequest, idempotency_key: str = Header(default="")
):
    return operate(incident_id, body, idempotency_key, "action")


@app.post(
    "/api/console/incidents/{incident_id}/reject", dependencies=[Depends(operator)]
)
def reject(
    incident_id: str, body: ActionRequest, idempotency_key: str = Header(default="")
):
    return operate(incident_id, body, idempotency_key, "reject")


@app.get("/api/console/orders", dependencies=[Depends(operator)])
def console_orders(
    q: str = Query("", max_length=100),
    status: str = "",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    s=Depends(session),
):
    query = select(Order)
    if q:
        query = query.where(or_(Order.id.contains(q), Order.user_name.contains(q)))
    if status:
        query = query.where(Order.status == status)
    total = s.scalar(select(func.count()).select_from(query.subquery()))
    return {
        "total": total,
        "items": [
            core.order_view(s, o)
            for o in s.scalars(
                query.order_by(Order.booking_seq.desc()).limit(limit).offset(offset)
            )
        ],
    }


@app.post(
    "/api/console/incidents/{incident_id}/notes", dependencies=[Depends(operator)]
)
def add_note(
    incident_id: str, body: NoteRequest, idempotency_key: str = Header(default="")
):
    with transaction() as s:
        inc = get_incident(s, incident_id)
        order = get_order(s, inc.order_id)

        def apply():
            if inc.version != body.expected_version:
                raise HTTPException(409, "Incident changed; refresh before adding note")
            inc.version += 1
            core.log(
                s,
                order,
                inc,
                "NOTE",
                "OPERATOR",
                order.status,
                "Operator audit note recorded",
                body.note,
            )
            core.emit(s, "action_done", order, inc, {"action": "NOTE"})
            s.flush()
            return core.incident_view(s, inc, True)

        return core.remember(
            s, "notes:" + incident_id, idempotency_key, body.model_dump(), apply
        )


@app.post("/api/console/orders/{order_id}/fulfilment", dependencies=[Depends(operator)])
def fulfilment(order_id: str, body: dict, idempotency_key: str = Header(default="")):
    with transaction() as s:
        order = get_order(s, order_id)

        def apply():
            states = ["UNFULFILLED", "PACKED", "OUT_FOR_DELIVERY", "DELIVERED"]
            if (
                order.status not in ("CONFIRMED", "RESOLVED")
                or body.get("expected_version") != order.version
            ):
                raise HTTPException(409, "Order cannot advance or its version changed")
            index = states.index(order.fulfilment)
            if index == 3 or body.get("state") != states[index + 1]:
                raise HTTPException(409, "Advance exactly one fulfilment stage")
            before = order.status
            order.fulfilment = states[index + 1]
            core.bump(order)
            if order.fulfilment == "DELIVERED":
                order.delivered_at, order.reservation_active = stamp(), False
            core.log(
                s,
                order,
                None,
                "FULFILMENT",
                "OPERATOR",
                before,
                f"Simulated {order.fulfilment}",
            )
            core.emit(s, "order_updated", order)
            return core.order_view(s, order)

        return core.remember(s, "fulfilment:" + order_id, idempotency_key, body, apply)


@app.get("/api/console/history", dependencies=[Depends(operator)])
def history(
    q: str = Query("", max_length=100),
    priority: str = "",
    risk: str = "",
    actor: str = "",
    since: str = "",
    until: str = "",
    format: str = "",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    s=Depends(session),
):
    query = incident_query(
        q=q,
        priority=priority,
        risk=risk,
        actor=actor,
        since=since,
        until=until,
        status="RESOLVED",
    ).order_by(Incident.resolved_at.desc())
    total = s.scalar(select(func.count()).select_from(query.subquery()))
    if format == "csv":
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        fields = [
            "id",
            "order_id",
            "error_type",
            "priority",
            "risk_tier",
            "risk_score",
            "resolved_by",
            "detected_at",
            "resolved_at",
            "time_to_fix_sec",
        ]
        writer.writerow(fields)
        for inc in s.scalars(query.limit(10000)):
            writer.writerow([getattr(inc, f) for f in fields])
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=sentinel-history.csv",
                "X-Export-Limit": "10000",
            },
        )
    return {
        "total": total,
        "items": [
            core.incident_view(s, inc)
            for inc in s.scalars(query.limit(limit).offset(offset))
        ],
    }


@app.get("/api/console/stats", dependencies=[Depends(operator)])
def stats(s=Depends(session)):
    orders = s.scalars(select(Order)).all()
    incidents = s.scalars(select(Incident)).all()
    total, failures = len(orders), sum(o.initial_failed for o in orders)
    resolved = [i for i in incidents if i.status == "RESOLVED"]
    recovered = [
        i
        for i in resolved
        if s.get(Order, i.order_id).initial_failed
        and s.get(Order, i.order_id).status not in ("CANCELLED", "REFUNDED")
    ]
    recovered_ids = {i.order_id for i in recovered}
    open_ = [i for i in incidents if i.status != "RESOLVED"]
    times = [i.time_to_fix_sec for i in resolved if i.time_to_fix_sec is not None]
    by_type = [
        {"name": name, "count": sum(i.error_type == name for i in incidents)}
        for name in sorted({i.error_type for i in incidents})
    ]
    trend = []
    for delta in reversed(range(6)):
        hour = (now() - timedelta(hours=delta)).replace(
            minute=0, second=0, microsecond=0
        )
        end = hour + timedelta(hours=1)
        bucket = [i for i in incidents if hour <= dt(i.detected_at) < end]
        durations = [i.time_to_fix_sec for i in bucket if i.time_to_fix_sec is not None]
        trend.append(
            {
                "hour": stamp(hour),
                "detected": len(bucket),
                "recovered": sum(i in recovered for i in bucket),
                "mean_seconds": sum(durations) / len(durations) if durations else None,
            }
        )
    return {
        "total_orders": total,
        "initial_failures": failures,
        "initial_success_rate": (total - failures) / total if total else None,
        "recovered_orders": len(recovered_ids),
        "eventual_recovery_rate": len(recovered_ids) / failures if failures else None,
        "open_incidents": len(open_),
        "open_p1": sum(i.priority == "P1" for i in open_),
        "auto_resolved": sum(i.resolved_by == "ENGINE" for i in resolved),
        "average_resolution_seconds": sum(times) / len(times) if times else None,
        "money_at_risk_paise": sum(
            s.get(Order, i.order_id).amount
            for i in open_
            if s.scalar(select(Payment).where(Payment.order_id == i.order_id)).status
            in ("CAPTURED", "DEBIT_UNKNOWN")
        ),
        "errors_by_type": by_type,
        "trend": trend,
        "handling": [
            {"name": mode, "count": sum(i.decision == mode for i in incidents)}
            for mode in ("AUTO", "ONE_CLICK", "MANUAL")
        ],
        "risk_distribution": [
            {"name": tier, "count": sum(i.risk_tier == tier for i in incidents)}
            for tier in ("LOW", "MED", "HIGH")
        ],
        "events": [
            core.serial(e)
            for e in s.scalars(select(Event).order_by(Event.id.desc()).limit(20))
        ],
        "model": classifier.current()["report"] if classifier.current() else None,
    }


@app.get("/api/console/gateways", dependencies=[Depends(operator)])
def gateways(s=Depends(session)):
    return [core.serial(g) for g in s.scalars(select(Gateway))]


@app.post("/api/console/gateways/{name}/probe", dependencies=[Depends(operator)])
def probe(name: str, body: dict):
    with transaction() as s:
        gw = s.get(Gateway, name)
        if (
            not gw
            or gw.circuit_state != "HALF_OPEN"
            or not core.gateway_available(s, name, True)
        ):
            raise HTTPException(409, "Only one probe is allowed in HALF_OPEN")
        if body.get("success") is True:
            core.gateway_success(s, name)
        else:
            core.circuit_error(s, name)
        return core.serial(gw)


@app.get("/api/console/settings", dependencies=[Depends(operator)])
def get_settings(s=Depends(session)):
    return core.settings(s)


@app.post("/api/console/settings", dependencies=[Depends(operator)])
def save_settings(body: Settings):
    with transaction() as s:
        s.get(Setting, "config").value = body.model_dump()
        core.emit(s, "settings_updated")
    return body


@app.post("/api/console/demo", dependencies=[Depends(operator)], status_code=201)
def demo(
    body: DemoRequest,
    identity=Depends(customer),
    idempotency_key: str = Header(default=""),
):
    with transaction() as s:

        def create():
            seq = s.get(Setting, "sequence").value["next"]
            position = ((seq - 1) % 5) + 1
            product = (
                "PROD-101" if body.profile == "judge" and position == 4 else "PROD-109"
            )
            booking = Booking(
                user_name="Demo Customer",
                phone="DEMO_CONTACT",
                address="DEMO_LOCATION",
                contact_mode="demo",
                pincode="560038",
                items=[{"product_id": product, "qty": 1}],
            )
            return core.book(
                s,
                booking,
                identity,
                idempotency_key,
                profile=body.profile,
                explicit_error=body.error_type,
            )

        return core.remember(
            s, "demo:" + identity, idempotency_key, body.model_dump(), create
        )


async def training_job(job_id):
    try:
        from .train.train_models import train

        report = await asyncio.to_thread(train)
        classifier.current()
        with transaction() as s:
            version = report["version"]
            s.add(
                ModelArtifact(
                    version=version,
                    bundle=(
                        ROOT / "backend/data/models" / f"{version}.joblib"
                    ).read_bytes(),
                    report=report,
                )
            )
            active = s.get(Setting, "active_model_version")
            if active:
                active.value = {"version": version}
            else:
                s.add(Setting(key="active_model_version", value={"version": version}))
            job = s.get(Job, job_id)
            job.status, job.result = "DONE", report
            core.emit(s, "model_updated", data={"version": report["version"]})
    except Exception as error:
        with transaction() as s:
            job = s.get(Job, job_id)
            job.status, job.result = "FAILED", {
                "error": str(error),
                "previous_model_preserved": True,
            }


@app.post("/api/console/retrain", dependencies=[Depends(operator)], status_code=202)
async def retrain():
    with transaction() as s:
        existing = s.scalar(
            select(Job).where(Job.kind == "TRAIN", Job.status == "RUNNING")
        )
        if existing:
            return core.serial(existing)
        job = Job(
            id=core.uid("TRAIN"),
            kind="TRAIN",
            due_at=stamp(),
            status="RUNNING",
            payload={},
        )
        s.add(job)
        s.flush()
        result = core.serial(job)
    asyncio.create_task(training_job(job.id))
    return result


@app.get("/api/console/jobs", dependencies=[Depends(operator)])
def jobs(s=Depends(session)):
    return [
        core.serial(j)
        for j in s.scalars(select(Job).order_by(Job.due_at.desc()).limit(100))
    ]


@app.websocket("/ws/console")
async def console_ws(ws: WebSocket, token: str = ""):
    with Session(engine) as s:
        if not valid_operator(token, s):
            await ws.close(code=4401)
            return
    await stream(ws, None, token, None)


@app.websocket("/ws/order/{order_id}")
async def order_ws(ws: WebSocket, order_id: str, token: str = ""):
    with Session(engine) as s:
        order = s.get(Order, order_id)
        if not core.customer_access(order, tracking_token=token):
            await ws.close(code=4404)
            return
    await stream(ws, order_id, None, token)


async def stream(ws, order_id, operator_token, tracking_token):
    if ws.headers.get("origin") not in origins:
        await ws.close(code=4403)
        return
    await ws.accept()
    with Session(engine) as s:
        cursor = s.scalar(select(func.max(Event.id))) or 0
    await ws.send_json(
        {
            "id": cursor,
            "type": "snapshot_required",
            "timestamp": stamp(),
            "entity_version": 0,
            "order_id": order_id,
            "incident_id": None,
        }
    )
    try:
        while True:
            with Session(engine) as s:
                if operator_token and not valid_operator(operator_token, s):
                    await ws.close(code=4401)
                    return
                query = select(Event).where(Event.id > cursor)
                if order_id:
                    query = query.where(Event.order_id == order_id)
                events = s.scalars(query.order_by(Event.id).limit(100)).all()
                payloads = []
                for event in events:
                    cursor = event.id
                    payload = core.serial(event)
                    if order_id:
                        # Customer events carry safe invalidations only: never scores/internal data.
                        payload["type"], payload["data"], payload["incident_id"] = (
                            "order_updated",
                            {},
                            None,
                        )
                    payloads.append(payload)
            for payload in payloads:
                await ws.send_json(payload)
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect, RuntimeError):
        return


from .hosting import mount_frontends

mount_frontends(app)
