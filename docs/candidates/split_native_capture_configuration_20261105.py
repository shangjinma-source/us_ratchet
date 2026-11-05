"""Unactivated server configuration for native capture -> protected daily admission."""
from pathlib import Path
import json
from core.strategy_account_ledger import canonical,require
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.saved_frontier_policy_archive import _read as bounded_read, _research_root
from data.strategy_daily_session_capture import reject_links
from docs.candidates.split_native_capture_review_20261105 import NativeCaptureReview,digest
from docs.candidates.split_native_month_capture_20261105 import NativeMonthCaptureReader
from docs.candidates.split_native_rolling_admission_20261105 import NativeSplitRollingAdmission

# Fixed conservative local-import inventory; includes inactive branches, not a claim
# that every imported function executes. No request-time dependency discovery.
SOURCE_PATHS=frozenset({
 'backtest/affordable_support_seeds.py',
 'backtest/continuous_guided_account_decision.py',
 'backtest/continuous_quantity_candidates.py',
 'backtest/current_quantity_v2_risk_overlays.py',
 'backtest/log_concave_integer_search.py',
 'backtest/partial_trend_exposure.py',
 'backtest/quantity_training_upper_bound.py',
 'backtest/return_priority_exact_floor_ceil_research.py',
 'backtest/return_priority_fresh_cash_quantity_search.py',
 'backtest/return_priority_fresh_cash_quantity_search_v2.py',
 'backtest/return_priority_joint_candidate_generator_research.py',
 'backtest/return_priority_monthly_training_inputs.py',
 'backtest/saved_quantity_candidate_comparison.py',
 'core/monthly_peak_exit.py',
 'core/saved_monthly_frontier_proposal.py',
 'core/strategy_account_difference.py',
 'core/strategy_account_ledger.py',
 'core/strategy_account_split_store_v1.py',
 'core/strategy_account_split_v1.py',
 'core/strategy_account_store.py',
 'core/strategy_monthly_target_store.py',
 'core/strategy_split_risk_projection_v1.py',
 'data/current_cash_portfolio_research.py',
 'data/current_portfolio_preview.py',
 'data/current_quantity_portfolio_research.py',
 'data/current_quantity_portfolio_research_v2.py',
 'data/current_quantity_projection_v2.py',
 'data/current_quantity_v2_bounded_unit_review.py',
 'data/current_quantity_v2_continuation_service.py',
 'data/current_quantity_v2_current_cash_continuation.py',
 'data/current_quantity_v2_current_cash_ledger_adapter.py',
 'data/current_quantity_v2_current_cash_plan.py',
 'data/current_quantity_v2_current_cash_sources.py',
 'data/current_quantity_v2_difference_plan.py',
 'data/current_quantity_v2_difference_service.py',
 'data/current_quantity_v2_execution_month.py',
 'data/current_quantity_v2_monthly_bounded_review.py',
 'data/current_quantity_v2_monthly_capture_audit.py',
 'data/current_quantity_v2_monthly_composition.py',
 'data/current_quantity_v2_monthly_continuation_factory.py',
 'data/current_quantity_v2_monthly_continuation_sources.py',
 'data/current_quantity_v2_monthly_decision.py',
 'data/current_quantity_v2_monthly_factory.py',
 'data/current_quantity_v2_monthly_origins.py',
 'data/current_quantity_v2_monthly_research_service.py',
 'data/current_quantity_v2_monthly_retarget.py',
 'data/current_quantity_v2_monthly_service.py',
 'data/current_quantity_v2_monthly_sources.py',
 'data/current_quantity_v2_monthly_training.py',
 'data/current_quantity_v2_monthly_training_reader.py',
 'data/current_quantity_v2_paper_action_sources.py',
 'data/current_quantity_v2_paper_chain.py',
 'data/current_quantity_v2_paper_ledger.py',
 'data/current_quantity_v2_paper_review.py',
 'data/current_quantity_v2_paper_review_provider.py',
 'data/current_quantity_v2_paper_service.py',
 'data/current_quantity_v2_pullback_cap_store.py',
 'data/current_quantity_v2_pullback_entry.py',
 'data/current_quantity_v2_pullback_proof.py',
 'data/current_quantity_v2_pullback_runtime.py',
 'data/current_quantity_v2_pullback_sources.py',
 'data/current_research_capital_decision.py',
 'data/current_research_capital_decision_v2.py',
 'data/current_research_close_panel.py',
 'data/current_research_intraday_cap_store.py',
 'data/current_research_intraday_execution.py',
 'data/current_research_intraday_journal.py',
 'data/current_research_ohlc_panel.py',
 'data/current_research_snapshot_resolver.py',
 'data/current_top1_portfolio_research.py',
 'data/frontier_monthly_peak_raw_history_v1.py',
 'data/monthly_peak_exit_history.py',
 'data/monthly_peak_exit_store.py',
 'data/monthly_peak_raw_history.py',
 'data/monthly_risk_epoch.py',
 'data/official_rss_gzip_transport_v1.py',
 'data/saved_frontier_buy_data_wait_preview_v1.py',
 'data/saved_frontier_capture_review_v1.py',
 'data/saved_frontier_daily_composition_v1.py',
 'data/saved_frontier_exit_packet_v1.py',
 'data/saved_frontier_first_window_v1.py',
 'data/saved_frontier_live_reader_v1.py',
 'data/saved_frontier_policy_archive.py',
 'data/saved_frontier_preview_service_v1.py',
 'data/saved_frontier_security_domain_v1.py',
 'data/saved_frontier_source_reader_v1.py',
 'data/saved_frontier_source_review_v1.py',
 'data/saved_frontier_supplement_prepare_v1.py',
 'data/saved_frontier_supplement_request_v1.py',
 'data/saved_frontier_zero_cash_preview_v1.py',
 'data/strategy_account_action_capture.py',
 'data/strategy_account_action_capture_v3.py',
 'data/strategy_account_action_capture_v6.py',
 'data/strategy_account_evidence_provider.py',
 'data/strategy_account_execution_limits.py',
 'data/strategy_account_identity.py',
 'data/strategy_account_live_pullback_cap_store.py',
 'data/strategy_account_live_pullback_entry.py',
 'data/strategy_account_live_pullback_runtime.py',
 'data/strategy_account_live_pullback_sources.py',
 'data/strategy_account_mark_reference.py',
 'data/strategy_account_market_capture.py',
 'data/strategy_account_market_capture_v2.py',
 'data/strategy_account_monthly_release.py',
 'data/strategy_account_notice_review.py',
 'data/strategy_account_preview.py',
 'data/strategy_account_quote_clock.py',
 'data/strategy_account_runtime.py',
 'data/strategy_account_split_migration_v1.py',
 'data/strategy_account_target_decision.py',
 'data/strategy_account_target_inputs.py',
 'data/strategy_account_target_service.py',
 'data/strategy_account_unit_review.py',
 'data/strategy_continuous32_target_decision.py',
 'data/strategy_daily_buy_data_wait_bridge_v1.py',
 'data/strategy_daily_continuity_normalizer.py',
 'data/strategy_daily_domain_policy_review_v1.py',
 'data/strategy_daily_evidence_adapter.py',
 'data/strategy_daily_evidence_rebind.py',
 'data/strategy_daily_execution_bridge.py',
 'data/strategy_daily_first_window_v4.py',
 'data/strategy_daily_market_capture_v3.py',
 'data/strategy_daily_mixed_execution_bridge.py',
 'data/strategy_daily_profile_binding.py',
 'data/strategy_daily_rebound_archive.py',
 'data/strategy_daily_rolling_parent_v3.py',
 'data/strategy_daily_security_domain_v1.py',
 'data/strategy_daily_session_capture.py',
 'data/strategy_daily_signal_verifier.py',
 'data/strategy_daily_target_gate.py',
 'data/strategy_execution_halt_evidence_v1.py',
 'data/strategy_halt_aware_execution_limits_v1.py',
 'data/strategy_halt_aware_pullback_cap_store_v1.py',
 'data/strategy_halt_aware_pullback_cap_store_v2.py',
 'data/strategy_halt_aware_pullback_entry_v1.py',
 'data/strategy_halt_aware_pullback_sources_v1.py',
 'data/strategy_halt_gap_diagnostic_v1.py',
 'data/strategy_halt_gzip_capture_v1.py',
 'data/strategy_monthly_supplement_gzip_v1.py',
 'data/strategy_monthly_target_service.py',
 'data/strategy_recent_minute_retry_v1.py',
 'data/strategy_recorded_split_review_v1.py',
 'data/strategy_rss_gzip_capture_v1.py',
 'data/strategy_rss_verified_transport_v3.py',
 'data/strategy_split_history_projection_v1.py',
 'data/strategy_split_native_projection_v1.py',
 'docs/candidates/split_calendar_extension_20261105.py',
 'docs/candidates/split_frontier_supplement_20261105.py',
 'docs/candidates/split_monthly_raw_history_20261105.py',
 'docs/candidates/split_native_capture_configuration_20261105.py',
 'docs/candidates/split_native_capture_review_20261105.py',
 'docs/candidates/split_native_daily_composition_20261105.py',
 'docs/candidates/split_native_daily_execution_bridge_20261105.py',
 'docs/candidates/split_native_month_capture_20261105.py',
 'docs/candidates/split_native_month_daily_20261105.py',
 'docs/candidates/split_native_rolling_admission_20261105.py',
 'docs/candidates/split_production_admission_20261105.py',
 'docs/candidates/split_saved_frontier_daily_evidence_20261105.py',
 'docs/candidates/split_three_clock_action_review_20261105.py',
 'docs/candidates/split_three_clock_coordinates_20261105.py',
 'docs/candidates/split_three_clock_daily_composition_20261105.py',
 'docs/candidates/split_three_clock_daily_evidence_20261105.py',
 'docs/candidates/strategy_account_split_evidence_provider.py',
 'docs/candidates/strategy_account_split_market_capture.py',
 'docs/candidates/strategy_account_split_scoped_preview.py',
 'docs/candidates/strategy_account_split_target_inputs.py',
 'docs/candidates/strategy_account_split_unit_review.py',
 'docs/candidates/strategy_split_daily_execution_bridge.py',
 'docs/candidates/strategy_split_frontier_preview_service.py',
 'scripts/current_research_official_alert_capture.py',
 'scripts/return_priority_current_rebased_training.py',
 'scripts/return_priority_latest_saved_snapshot_research.py',
})
CODE_ROOT=Path(__file__).resolve().parents[2]

class ConfiguredNativeAdmission:
 def __init__(self,*,root,configuration_path,configuration_sha256,monthly,monthly_view,
              research_root,risk_path,capture_root,clock,validate_runtime,
              fetch_daily=None,fetch_official=None):
  reject_links(Path(root));self.root=Path(root).resolve();self.config_path=configuration_path;self.expected=configuration_sha256
  self.monthly,self.monthly_view=monthly,monthly_view
  require(monthly_view.monthly is monthly,'NATIVE_CONFIG_MONTHLY_IDENTITY')
  self.research_root=_research_root(research_root)
  risk=Path(risk_path);reject_links(risk);risk=risk.resolve()
  require(risk.is_relative_to(self.research_root) and risk.is_file() and risk.stat().st_nlink==1,'NATIVE_CONFIG_RISK_ISOLATION')
  self.risk=MonthlyPeakExitStore(risk);self.capture_root=capture_root
  self.clock,self.runtime_gate=clock,validate_runtime
  self.fetch_daily,self.fetch_official=fetch_daily,fetch_official
  self.service=self
  self.validate_code()

 def _read(self,name):
  candidate=self.root/name;reject_links(candidate);path=candidate.resolve()
  require(path.is_relative_to(self.root),'NATIVE_CONFIG_PATH_ESCAPE')
  return bounded_read(path,maximum=8*1024*1024)

 def validate_code(self):
  self.runtime_gate()
  raw=self._read(self.config_path);require(digest(raw)==self.expected,'NATIVE_CONFIG_CHANGED')
  configuration=json.loads(raw)
  require(configuration['schema']=='NATIVE_CAPTURE_RUNTIME_CANDIDATE_V1' and configuration['production_activated'] is False,'NATIVE_CONFIG_SCHEMA')
  require(set(configuration['source_pins'])>=SOURCE_PATHS,'NATIVE_CONFIG_SOURCE_DOMAIN')
  for name,expected in configuration['source_pins'].items():
   actual=(CODE_ROOT/name).resolve();require(actual.is_relative_to(CODE_ROOT),'NATIVE_CONFIG_CODE_PATH')
   require(digest(self._read(name))==expected and digest(bounded_read(actual,maximum=8*1024*1024))==expected,'NATIVE_CONFIG_SOURCE_CHANGED')
  require(type(configuration['policy_execution_enabled']) is bool and configuration['policy_id']=='SPLIT_NATIVE_MONTH_CONTENT_ONLY_V1','NATIVE_CONFIG_RESEARCH_POLICY')
  for target_id,reference in configuration['authorizations'].items():
   raw=self._read(reference['path']);require(digest(raw)==reference['sha256'],'NATIVE_CONFIG_AUTH_CHANGED')
   grant=json.loads(raw);require(grant['target_id']==target_id,'NATIVE_CONFIG_AUTH_TARGET')
   require(set(reference['files'])==set(grant['source_sha256']),'NATIVE_CONFIG_AUTH_FILES')
   for key,path in reference['files'].items():require(digest(self._read(path))==grant['source_sha256'][key],'NATIVE_CONFIG_AUTH_SOURCE_CHANGED')
  return configuration

 def preview(self,*,expected_revision,target_id,expected_proposal_id):
  configuration=self.validate_code()
  require(target_id in configuration['authorizations'],'NATIVE_CONFIG_NEW_TARGET_AUTHORIZATION_REQUIRED')
  reference=configuration['authorizations'][target_id];raw=self._read(reference['path']);grant=json.loads(raw)
  files={key:self._read(path) for key,path in reference['files'].items()}
  reviewer=NativeCaptureReview(research_root=self.research_root,authorization_bytes=raw,authorization_sha256=reference['sha256'],files=files)
  context=dict(calendar=json.loads(files[grant['calendar']]),identities=json.loads(files[grant['identities']])['securities'])
  reader=NativeMonthCaptureReader(monthly_view=self.monthly_view,risk_store=self.risk,research_root=self.research_root,capture_root=self.capture_root,context_sha256=digest(canonical(context)),review_capture=reviewer,clock=self.clock,validate_sources=self.validate_code,fetch_daily=self.fetch_daily,fetch_official=self.fetch_official,**context)
  admission=NativeSplitRollingAdmission(monthly=self.monthly,monthly_view=self.monthly_view,reader=reader,clock=self.clock,validate_code=self.validate_code,timing_bundles=grant['timing_bundles'],policy_execution_enabled=configuration['policy_execution_enabled'],policy_id=configuration['policy_id'])
  result=admission.preview(expected_revision=expected_revision,target_id=target_id,expected_proposal_id=expected_proposal_id)
  self.validate_code()
  return result
