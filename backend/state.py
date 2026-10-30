"""Legal order and fulfilment transitions, checked on every ORM flush."""

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from .models import Order

ORDER_TRANSITIONS = {
    "PLACED": {
        "PAYMENT_PENDING",
        "CONFIRMED",
        "FAILED",
        "DELAYED",
        "AUTO_FIXING",
        "WAITING_APPROVAL",
        "MANUAL_REVIEW",
        "CANCELLED",
    },
    "PAYMENT_PENDING": {
        "CONFIRMED",
        "FAILED",
        "AUTO_FIXING",
        "WAITING_APPROVAL",
        "MANUAL_REVIEW",
        "CANCELLED",
    },
    "CONFIRMED": {
        "DELAYED",
        "FAILED",
        "AUTO_FIXING",
        "WAITING_APPROVAL",
        "MANUAL_REVIEW",
        "RESOLVED",
        "CANCELLED",
    },
    "FAILED": {
        "AUTO_FIXING",
        "WAITING_APPROVAL",
        "MANUAL_REVIEW",
        "CONFIRMED",
        "CANCELLED",
    },
    "DELAYED": {
        "AUTO_FIXING",
        "WAITING_APPROVAL",
        "MANUAL_REVIEW",
        "CONFIRMED",
        "RESOLVED",
        "CANCELLED",
    },
    "AUTO_FIXING": {
        "CONFIRMED",
        "RESOLVED",
        "FAILED",
        "DELAYED",
        "WAITING_APPROVAL",
        "MANUAL_REVIEW",
        "CANCELLED",
    },
    "WAITING_APPROVAL": {
        "CONFIRMED",
        "RESOLVED",
        "PAYMENT_PENDING",
        "AUTO_FIXING",
        "MANUAL_REVIEW",
        "CANCELLED",
    },
    "MANUAL_REVIEW": {
        "CONFIRMED",
        "RESOLVED",
        "PAYMENT_PENDING",
        "AUTO_FIXING",
        "WAITING_APPROVAL",
        "CANCELLED",
    },
    "RESOLVED": {"CONFIRMED", "DELAYED", "MANUAL_REVIEW", "CANCELLED"},
    "CANCELLED": {"REFUNDED"},
    "REFUNDED": set(),
}
FULFILMENT_TRANSITIONS = {
    "UNFULFILLED": {"PACKED"},
    "PACKED": {"OUT_FOR_DELIVERY"},
    "OUT_FOR_DELIVERY": {"DELIVERED"},
    "DELIVERED": set(),
}


@event.listens_for(Session, "before_flush")
def enforce_transitions(session, *_):
    for order in session.new | session.dirty:
        if not isinstance(order, Order):
            continue
        for name, graph in [
            ("status", ORDER_TRANSITIONS),
            ("fulfilment", FULFILMENT_TRANSITIONS),
        ]:
            value = getattr(order, name)
            if value is None and order in session.new:
                continue
            if value not in graph:
                raise ValueError(f"Unknown {name}: {value}")
            history = inspect(order).attrs[name].history
            if history.deleted and history.added and history.deleted[0] != value:
                previous = history.deleted[0]
                if value not in graph[previous]:
                    raise ValueError(
                        f"Illegal {name} transition: {previous} -> {value}"
                    )
