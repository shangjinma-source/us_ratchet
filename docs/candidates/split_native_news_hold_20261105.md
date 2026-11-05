# Native AI HOLD execution integration ¡ª 2026-11-05

Status: isolated integration passed; no production activation or account writes outside temporary test stores.

The real issue was not a missing attribute alone. The old news HOLD bridge expected a concrete daily composition, checked the legacy provider class, directly called its base `_assemble`, and inserted lineage into its training package. Adding `.provider/.reader/.fees` to the configured facade would retain incorrect execution semantics.

Minimal change:

- `NativeSplitRollingAdmission.protected_composition(...)` now assembles the same protected provider under the real monthly snapshot. It binds account revision, target and saved proposal, validates before/after and checks the snapshot remains unchanged. Normal preview also uses this context.
- `ConfiguredNativeAdmission.protected_composition(...)` selects the same exact authorized target, creates its actual source reviewer/reader and opens the rolling context. It does not expose arbitrary provider/reader attributes as substitutes. Config/source validation remains on both ends.
- `install_native_hold_risk_plan(...)` accepts an actual NewsInvestmentService, retains the original non-HOLD risk plan and the original HOLD checks via a private function dependency binding. Only the bridge and scoped account preview are replaced by split-aware versions. News-generation validation, exact domains, cash reconciliation, review expiry, original-risk validity and quote deadlines remain checked.
- `NativeNewsHoldBridge` reuses the native execution bridge with unchanged original signal. Only execution projection can decrease; quantities cannot exceed either actual holdings or strategy effective quantities. The true factory subclass `_assemble`, history/timing admission, halted-market transport and protected execution limits are retained. News lineage is separate from original training bytes.

Integration test `test_split_native_news_hold_20261105` uses the real profiled router, native target, source authority/capture, risk store and NewsInvestmentService.risk_plan_provider. Synthetic transport and grants remain explicit; no model is called. Temporary real ledger fills bring holdings to saved targets, cash is reconfirmed, and the actual ordinary preview returns HOLD. The news risk provider produces one-share sell-only reduction proposals. Raising the target is rejected; forcing the actual provider subclass gate to fail produces WAIT and verifies one gate call. The account, target, original preview and risk state remain unchanged during news execution.

Final authoritative HOLD run: session 3278, exit 0, 1 test, 137.808 seconds, including exact chosen-security SELL 1 and independent lineage/review digest checks. The subsequently added single unified-route source pin will be covered by root HTTP integration; no further HOLD runtime logic changed. Earlier session 93557 passed in 137.675 seconds. Earlier 56665 failed only because the test expected a non-null optional effective-target field in HOLD; the test now uses actual saved proposal quantities to form its review rows without changing the original preview.

Changed candidates: `split_native_rolling_admission_20261105.py`, `split_native_capture_configuration_20261105.py`. New files: `split_native_news_hold_20261105.py`, its test and this note. The configured source inventory includes these changed dependencies and the reused original news bridge/plan/service/review core. Previously frozen source files and live configuration are untouched. Fresh route composition must explicitly install the new risk provider before worker start; calendar-window integration is handled separately. This is not a claim of deployment, model profitability or broker-managed stop orders.

Scope clarification: directly invoking the actual service risk_plan_provider verifies its callback integration, not the full news API pre-analysis/source-binding workflow. No real model or news API authentication is claimed.
