# Client trial checkout restoration — 2026-09-05

Code commit: e28a03d7. Production baseline: 4d1bc207 (including the public child-trial calendar restoration).

The client dashboard omitted trial purchase offers when no compatible subscription or unit-payment price was available. Checkout availability now includes a positive trial price and the selected participant's trial permission. Adult participation must still be explicitly enabled on a children's class. Capacity, adult quota, subscription coverage, renewal and past-session restrictions remain enforced. The reservation-options endpoint remains authoritative for eligibility and the single-trial rule; trial-only offers cannot fall back to a credit booking if that endpoint fails.

Validation: 17 frontend tests passed locally and in the deployed image; TypeScript and production build passed. Compared 548 production source files with the baseline immediately before rollout and with e28a03d7 after rollout: no differences. Only frontend restarted; backend image and creation time unchanged. Login and public child-trial calendar return HTTP 200; calendar currently contains 14 unique session links (earlier snapshot contained 10, so fixed-count assertion was not retained). No booking, payment or email was performed for testing.

Deployed frontend image: sha256:57d503ae8eeeeb0e2b25fa8157a26cf3eaa49d674f32906ed6a6713a96e96c1a.

Rollback image: piano-client-trial-checkout-rollback-frontend:4d1bc207. Source backup: /home/ubuntu/client-trial-checkout-20260905/pre-rollout-4d1bc207.tgz. Restore the affected source files and prior image together if needed; preserve concurrent production changes first.
