# Anonymous demonstration data

The published project uses `DEMO_CONTACT`, `DEMO_LOCATION` and `DEMO_PICKUP_LOCATION` instead of example telephone numbers and residential addresses. Checkout selects anonymous demo mode by default. The API requires the exact non-personal markers in that mode; customer mode retains mobile-number validation.

Console demo creation, test fixtures, cloud verification and restart verification all use the anonymous markers. Service-area names and pincodes describe the simulated operating region, not a customer residence.

The approved HTML reference copy in this repository has also been anonymized. Its contact fields and customer names use demo labels; the original file supplied outside the project was left untouched. All 21 local screenshots were regenerated from this anonymized source on 30 October 2026 and individually inspected. The two full browser tests and the actual backend restart verification passed.

Automatic approval review continued to reject public screenshot-binary uploads after inspection. Screenshots therefore remain in the local deliverables and are excluded from the repository. The versioned browser and restart scripts reproduce them; this does not affect the runnable application.

Runtime databases, customer/session records, operator credentials, environment files, browser authentication state, logs and test traces remain local or in private hosting storage and are excluded from Git.
