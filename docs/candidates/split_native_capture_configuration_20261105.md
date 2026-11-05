# Native capture configured candidate — 2026-11-05

Status: isolated integration passed; not mounted, not production approval.

`ConfiguredNativeAdmission` is the single construction boundary. Its `service` is itself; `monthly`, `monthly_view`, `preview` and `validate_code` are available to the fresh route builder. No arbitrary `review_capture` parameter is exposed. Each target selects an exact authorization reference; a missing new-month authorization refuses instead of reusing the old target's grant.

The authorization drives actual `NativeCaptureReview` → `NativeMonthCaptureReader` → `NativeSplitRollingAdmission`. Calendar, identities, source files, per-security price basis and timing are hash-bound. Each validation rereads the configuration and source references, compares the fixed conservative local-import inventory with the actual repository and runtime-root bytes, and invokes the inherited monthly runtime gate. The fixed inventory includes imported inactive branches; it is not a claim that every function executes. Existing financial source authenticity remains conditional. No basis inference from adjusted close, no automatic approval of future broker evidence, no policy-name substitution.

The research directory and existing isolated risk SQLite are checked before capture. Construction never initializes a real risk database. The fixture explicitly provisions an empty SQLite, with no fabricated risk state, then uses real source admission to create risk state.

Validation: `PYTHONPATH=.;tests`, `D:/python/python.exe -m unittest test_split_native_capture_configuration_20261105 -v`.

Final session 37644: exit 0, one integrated test, 50.784 seconds. Earlier complete success 82495: 50.164 seconds. The final test uses actual SplitProfiledActivation, SplitProfiledRouter, saved proposal, native target archive, capture receipts, gzip RSS/halts, source normalization, risk persistence, and protected execution quotes. External source transport and authorization evidence are explicit synthetic fixtures. It returns READY with actual order suggestions, preserves account state, and rejects modified configuration/source, unknown target authorization, and absent risk database without risk mutation. This is not an HTTP fill test; the next agent owns that layer.

Reusable fixture: `tests/test_split_native_capture_configuration_20261105.py`, `Tests.case()` returns service, f, router, view, provider, timing (action-id map), request, state, configraw and constructor arguments. Its cleanup retains the temporary resources and transport patches until the consuming test finishes. No source approval, production activation, real-account operation, or order submission is implied.
