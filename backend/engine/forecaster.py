from sqlalchemy import select
from ..models import Order
from ..db import dt

PENALTIES = {
    "API_TIMEOUT": 2,
    "RATE_LIMIT": 3,
    "TOKEN_EXPIRED": 2,
    "ADDRESS_REJECTED": 12,
    "PAYMENT_DECLINED": 8,
    "UNMATCHED_DEBIT": 16,
    "DUPLICATE_ORDER": 12,
    "OUT_OF_STOCK": 14,
    "STORE_CLOSED": 15,
    "RIDER_LATE": 12,
}


def forecast(session, order, error_type):
    completed = session.scalars(
        select(Order)
        .where(Order.delivered_at.is_not(None))
        .order_by(Order.delivered_at.desc())
        .limit(20)
    ).all()
    durations = [
        (dt(o.delivered_at) - dt(o.created_at)).total_seconds() / 60 for o in completed
    ]
    enough = len(durations) >= 5
    baseline = sum(durations) / len(durations) if enough else 35.0
    penalty = PENALTIES.get(error_type, 0)
    promise = (dt(order.promised_by) - dt(order.created_at)).total_seconds() / 60
    return {
        "delivery_minutes": baseline + penalty,
        "delay_minutes": max(0, baseline + penalty - promise),
        "repair_seconds": None,
        "sample_count": len(durations),
        "error_penalty_minutes": penalty,
        "source": (
            "moving average, last 20 completed deliveries"
            if enough
            else "fallback: 35 minute simulated delivery baseline; fewer than five completions"
        ),
    }
