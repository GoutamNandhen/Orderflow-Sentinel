from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sqlalchemy import select, func
import pytest
from backend.db import transaction, now, stamp
from backend.models import (
    Order,
    Product,
    Incident,
    Payment,
    Job,
    ActionLog,
    Setting,
    Feedback,
)
from backend.services import worker, core
from .conftest import make_incident, perform, post


@pytest.mark.parametrize(
    "error,action,expected",
    [
        ("RATE_LIMIT", "RETRY", "CONFIRMED"),
        ("TOKEN_EXPIRED", "REFRESH_TOKEN", "CONFIRMED"),
        ("STORE_CLOSED", "REASSIGN_STORE", "CONFIRMED"),
        ("RIDER_LATE", "PRIORITY_RIDER", "CONFIRMED"),
        ("PAYMENT_DECLINED", "SWITCH_GATEWAY", "CONFIRMED"),
    ],
)
def test_simulated_service_handlers(client, booking, error, action, expected):
    _, inc = make_incident(client, booking, error)
    result = perform(client, inc, action).json()
    assert result["ok"] and result["incident"]["order"]["status"] == expected
    assert result["incident"]["order"]["fulfilment"] == "UNFULFILLED"


def test_decline_payment_link_acceptance_and_no_duplicate_charge(client, booking):
    order, inc = make_incident(client, booking, "PAYMENT_DECLINED")
    inc = perform(client, inc, "SEND_PAYMENT_LINK").json()["incident"]
    assert (
        inc["status"] != "RESOLVED" and inc["order"]["payment"]["status"] == "DECLINED"
    )
    body = {"accept": True, "expected_version": inc["order"]["version"]}
    accepted = post(
        client, f'/api/orders/{order["id"]}/accept', body, "payment-accept-once"
    )
    repeated = post(
        client, f'/api/orders/{order["id"]}/accept', body, "payment-accept-once"
    )
    assert accepted.json() == repeated.json()
    assert accepted.json()["payment"]["attempt_count"] == 2
    assert accepted.json()["payment"]["status"] == "CAPTURED"


def test_duplicate_signal_reconciles_without_new_debit(client, booking):
    _, inc = make_incident(client, booking, "DUPLICATE_ORDER")
    assert not inc["actions"]["SWITCH_GATEWAY"]["enabled"]
    inc = perform(client, inc, "CHECK_PAYMENT").json()["incident"]
    inc = perform(client, inc, "CONFIRM_ORDER").json()["incident"]
    assert inc["status"] == "RESOLVED" and inc["order"]["payment"]["attempt_count"] == 1


@pytest.mark.parametrize(
    "error,resolves",
    [("RIDER_LATE", True), ("OUT_OF_STOCK", False), ("ADDRESS_REJECTED", False)],
)
def test_new_slot_requires_acceptance_and_does_not_fix_other_faults(
    client, booking, error, resolves
):
    order, inc = make_incident(client, booking, error)
    inc = perform(client, inc, "NEW_SLOT").json()["incident"]
    assert (
        inc["status"] != "RESOLVED"
        and inc["order"]["promised_by"] == order["promised_by"]
    )
    accepted = post(
        client,
        f'/api/orders/{order["id"]}/accept',
        {"accept": True, "expected_version": inc["order"]["version"]},
    ).json()
    assert accepted["promised_by"] != order["promised_by"]
    assert (accepted["incident_status"] == "RESOLVED") == resolves


def test_cancel_returns_stock_once_and_repeated_approval_has_one_effect(
    client, booking
):
    booking["payment_method"] = "COD"
    _, inc = make_incident(client, booking, "OUT_OF_STOCK")
    assert (
        next(p for p in client.get("/api/products").json() if p["id"] == "PROD-109")[
            "stock"
        ]
        == 99
    )
    first = perform(client, inc, "CANCEL", confirmed=True, key="cancel-once-key")
    repeat = perform(client, inc, "CANCEL", confirmed=True, key="cancel-once-key")
    assert first.json() == repeat.json()
    assert (
        next(p for p in client.get("/api/products").json() if p["id"] == "PROD-109")[
            "stock"
        ]
        == 100
    )
    _, inc = make_incident(client, booking, "OUT_OF_STOCK")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: perform(
                    client, inc, "REASSIGN_STORE", "approve", key="approval-once-key"
                ),
                range(2),
            )
        )
    assert all(r.status_code == 200 for r in results)
    with transaction() as s:
        assert (
            s.scalar(
                select(func.count())
                .select_from(ActionLog)
                .where(
                    ActionLog.incident_id == inc["id"],
                    ActionLog.action == "REASSIGN_STORE",
                )
            )
            == 1
        )
        assert (
            s.scalar(
                select(func.count())
                .select_from(Feedback)
                .where(Feedback.incident_id == inc["id"])
            )
            == 1
        )


def test_engine_operator_race_does_not_duplicate_recovery(client, booking):
    _, inc = make_incident(client, booking, "API_TIMEOUT")
    with transaction() as s:
        for job in s.scalars(select(Job).where(Job.status == "PENDING")):
            job.due_at = stamp(now() - timedelta(seconds=1))
    with ThreadPoolExecutor(max_workers=2) as pool:
        ai = pool.submit(worker.tick)
        operator = pool.submit(perform, client, inc, "ESCALATE")
        ai.result()
        result = operator.result()
    assert result.status_code in (200, 409)
    updated = client.get("/api/console/incidents/" + inc["id"]).json()
    assert updated["order"]["attempt_count"] <= 1
    assert updated["order"]["payment"]["attempt_count"] == 1
    with transaction() as s:
        assert s.get(Product, "PROD-109").stock == 99


def test_standalone_note_is_idempotent_and_does_not_cancel_recovery(client, booking):
    _, inc = make_incident(client, booking, "API_TIMEOUT")
    body = {
        "note": "Reviewed local signal; watching idempotent retry",
        "expected_version": inc["version"],
    }
    one = post(
        client, f'/api/console/incidents/{inc["id"]}/notes', body, "audit-note-once"
    )
    two = post(
        client, f'/api/console/incidents/{inc["id"]}/notes', body, "audit-note-once"
    )
    assert one.status_code == 200 and one.json() == two.json()
    assert one.json()["order"]["version"] == inc["order"]["version"]
    assert any(j["status"] == "PENDING" for j in one.json()["jobs"])


def test_forecasting_uses_completed_durations(client, booking):
    from backend.engine.forecaster import forecast

    with transaction() as s:
        config = core.settings(s)
        config["enabled"] = False
        s.get(Setting, "config").value = config
    for duration in [20, 25, 30, 35, 40]:
        order = post(client, "/api/orders", booking).json()
        for stage in ["PACKED", "OUT_FOR_DELIVERY", "DELIVERED"]:
            order = post(
                client,
                f'/api/console/orders/{order["id"]}/fulfilment',
                {"state": stage, "expected_version": order["version"]},
            ).json()
        with transaction() as s:
            row = s.get(Order, order["id"])
            row.created_at = stamp(now() - timedelta(minutes=duration))
            row.delivered_at = stamp()
    with transaction() as s:
        result = forecast(s, s.get(Order, order["id"]), "API_TIMEOUT")
        assert result["sample_count"] == 5 and result[
            "delivery_minutes"
        ] == pytest.approx(32, abs=0.01)
        assert "moving average" in result["source"]
