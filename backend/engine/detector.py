def detect(
    error_type, response_time_ms=0, http_status=200, stuck=False, unmatched_debit=False
):
    signals = []
    if http_status >= 400:
        signals.append(f"HTTP {http_status}")
    if response_time_ms >= 5000:
        signals.append("Response time at least 5 seconds")
    if stuck:
        signals.append("Order stuck past monitoring threshold")
    if unmatched_debit:
        signals.append("Debit is unmatched in local payment ledger")
    if error_type:
        signals.append(f"Simulated service signal: {error_type}")
    return signals
