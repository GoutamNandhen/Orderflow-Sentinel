# Policy and KPI definitions

## Priority

P1 if **any** cart item is critical, deadline is within the configurable close window (default 12 minutes), money is debited without confirmation, or attempt_count ≥3. Mixed carts use the highest rule priority. P2 if amount reaches configurable high-value threshold (default ₹5,000) or the cart has at least five distinct items (documented high-impact proxy). P3 otherwise. Recovery preserves P1. Model confidence never lowers P1.

## Action-specific risk

```text
risk = 0.40 × impact
     + 0.25 × (1 − confidence) × 100
     + 0.20 × min(amount_rupees / 5000 × 100, 100)
     + 0.15 × no_undo
```

Impact: P1=100, P2=60, P3=20. CAPTURED or DEBIT_UNKNOWN payments add a documented 10-point charged-customer bump to impact, capped at 100. `no_undo=100` for REFUND/CANCEL and 0 for other actions; refund initiation is conservatively treated as irreversible. Clamp total to [0,100]. LOW ≤30; MED >30 and ≤60; HIGH >60. Decisions use full precision; UI shows both raw components and weighted contributions and recalculates for the selected action.

The policy confidence is the measured maximum error-class probability, **not** failure probability. Before training, probability is unavailable and policy uses confidence=0 to express worst-case uncertainty; UI explicitly labels rule fallback. This is not a fabricated model probability.

Decision precedence:
1. Confidence <0.70 **or** risk >60 → MANUAL.
2. Otherwise confidence ≥0.90 **and** risk ≤30 → AUTO.
3. Otherwise → ONE_CLICK.

Persisted settings can tighten the auto bounds; they cannot loosen the 0.90/30 defaults. Explicit restrictions then apply. Unmatched debit, duplicate-order and rejected-address incidents require manual review. REFUND/CANCEL, substitute/address/slot proposals and payment-link creation cannot run automatically. Store transfers need at least operator approval. Irreversible financial actions need confirmation regardless of the numerical mode. Selected-action probabilities never override prerequisites.

Example: insulin ₹1,500, confidence .96, CHECK_PAYMENT: impact 100; uncertainty 4; value 30; no_undo 0 → risk 47 (MED), yet manual because debit reconciliation has an explicit handling restriction. REFUND on the same evidence adds 15 → risk 62 (HIGH). A P1 label alone does not force HIGH risk.

## Dashboard denominators

All dashboard counts are all-time **within the selected local database**, not invented daily comparisons.

| KPI | Definition |
|---|---|
| Total orders | Count of accepted persisted bookings; retries and duplicates excluded |
| Initial booking success | Bookings with initial_failed=false / all bookings |
| Initial failures | Count of bookings with initial_failed=true, unchanged after recovery |
| Recovered orders | Unique initially failed bookings with a resolved incident, whose order is neither cancelled nor refunded |
| Eventual recovery rate | Recovered initially failed bookings / initial failures; unavailable if no failures |
| Open incidents | All incidents with status other than RESOLVED, including refund-pending and escalated |
| Open P1 | Open incidents whose persisted priority is P1 |
| Auto-resolved | Resolved incidents with resolved_by=ENGINE |
| Average resolution | Mean actual time_to_fix_sec for resolved incidents only; pending time excluded |
| Money at risk | Order amounts for open incidents whose payment is CAPTURED or DEBIT_UNKNOWN |
| Hourly trend | Incidents detected in each UTC hour bucket, displayed at browser local time; recovered count in that cohort |
| Handling split | Current persisted handling decisions across all incidents; decisions can change |
| Risk distribution | Latest persisted actual-action risk tiers across all incidents |

The recovery numerator deduplicates order IDs and includes only initial failures, so later monitoring incidents on initially healthy orders cannot inflate the rate. Resolution history excludes open incidents, preserves P1 and uses the same filters as CSV. Exports include all matching rows up to a documented 10,000-row cap; UI pages contain 25 records (API maximum 100).
