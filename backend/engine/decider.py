RESTRICTED = {
    "REFUND",
    "CANCEL",
    "OFFER_SUBSTITUTE",
    "NEW_SLOT",
    "CORRECT_ADDRESS",
    "SEND_PAYMENT_LINK",
}


def decide(confidence, risk, action, settings, error_type=""):
    if confidence < 0.70 or risk > 60:
        return "MANUAL"
    if error_type in ("UNMATCHED_DEBIT", "DUPLICATE_ORDER", "ADDRESS_REJECTED"):
        return "MANUAL"
    if (
        action not in RESTRICTED
        and confidence >= settings["auto_confidence"]
        and risk <= settings["auto_risk"]
    ):
        return "AUTO"
    return "ONE_CLICK"
