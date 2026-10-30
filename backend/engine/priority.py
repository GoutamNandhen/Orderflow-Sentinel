from ..db import now, dt


def assign(order, error_type, settings):
    reasons = []
    if any(i["is_critical"] for i in order.items):
        reasons.append("Critical item in cart")
    if (dt(order.promised_by) - now()).total_seconds() <= settings[
        "close_deadline_minutes"
    ] * 60:
        reasons.append("Delivery deadline is close")
    if error_type == "UNMATCHED_DEBIT":
        reasons.append("Debit without confirmation")
    if order.attempt_count >= 3:
        reasons.append("Three recovery attempts")
    if reasons:
        return "P1", reasons
    if order.amount >= settings["high_value_paise"] or len(order.items) >= 5:
        return "P2", ["High value or large customer impact"]
    return "P3", ["Standard order"]
