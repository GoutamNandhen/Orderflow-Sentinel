from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import csv
import io
import uuid
import pytest
from sqlalchemy import select, func
from backend.db import transaction, now, stamp
from backend.models import (
    Order,
    Incident,
    Setting,
    Product,
    Payment,
    Refund,
    Job,
    Notification,
    ActionLog,
    Gateway,
)
from backend.engine.risk import calculate
from backend.engine.decider import decide
from backend.services import core, worker
from backend.schemas import ERRORS, Settings
from .conftest import post, force, make_incident, perform


def accelerate_jobs():
    with transaction() as s:
        for job in s.scalars(select(Job).where(Job.status == "PENDING")):
            job.due_at = stamp(now() - timedelta(seconds=1))
    worker.tick()


def test_twenty_default_bookings_exactly_twelve_failures(client, booking):
    result = [post(client, "/api/orders", booking) for _ in range(20)]
    assert all(r.status_code == 201 for r in result)
    rows = [r.json() for r in result]
    assert sum(o["initial_failed"] for o in rows) == 12
    assert [o["booking_seq"] for o in rows] == list(range(1, 21))
    assert all(
        o["initial_failed"] == (((o["booking_seq"] - 1) % 5) + 1 in (2, 4, 5))
        for o in rows
    )


def test_concurrent_atomic_sequences_and_idempotency(client, booking):
    def create(_):
        return post(client, "/api/orders", booking).json()

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(create, range(20)))
    assert sorted(o["booking_seq"] for o in rows) == list(range(1, 21))
    assert len({o["id"] for o in rows}) == 20
    assert sum(o["initial_failed"] for o in rows) == 12
    with ThreadPoolExecutor(max_workers=8) as pool:
        duplicates = list(
            pool.map(
                lambda _: post(
                    client, "/api/orders", booking, "same-key-concurrent"
                ).json(),
                range(8),
            )
        )
    assert len({o["id"] for o in duplicates}) == 1
    assert client.get("/api/demo/status").json()["next_sequence"] == 22


def test_invalid_and_duplicate_do_not_consume_counter_or_force(client, booking):
    force(client, "RATE_LIMIT")
    bad = {**booking, "phone": "invalid"}
    assert post(client, "/api/orders", bad).status_code == 422
    assert post(client, "/api/orders", {**booking, "amount": 1}).status_code == 422
    assert client.get("/api/demo/status").json()["next_sequence"] == 1
    assert client.get("/api/demo/status").json()["forced_override_pending"]
    first = post(client, "/api/orders", booking, "same-key-order").json()
    duplicate = post(client, "/api/orders", booking, "same-key-order").json()
    assert (
        first == duplicate and first["simulator_override"] and first["initial_failed"]
    )
    assert first["amount"] == 23500
    assert not client.get("/api/demo/status").json()["forced_override_pending"]
    assert (
        post(
            client,
            "/api/orders",
            {**booking, "user_name": "Different"},
            "same-key-order",
        ).status_code
        == 409
    )


@pytest.mark.parametrize("error_type", ERRORS)
def test_all_ten_workflows(client, booking, error_type):
    order, inc = make_incident(client, booking, error_type)
    assert inc["error_type"] == error_type
    assert inc["explanation"]["signals"] and inc["playbook"]["candidate_actions"]
    assert (
        inc["actions"][inc["suggested_action"]]["enabled"]
        or error_type == "ADDRESS_REJECTED"
    )
    if error_type == "ADDRESS_REJECTED":
        assert "No explicit demo lookup" in inc["actions"]["CORRECT_ADDRESS"]["reason"]
    assert inc["risk_score"] == sum(inc["risk_breakdown"]["contributions"].values())


@pytest.mark.parametrize(
    "confidence,risk,expected",
    [
        (0.699999, 5, "MANUAL"),
        (0.7, 60, "ONE_CLICK"),
        (0.9, 30, "AUTO"),
        (0.9, 30.0000001, "ONE_CLICK"),
        (0.9, 60.000001, "MANUAL"),
        (0.899999, 30, "ONE_CLICK"),
    ],
)
def test_decision_exact_boundaries(confidence, risk, expected):
    assert decide(confidence, risk, "RETRY", Settings().model_dump()) == expected


def test_action_specific_risk_exact():
    r = calculate("P1", 0.9, 150000, "REFUND", True)
    assert r["components"] == {
        "impact": 100,
        "uncertainty": pytest.approx(10),
        "value_score": 30,
        "no_undo": 100,
    }
    assert r["score"] == pytest.approx(63.5) and r["tier"] == "HIGH"
    assert calculate("P1", 0.9, 150000, "CHECK_PAYMENT", True)[
        "score"
    ] == pytest.approx(48.5)
    assert calculate("P3", 1, 550000, "RETRY")["components"]["value_score"] == 100


def test_mixed_critical_cart_stays_p1_after_recovery(client, booking):
    booking["items"].append({"product_id": "PROD-101", "qty": 1})
    order, inc = make_incident(client, booking, "OUT_OF_STOCK")
    assert inc["priority"] == order["priority"] == "P1"
    result = perform(client, inc, "REASSIGN_STORE").json()
    assert result["ok"] and result["incident"]["priority"] == "P1"
    assert result["incident"]["order"]["fulfilment"] == "UNFULFILLED"


def test_automatic_retry_real_job_and_exhaustion(client, booking):
    _, inc = make_incident(client, booking, "API_TIMEOUT")
    assert inc["decision"] == "AUTO"
    accelerate_jobs()
    updated = client.get("/api/console/incidents/" + inc["id"]).json()
    assert updated["status"] == "RESOLVED" and updated["order"]["attempt_count"] == 1
    assert (
        updated["time_to_fix_sec"] >= 0
        and updated["order"]["fulfilment"] == "UNFULFILLED"
    )
    config = client.get("/api/console/settings").json()
    config["retry_failures"] = 3
    client.post("/api/console/settings", json=config)
    _, inc = make_incident(client, booking, "API_TIMEOUT")
    for _ in range(3):
        accelerate_jobs()
    updated = client.get("/api/console/incidents/" + inc["id"]).json()
    assert updated["status"] == "ESCALATED" and updated["priority"] == "P1"
    assert updated["order"]["attempt_count"] == 3
    assert not updated["actions"]["RETRY"]["enabled"]


def test_circuit_open_half_open_probe_and_failure(client):
    with transaction() as s:
        for _ in range(5):
            core.circuit_error(s, "DemoPay Primary")
    gateway = next(
        g
        for g in client.get("/api/console/gateways").json()
        if g["gateway_name"] == "DemoPay Primary"
    )
    assert gateway["circuit_state"] == "OPEN"
    assert (
        client.post(
            "/api/console/gateways/DemoPay Primary/probe", json={"success": True}
        ).status_code
        == 409
    )
    with transaction() as s:
        s.get(Gateway, "DemoPay Primary").opened_at = stamp(
            now() - timedelta(seconds=31)
        )
    worker.tick()
    assert (
        client.post(
            "/api/console/gateways/DemoPay Primary/probe", json={"success": False}
        ).json()["circuit_state"]
        == "OPEN"
    )
    with transaction() as s:
        s.get(Gateway, "DemoPay Primary").opened_at = stamp(
            now() - timedelta(seconds=31)
        )
    worker.tick()
    assert (
        client.post(
            "/api/console/gateways/DemoPay Primary/probe", json={"success": True}
        ).json()["circuit_state"]
        == "CLOSED"
    )


def test_uncertain_payment_manual_policy_no_double_charge_and_refund_pending(
    client, booking
):
    order, inc = make_incident(client, booking, "UNMATCHED_DEBIT")
    assert inc["decision"] == "MANUAL" and inc["priority"] == "P1"
    assert perform(client, inc, "CHECK_PAYMENT", "approve").status_code == 409
    assert not perform(client, inc, "SWITCH_GATEWAY").json()["ok"]
    inc = perform(client, inc, "CHECK_PAYMENT").json()["incident"]
    assert (
        inc["order"]["payment"]["status"] == "CAPTURED" and inc["status"] != "RESOLVED"
    )
    assert inc["order"]["payment"]["attempt_count"] == 1
    assert not perform(client, inc, "REFUND").json()["ok"]
    refunded = perform(client, inc, "REFUND", confirmed=True, key="refund-idempotency")
    assert refunded.json()["ok"]
    repeat = perform(client, inc, "REFUND", confirmed=True, key="refund-idempotency")
    assert repeat.json() == refunded.json()
    inc = refunded.json()["incident"]
    assert (
        inc["order"]["refund"]["status"] == "PENDING"
        and inc["status"] == "REFUND_PENDING"
    )
    accelerate_jobs()
    inc = client.get("/api/console/incidents/" + inc["id"]).json()
    assert (
        inc["order"]["refund"]["status"] == "COMPLETED"
        and inc["order"]["status"] == "REFUNDED"
    )
    assert inc["status"] == "RESOLVED"
    with transaction() as s:
        assert s.scalar(select(func.count()).select_from(Refund)) == 1


def test_cod_never_refunded(client, booking):
    booking["payment_method"] = "COD"
    _, inc = make_incident(client, booking, "OUT_OF_STOCK")
    assert not inc["actions"]["REFUND"]["enabled"]
    assert not perform(client, inc, "REFUND", confirmed=True).json()["ok"]
    result = perform(client, inc, "CANCEL", confirmed=True).json()
    assert result["ok"] and result["incident"]["order"]["status"] == "CANCELLED"


def test_notify_and_substitute_remain_open_until_acceptance(client, booking):
    order, inc = make_incident(client, booking, "OUT_OF_STOCK")
    inc = perform(client, inc, "NOTIFY_CUSTOMER").json()["incident"]
    assert inc["status"] != "RESOLVED"
    inc = perform(client, inc, "OFFER_SUBSTITUTE").json()["incident"]
    assert (
        inc["order"]["pending_offer"]["kind"] == "SUBSTITUTE"
        and inc["status"] != "RESOLVED"
    )
    changed = post(
        client,
        f'/api/orders/{order["id"]}/accept',
        {"accept": True, "expected_version": inc["order"]["version"]},
    ).json()
    assert (
        changed["items"][0]["product_id"] == "PROD-120"
        and changed["incident_status"] == "RESOLVED"
    )
    assert changed["amount"] == order["amount"]


def test_address_requires_explicit_lookup_and_acceptance(client, booking):
    booking["pincode"] = "560039"
    order, inc = make_incident(client, booking, "ADDRESS_REJECTED")
    inc = perform(client, inc, "CORRECT_ADDRESS").json()["incident"]
    assert inc["order"]["pincode"] == "560039"
    changed = post(
        client,
        f'/api/orders/{order["id"]}/accept',
        {"accept": True, "expected_version": inc["order"]["version"]},
    ).json()
    assert (
        changed["pincode"] == "560038" and changed["address"] == "DEMO_PICKUP_LOCATION"
    )


def test_medicine_substitutions_disabled(client, booking):
    booking["items"] = [{"product_id": "PROD-101", "qty": 1}]
    _, inc = make_incident(client, booking, "OUT_OF_STOCK")
    assert not inc["actions"]["OFFER_SUBSTITUTE"]["enabled"]


def test_concurrent_stock_and_cancel_release_exactly_once(client, booking):
    with transaction() as s:
        s.get(Product, "PROD-109").stock = 1
        conf = core.settings(s)
        conf["enabled"] = False
        s.get(Setting, "config").value = conf
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda _: post(client, "/api/orders", booking), range(8))
        )
    assert sum(r.status_code == 201 for r in results) == 1
    assert sum(r.status_code == 409 for r in results) == 7
    with transaction() as s:
        assert s.get(Product, "PROD-109").stock == 0
    assert client.get("/api/demo/status").json()["next_sequence"] == 2


def test_operator_race_stops_stale_recovery(client, booking):
    _, inc = make_incident(client, booking, "API_TIMEOUT")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: perform(client, inc, "ESCALATE"), range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    accelerate_jobs()
    updated = client.get("/api/console/incidents/" + inc["id"]).json()
    assert updated["status"] == "ESCALATED" and updated["order"]["attempt_count"] == 0
    assert all(j["status"] == "CANCELLED" for j in updated["jobs"])


def test_deadline_dedup_late_and_restart_state(client, booking):
    order = post(client, "/api/orders", booking).json()
    with transaction() as s:
        o = s.get(Order, order["id"])
        o.created_at = stamp(now() - timedelta(minutes=29))
        o.promised_by = stamp(now() + timedelta(minutes=11))
    worker.tick()
    worker.tick()
    core.initialize()
    with transaction() as s:
        notes = s.scalars(
            select(Notification).where(Notification.order_id == order["id"])
        ).all()
        assert len(notes) == 1 and not notes[0].late
        assert s.get(Setting, "sequence").value["next"] == 2
    order = post(client, "/api/orders", booking).json()
    with transaction() as s:
        o = s.get(Order, order["id"])
        o.created_at = stamp(now() - timedelta(minutes=50))
        o.promised_by = stamp(now() - timedelta(minutes=10))
    worker.tick()
    with transaction() as s:
        note = s.scalar(
            select(Notification).where(
                Notification.order_id == order["id"],
                Notification.kind == "DEADLINE_WARNING",
            )
        )
        assert note.late and "late" in note.message


def test_restart_pending_job_persists_and_runs(client, booking):
    _, inc = make_incident(client, booking, "API_TIMEOUT")
    core.initialize()
    accelerate_jobs()
    assert (
        client.get("/api/console/incidents/" + inc["id"]).json()["status"] == "RESOLVED"
    )


def test_filtered_csv_matches_history_and_access_boundaries(client, booking):
    _, inc = make_incident(client, booking, "OUT_OF_STOCK")
    assert perform(client, inc, "REASSIGN_STORE").json()["ok"]
    query = "q=OUT&risk=LOW&actor=OPERATOR"
    rows = client.get("/api/console/history?" + query).json()["items"]
    assert len(rows) == 1
    export = client.get("/api/console/history?" + query + "&format=csv")
    parsed = list(csv.DictReader(io.StringIO(export.text)))
    assert [r["id"] for r in parsed] == [r["id"] for r in rows]
    client.headers.pop("Authorization")
    assert client.get("/api/console/settings").status_code == 401
    assert client.post("/api/console/retrain").status_code == 401
    client.headers["X-Customer-Session"] = "another-private-customer-session-abcdef"
    assert client.get("/api/orders/" + inc["order_id"]).status_code == 404


def test_demo_idempotency_across_block_positions(client):
    for _ in range(3):
        post(client, "/api/console/demo", {"profile": "judge"})
    one = post(client, "/api/console/demo", {"profile": "judge"}, "judge-key-on-four")
    two = post(client, "/api/console/demo", {"profile": "judge"}, "judge-key-on-four")
    assert one.json() == two.json() and one.json()["booking_seq"] == 4
    assert client.get("/api/demo/status").json()["next_sequence"] == 5


def test_rule_fallback_unavailable_scores(client, booking, monkeypatch):
    from backend.engine import classifier

    monkeypatch.setattr(classifier, "current", lambda: None)
    _, inc = make_incident(client, booking, "API_TIMEOUT")
    assert (
        inc["model_output"]["confidence"] is None
        and inc["model_output"]["failure_probability"] is None
    )
    assert inc["decision"] == "MANUAL" and "fallback" in inc["model_output"]["source"]


def test_fulfilment_legal_transitions_and_no_delivery_on_recovery(client, booking):
    order = post(client, "/api/orders", booking).json()
    assert (
        post(
            client,
            f'/api/console/orders/{order["id"]}/fulfilment',
            {"state": "DELIVERED", "expected_version": order["version"]},
        ).status_code
        == 409
    )
    for stage in ["PACKED", "OUT_FOR_DELIVERY", "DELIVERED"]:
        result = post(
            client,
            f'/api/console/orders/{order["id"]}/fulfilment',
            {"state": stage, "expected_version": order["version"]},
        )
        assert result.status_code == 200
        order = result.json()
    assert order["delivered_at"] and order["fulfilment"] == "DELIVERED"


def test_customer_websocket_safe_and_console_committed(client, booking):
    order = post(client, "/api/orders", booking).json()
    with client.websocket_connect(
        f'/ws/order/{order["id"]}?token={order["tracking_token"]}',
        headers={"origin": "http://localhost:5173"},
    ) as ws:
        assert ws.receive_json()["type"] == "snapshot_required"
        with transaction() as s:
            o = s.get(Order, order["id"])
            core.bump(o)
            core.emit(s, "risk_scored", o, data={"secret_risk": 99})
        event = ws.receive_json()
        assert (
            event["type"] == "order_updated"
            and event["data"] == {}
            and event["incident_id"] is None
        )
        assert event["entity_version"] == 2 and event["id"] > 0 and event["timestamp"]


def test_settings_guardrails_validated(client):
    settings = client.get("/api/console/settings").json()
    for field, value in [
        ("auto_risk", 35),
        ("auto_confidence", 0.85),
        ("failing_positions", [2, 2]),
        ("force_error", "UNKNOWN"),
    ]:
        assert (
            client.post(
                "/api/console/settings", json={**settings, field: value}
            ).status_code
            == 422
        )
