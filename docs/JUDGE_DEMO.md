# Five-order judge walkthrough

Start with a **fresh separate demo database**, trained artifacts and both localhost applications in one browser profile. Sign in to Sentinel using your private configured operator credential (see README). Normal data must not be cleared. Create a fresh file with `scripts/demo_data.py`; it refuses overwrites. The block indicator must say next #1 of 5. Keep both tabs open.

| Booking | Product / inputs | Initial outcome | Actual recovery |
|---|---|---|---|
| 1 | Amul Milk & Sourdough combo, UPI, 40-minute promise | CONFIRMED | No incident; not yet delivered |
| 2 | Same noncritical combo, UPI | API timeout; model and risk evaluated | AUTO if real maximum class probability ≥.90 and risk ≤30; first persistent retry normally succeeds after 1 second |
| 3 | Same combo, UPI | CONFIRMED | No incident |
| 4 | Humalog insulin, UPI | Unmatched debit, P1 | Manual ledger reconciliation, then explicit confirmed refund or order confirmation |
| 5 | Amul combo, UPI | Stock mismatch, P3 | ONE_CLICK same-item store reassignment; alternatively offer equal-price substitute and wait for customer acceptance |

Leave **Use anonymized demo contact** selected at checkout. It sends the explicit `DEMO_CONTACT` and `DEMO_LOCATION` markers, not a phone number or residential address. Use the generic demo service-area pincode shown by the form. Product totals are database prices, no extra fee. Nothing is charged or delivered externally. The ordinary default first block already selects these errors. Later failing bookings rotate through all ten types.

For a repeatable named scenario after other demo activity, the console's **Simulate New Order → Judge five-order scripted error profile** selects the same types by block position and insulin on position 4. It is explicitly labelled as an override, and uses the same sequence/service. It **does not set model confidences or risk scores**. Use a fresh database to ensure five positions start at 1. Synthetic measured inference for the shipped seed/version qualified the timeout for AUTO and the stock transfer for ONE_CLICK; different retraining changes must be inspected honestly rather than forcing scores.

Inspect booking 4 in the Incident Queue. Its P1 urgency is retained even though CHECK_PAYMENT risk may be MED. One-click approval is disabled by the manual-debit restriction. Choose **CHECK PAYMENT → Execute CHECK PAYMENT** and record a note. The simulated ledger changes DEBIT_UNKNOWN to CAPTURED without a new charge and the incident stays open. Then choose either:

- **CONFIRM ORDER → Execute**: resolves to CONFIRMED, fulfilment remains UNFULFILLED.
- **REFUND → Execute REFUND → Confirm & Execute**: captured-debit prerequisites and selected-action risk are rechecked; refund remains PENDING, order CANCELLED and incident REFUND_PENDING. After five real seconds, the persisted simulated-settlement job marks refund COMPLETED, order REFUNDED and incident RESOLVED. Show the pending state in ShopEase first.

For booking 5, **Approve Suggested** transfers the same items to the demo backup hub. To demonstrate acceptance instead, select **OFFER SUBSTITUTE → Execute OFFER SUBSTITUTE**. Incident remains open, no inventory/product change yet. In ShopEase Live Tracking select order 5 and **Accept Change**; stock and equal-price substitution are applied atomically, and both tabs show resolution. Declining keeps the order in manual review. Medicines and infant formula never offer substitutes.

Show actual duration in the audit timeline/history, initial failures remaining 3/5, recovered counts separately from refunds, analytics from the database, actual socket status and retraining job results. Use Orders → Simulate next delivery step to advance PACKED, OUT_FOR_DELIVERY, DELIVERED one at a time. This is simulated fulfilment and does not follow automatically from incident resolution.

Other demonstrations: settings can force any of the ten errors once; address correction requires pincode 560039 (explicit pickup-desk lookup) and customer acceptance. Set retry failures to 3 and force API_TIMEOUT to demonstrate 1s/2s/4s backoff and P1 escalation. Five technical gateway failures in a rolling minute open its circuit; after 30 seconds test a half-open probe. These are explicit service fixtures, not fake model outputs.
