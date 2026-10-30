import uuid
import pytest
from sqlalchemy import create_engine, event
from fastapi.testclient import TestClient
from backend import db, main
from backend.services import core


@pytest.fixture
def client(tmp_path, monkeypatch):
    password = uuid.uuid4().hex
    monkeypatch.setenv("OPERATOR_PASSWORD", password)
    engine = create_engine(
        f'sqlite:///{(tmp_path / "test.db").as_posix()}',
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def setup(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")

    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(core, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)
    core.initialize()
    c = TestClient(main.app)
    login = c.post("/api/console/login", json={"password": password})
    c.headers.update(
        {
            "Authorization": "Bearer " + login.json()["token"],
            "X-Customer-Session": "customer-test-session-" + uuid.uuid4().hex,
        }
    )
    yield c
    c.close()
    engine.dispose()


@pytest.fixture
def booking():
    return {
        "user_name": "Test Customer",
        "phone": "DEMO_CONTACT",
        "address": "DEMO_LOCATION",
        "contact_mode": "demo",
        "pincode": "560038",
        "payment_method": "UPI",
        "items": [{"product_id": "PROD-109", "qty": 1}],
    }


def post(client, path, body, key=None):
    return client.post(
        path, json=body, headers={"Idempotency-Key": key or str(uuid.uuid4())}
    )


def force(client, error):
    config = client.get("/api/console/settings").json()
    config["force_error"] = error
    return client.post("/api/console/settings", json=config)


def make_incident(client, booking, error):
    force(client, error)
    order = post(client, "/api/orders", booking).json()
    queue = client.get("/api/console/incidents").json()["items"]
    inc = next(i for i in queue if i["order_id"] == order["id"])
    return order, client.get("/api/console/incidents/" + inc["id"]).json()


def perform(client, inc, action, endpoint="action", confirmed=False, key=None):
    return post(
        client,
        f'/api/console/incidents/{inc["id"]}/{endpoint}',
        {
            "action": action,
            "expected_version": inc["version"],
            "note": "Test evidence checked",
            "confirmed": confirmed,
        },
        key,
    )
