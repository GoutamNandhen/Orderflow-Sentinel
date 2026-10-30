"""Offline local fixtures, not real provider integrations."""

ADDRESS_LOOKUP = {
    "560039": {
        "address": "DEMO_PICKUP_LOCATION",
        "pincode": "560038",
    }
}


def payment_result(error_type, method):
    if method == "COD":
        return "NOT_REQUIRED"
    if error_type in ("UNMATCHED_DEBIT", "DUPLICATE_ORDER"):
        return "DEBIT_UNKNOWN"
    if error_type == "PAYMENT_DECLINED":
        return "DECLINED"
    return "CAPTURED"


def retry_result(order):
    return order.attempt_count > order.recovery_failures


def backup_store(order):
    return {
        "name": "Koramangala Demo Hub",
        "same_items_available": True,
        "source": "local simulated inventory fixture",
    }
