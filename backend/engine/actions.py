from ..schemas import ACTIONS
from ..services.adapters import ADDRESS_LOOKUP


def applicability(session, incident, order, payment, refund, playbook):
    allowed = set(playbook[incident.error_type]["candidate_actions"]) | {
        "NOTIFY_CUSTOMER",
        "ESCALATE",
        "CANCEL",
        "REFUND",
    }
    result = {}
    for action in ACTIONS:
        reason = None
        if incident.status == "RESOLVED":
            reason = "Incident is already resolved"
        elif order.fulfilment == "DELIVERED":
            reason = "Delivered orders cannot use this pre-delivery recovery workflow"
        elif action not in allowed:
            reason = "Action does not address this incident type"
        elif refund or order.status in ("CANCELLED", "REFUNDED"):
            reason = "Order is cancelled or refund is already pending/completed"
        elif action == "REFUND" and payment.status != "CAPTURED":
            reason = "Requires a reconciled captured debit; COD/unknown/declined cannot be refunded"
        elif action in (
            "SWITCH_GATEWAY",
            "SEND_PAYMENT_LINK",
        ) and payment.status not in ("DECLINED", "NOT_DEBITED"):
            reason = "Reconcile an unknown debit first; captured/COD payments cannot be charged again"
        elif action == "CONFIRM_ORDER" and payment.status not in (
            "CAPTURED",
            "NOT_REQUIRED",
        ):
            reason = "Payment must be reconciled or COD"
        elif action == "CANCEL" and payment.status in ("DEBIT_UNKNOWN", "CAPTURED"):
            reason = "Reconcile unknown debit or request a refund before cancellation"
        elif action == "RETRY" and order.attempt_count >= 3:
            reason = "Maximum three recovery attempts reached"
        elif action == "OFFER_SUBSTITUTE" and (
            any(i["category"] in ("Medicines", "Baby Food") for i in order.items)
            or len(order.items) != 1
        ):
            reason = "No medicine/infant substitutions; demo substitute requires one noncritical grocery item"
        elif action == "OFFER_SUBSTITUTE" and (
            order.items[0]["product_id"] not in ("PROD-109", "PROD-120")
        ):
            reason = "No verified equal-price substitute in the local demo catalogue"
        elif action == "CORRECT_ADDRESS" and order.pincode not in ADDRESS_LOOKUP:
            reason = (
                "No explicit demo lookup for this pincode; cannot invent an address"
            )
        elif order.pending_offer and action in (
            "OFFER_SUBSTITUTE",
            "NEW_SLOT",
            "CORRECT_ADDRESS",
        ):
            reason = "A customer acceptance request is already pending"
        result[action] = {"enabled": reason is None, "reason": reason}
    return result
