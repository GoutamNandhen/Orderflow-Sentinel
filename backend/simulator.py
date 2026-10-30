import random
from .schemas import ERRORS


def choose(seq, settings):
    position = ((seq - 1) % 5) + 1
    if settings["force_error"]:
        return settings["force_error"], True
    if not settings["enabled"] or position not in settings["failing_positions"]:
        return None, False
    if settings["selection"] == "weighted":
        return (
            random.Random(settings["seed"] + seq).choices(
                ERRORS, weights=[5, 2, 1, 1, 2, 2, 1, 3, 1, 2]
            )[0],
            False,
        )
    # Rotate every error over failing bookings, keeping the first block familiar.
    rotation = [
        "API_TIMEOUT",
        "UNMATCHED_DEBIT",
        "OUT_OF_STOCK",
        "RATE_LIMIT",
        "TOKEN_EXPIRED",
        "ADDRESS_REJECTED",
        "PAYMENT_DECLINED",
        "DUPLICATE_ORDER",
        "STORE_CLOSED",
        "RIDER_LATE",
    ]
    previous = ((seq - 1) // 5) * len(settings["failing_positions"])
    previous += sum(p < position for p in settings["failing_positions"])
    return rotation[previous % len(rotation)], False
