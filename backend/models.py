from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    LargeBinary,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, stamp


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]
    category: Mapped[str]
    price: Mapped[int]
    stock: Mapped[int]
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(default="")
    icon: Mapped[str] = mapped_column(default="Package")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(primary_key=True)
    customer_session: Mapped[str] = mapped_column(index=True)
    tracking_token: Mapped[str] = mapped_column(unique=True)
    user_name: Mapped[str]
    phone: Mapped[str]
    address: Mapped[str]
    pincode: Mapped[str]
    items: Mapped[list] = mapped_column(JSON)
    amount: Mapped[int]
    payment_method: Mapped[str]
    category: Mapped[str]
    priority: Mapped[str]
    status: Mapped[str]
    fulfilment: Mapped[str] = mapped_column(default="UNFULFILLED")
    promised_by: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=stamp)
    updated_at: Mapped[str] = mapped_column(default=stamp)
    delivered_at: Mapped[str | None]
    attempt_count: Mapped[int] = mapped_column(default=0)
    booking_seq: Mapped[int] = mapped_column(unique=True)
    version: Mapped[int] = mapped_column(default=1)
    initial_failed: Mapped[bool] = mapped_column(default=False)
    simulator_override: Mapped[bool] = mapped_column(default=False)
    profile: Mapped[str] = mapped_column(default="normal")
    recovery_failures: Mapped[int] = mapped_column(default=0)
    reservation_active: Mapped[bool] = mapped_column(default=True)
    pending_offer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    customer_message: Mapped[str] = mapped_column(
        default="Booking accepted. Payment and fulfilment are simulated."
    )
    gateway: Mapped[str] = mapped_column(default="DemoPay Primary")
    distance_km: Mapped[float] = mapped_column(default=3.0)


class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    error_code: Mapped[str]
    error_type: Mapped[str]
    message: Mapped[str]
    detected_at: Mapped[str] = mapped_column(default=stamp)
    anomaly_score: Mapped[float | None]
    xgb_fail_prob: Mapped[float | None]
    xgb_error_class: Mapped[str | None]
    predicted_delay_min: Mapped[float]
    confidence: Mapped[float]
    risk_score: Mapped[float]
    risk_tier: Mapped[str]
    priority: Mapped[str]
    decision: Mapped[str]
    suggested_action: Mapped[str]
    explanation: Mapped[dict] = mapped_column(JSON)
    model_output: Mapped[dict] = mapped_column(JSON)
    risk_breakdown: Mapped[dict] = mapped_column(JSON)
    forecast: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(default="OPEN")
    resolved_at: Mapped[str | None]
    resolved_by: Mapped[str | None]
    time_to_fix_sec: Mapped[float | None]
    version: Mapped[int] = mapped_column(default=1)


class ActionLog(Base):
    __tablename__ = "actions_log"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    action: Mapped[str]
    done_by: Mapped[str]
    attempt_no: Mapped[int] = mapped_column(default=0)
    result: Mapped[str]
    before_status: Mapped[str]
    after_status: Mapped[str]
    note: Mapped[str] = mapped_column(default="")
    timestamp: Mapped[str] = mapped_column(default=stamp)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    operator_decision: Mapped[str]
    chosen_action: Mapped[str]
    comment: Mapped[str]
    timestamp: Mapped[str] = mapped_column(default=stamp)


class Gateway(Base):
    __tablename__ = "gateway_health"
    gateway_name: Mapped[str] = mapped_column(primary_key=True)
    last_errors_1min: Mapped[int] = mapped_column(default=0)
    circuit_state: Mapped[str] = mapped_column(default="CLOSED")
    errors: Mapped[list] = mapped_column(JSON, default=list)
    opened_at: Mapped[str | None]
    probe_claimed: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[str] = mapped_column(default=stamp)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    status: Mapped[str]
    amount: Mapped[int]
    attempt_count: Mapped[int] = mapped_column(default=1)
    reconciled: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[str] = mapped_column(default=stamp)


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[str] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    status: Mapped[str] = mapped_column(default="PENDING")
    amount: Mapped[int]
    created_at: Mapped[str] = mapped_column(default=stamp)
    settled_at: Mapped[str | None]


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    kind: Mapped[str]
    message: Mapped[str]
    timestamp: Mapped[str] = mapped_column(default=stamp)
    late: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("order_id", "kind"),)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str]
    order_id: Mapped[str | None]
    incident_id: Mapped[str | None]
    due_at: Mapped[str]
    expected_version: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(default="PENDING")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Idempotency(Base):
    __tablename__ = "idempotency"
    key: Mapped[str] = mapped_column(primary_key=True)
    digest: Mapped[str]
    response: Mapped[dict] = mapped_column(JSON)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[str]
    timestamp: Mapped[str] = mapped_column(default=stamp)
    order_id: Mapped[str | None]
    incident_id: Mapped[str | None]
    entity_version: Mapped[int]
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class OperatorSession(Base):
    __tablename__ = "operator_sessions"
    token: Mapped[str] = mapped_column(primary_key=True)
    expires_at: Mapped[str]


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"
    version: Mapped[str] = mapped_column(primary_key=True)
    bundle: Mapped[bytes] = mapped_column(LargeBinary)
    report: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=stamp)
