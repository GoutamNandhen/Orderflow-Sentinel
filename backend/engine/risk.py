def calculate(priority, confidence, amount_paise, action, charged=False):
    base = {"P1": 100, "P2": 60, "P3": 20}[priority]
    impact = min(100, base + (10 if charged else 0))
    components = {
        "impact": impact,
        "uncertainty": (1 - confidence) * 100,
        "value_score": min(amount_paise / 100 / 5000 * 100, 100),
        "no_undo": 100 if action in ("REFUND", "CANCEL") else 0,
    }
    weights = {
        "impact": 0.40,
        "uncertainty": 0.25,
        "value_score": 0.20,
        "no_undo": 0.15,
    }
    contributions = {k: v * weights[k] for k, v in components.items()}
    score = min(100, max(0, sum(contributions.values())))
    return {
        "score": score,
        "tier": "LOW" if score <= 30 else "MED" if score <= 60 else "HIGH",
        "components": components,
        "weights": weights,
        "contributions": contributions,
        "charged_bump": 10 if charged else 0,
        "action": action,
    }
