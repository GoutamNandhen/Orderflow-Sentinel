import json
import os
import urllib.request


def explain(entry, priority, decision, action, risk):
    fallback = {
        "operator": [
            entry["explanation"],
            f"{priority}; {decision} handling for {action}; action risk {risk:.2f}/100.",
        ],
        "customer": entry["customer_message"],
        "source": "offline template / exact JSON playbook lookup",
    }
    key, model = os.getenv("GEMINI_API_KEY"), os.getenv("GEMINI_MODEL")
    if not key or not model:
        return fallback
    # Only established, non-personal facts leave the machine. No action tools.
    facts = {k: fallback[k] for k in ("operator", "customer")}
    try:
        body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Rewrite these established facts as JSON with operator (exactly two short strings) and customer (one string). Do not add claims, change decisions or scores: "
                            + json.dumps(facts)
                        }
                    ]
                }
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            raw = json.load(response)
        candidate = json.loads(raw["candidates"][0]["content"]["parts"][0]["text"])
        if (
            len(candidate["operator"]) == 2
            and all(isinstance(s, str) and len(s) <= 400 for s in candidate["operator"])
            and isinstance(candidate["customer"], str)
            and len(candidate["customer"]) <= 400
        ):
            # Keep authoritative numeric/policy facts visible even with prose adapter.
            return {
                **fallback,
                "optional_prose": candidate,
                "source": "template facts + optional Gemini prose (untrusted explanatory text)",
            }
    except Exception:
        pass
    return fallback
