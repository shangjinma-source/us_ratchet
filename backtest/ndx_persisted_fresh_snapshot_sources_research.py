"""Byte-bound source fragments, not a complete prospective execution input.

No filesystem, network, clock, numerical executor or publication calls. References
are externally supplied anchors: equality to them is not proof of origin or PIT.
Unimplemented semantic joins remain explicit blockers even with all bytes present.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import PureWindowsPath, PurePosixPath
import csv
import io
import json

POLICY = 'FIRST_ACTUAL_OBSERVED_SESSION_GAPS_DO_NOT_CONSUME_MONTH'
ROLES = ('official_archive', 'official_receipt', 'membership', 'identity_taxonomy',
         'identity_audit', 'risk_evidence', 'original8', 'adjusted_prices',
         'nominal_prices', 'corporate_actions', 'target_nav', 'target_receipt',
         'target_currency', 'config', 'generator_contract', 'membership_scope')
FROZEN = {
 'executor_reference': ('backtest/ndx_persisted_fresh_snapshot_executor_research.py', 'ece6c32de5e052b9b12d8ac63d59b9096fb2234fb5b318a3d968ef2f156e77ce'),
 'computation_reference': ('backtest/ndx_dynamic_shadow_candidate_snapshot.py', 'b6ecd412a2e62fb625811101b4076d74150693a0cdc8c2b3fd0fd2d66388f93d'),
 'versioning_reference': ('data/versioning.py', 'a71abbf07e8cd1b35f5fa09f9842a15470553fc42e410fe97886c76711fef7df'),
 'generator_contract_reference': ('config/ndx_dynamic_shadow_candidate_generator_v1.yaml', '46a20fdec256bc0b4f72c8acc64f9ef59b2e80b0e23d6451f60f068b89b059f8'),
 'membership_scope_reference': ('config/ndx_membership_scope_research_v1.yaml', '3136387ea83523bd22068c7f70b282dcd44d9195efed985e630bcacd187f5d2a')}
ROOT = 'E:/Git/us_ratchet/'
FLAGS = dict.fromkeys(('source_origin_authenticated', 'point_in_time_verified',
 'registration_approved', 'clock_authenticity_verified', 'candidate_seal_allowed',
 'cohort_registration_allowed', 'execution_input_ready', 'executor_called',
 'fit_executed', 'account_executed', 'seal_executed', 'snapshot_published'), False)
FORMATS = {'official_archive': 'OFFICIAL_IMMUTABLE_CSV',
 'nominal_prices': 'SINGLE_FROZEN_NOMINAL_CSV', 'target_nav': 'FUND_NAV_CSV',
 'original8': 'FROZEN_ORIGINAL8_JSON', 'generator_contract': 'FROZEN_BYTES',
 'membership_scope': 'FROZEN_BYTES'}

def require(ok, message):
 if not ok: raise ValueError(message)

def reference(r):
 require(type(r) is dict and set(r) == {'path', 'sha256'}, 'Exact reference')
 p, h = r['path'], r['sha256']
 require(type(p) is str and p.strip() == p and (PureWindowsPath(p).is_absolute() or PurePosixPath(p).is_absolute()), 'Absolute reference path')
 require(type(h) is str and len(h) == 64 and set(h) <= set('0123456789abcdef'), 'SHA256 hex')
 return p, h

def object_pairs(pairs):
 result = {}
 for k, v in pairs:
  require(k not in result, 'Duplicate JSON key')
  result[k] = v
 return result

def document(raw):
 result = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=object_pairs,
                     parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
 require(type(result) is dict, 'JSON object')
 return result

def byte_store(artifacts):
 require(type(artifacts) is list, 'Explicit byte artifacts')
 store = {}
 for item in artifacts:
  require(type(item) is dict and set(item) == {'reference', 'raw_bytes'}, 'Byte artifact fields')
  p, h = reference(item['reference']); raw = item['raw_bytes']
  require(type(raw) is bytes and sha256(raw).hexdigest() == h, 'Same consumed bytes must match external SHA')
  require(p not in store, 'Duplicate artifact path, including conflicting hash')
  store[p] = (h, raw)
 return store

def take(store, r):
 p, h = reference(r)
 require(p in store and store[p][0] == h, 'Referenced original bytes required')
 return store[p][1]

def csv_rows(raw, financial=False, volume=False):
 reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
 header = next(reader, None)
 require(header and all(header) and len(header) == len(set(header)), 'Unique nonempty CSV header')
 rows = []
 for fields in reader:
  require(len(fields) == len(header), 'No truncated or extra CSV fields')
  rows.append(dict(zip(header, fields)))
 require(rows, 'Nonempty CSV')
 if financial:
  require({'Date', 'Close'} <= set(header) and (not volume or 'Volume' in header), 'Financial columns')
  previous = ''
  for r in rows:
   d = date.fromisoformat(r['Date']); require(d.isoformat() == r['Date'] and r['Date'] > previous, 'Canonical ascending unique source dates')
   previous = r['Date']
   for k in ('Open', 'High', 'Low', 'Close', 'Volume'):
    if k in r:
     n = Decimal(r[k]); require(n.is_finite() and (n >= 0 if k == 'Volume' else n > 0), 'Finite financial source value')
 return header, rows

def inspect_source_bundle(*, artifacts, role_bindings):
 """Validate confirmed original formats; never synthesize missing role schemas.

 Each binding is {format, reference, receipt_reference?}. Financial projections
 retain CSV strings, all rows, original manifest and zero-based CSV data-row locators.
 SINGLE_FROZEN_NOMINAL_CSV is deliberately not a complete ticker bundle.
 """
 store = byte_store(artifacts)
 require(type(role_bindings) is dict and set(role_bindings) <= set(ROLES), 'Known role names')
 projections, gaps = {}, [dict(role='calendar', reason='FROZEN_ECE6_REQUIRES_EXACTLY_FIVE_GAPS_IN_ENTIRE_HISTORY_NOT_ONLY_GENESIS_PREFIX;NEW_GAPS_REQUIRE_SEPARATE_CORE_VERSION'),
                          dict(role='observation_calendar', reason='FULL_AUTHENTICATED_ENVELOPE_JOIN_NOT_IMPLEMENTED')]
 for role in ROLES:
  b = role_bindings.get(role)
  if b is None:
   gaps.append(dict(role=role, reason='MISSING_ROLE_BINDING')); continue
  require(type(b) is dict and set(b) in ({'format', 'reference'}, {'format', 'reference', 'receipt_reference'}), 'Binding fields')
  raw = take(store, b['reference'])
  if role not in FORMATS:
   if 'receipt_reference' in b: take(store, b['receipt_reference'])
   gaps.append(dict(role=role, reason='SEMANTIC_ADAPTER_NOT_IMPLEMENTED', original_binding=deepcopy(b))); continue
  require(b['format'] == FORMATS[role], 'Explicit original source format, no relabel')
  out = dict(source_reference=deepcopy(b['reference']), binding_preserved=deepcopy(b))
  if role in ('generator_contract', 'membership_scope'):
   expected = FROZEN[role + '_reference']
   require(b['reference'] == {'path': str(PureWindowsPath(ROOT + expected[0])), 'sha256': expected[1]}, 'Fixed Windows core reference path and bytes')
   out['byte_count'] = len(raw)
  elif role == 'original8':
   d = document(raw); definition = d['definition']; securities = definition['securities']
   require(d['manifest_type'] == 'ndx_original_8_frozen_research_control' and d['status'] == 'FROZEN_RESEARCH_CONTROL_NOT_CURRENT_BROKER_OVERLAY', 'Original control role')
   require([r['ticker'] for r in securities] == ['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG'], 'Original order')
   require(all(type(r[k]) is str and r[k] for r in securities for k in ('security_id','issuer_id')) and all(len({r[k] for r in securities}) == 8 for k in ('security_id','issuer_id')), 'Original coordinates')
   require(sha256(json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == d['definition_sha256'], 'Definition bytes identity')
   for r in securities:
    require(type(r['target_weight']) in (int,float,str) and Decimal(str(r['target_weight'])).is_finite() and Decimal(str(r['target_weight'])) > 0, 'Original literal weight')
   require(d['broker_current_overlay_included'] is False, 'No broker overlay')
   for r in d['inputs'].values():
    if type(r) is dict and set(r) == {'path','sha256'}: take(store, r)
   out['original_document'] = d
   out['validation_scope'] = 'LITERAL_DEFINITION_AND_SUPPLIED_PARENT_BYTES_ONLY_NOT_FULL_CANONICAL_RECONSTRUCTION'
   gaps.append(dict(role=role, reason='CANONICAL_CHILD_MANIFEST_CONSENSUS_RECONSTRUCTION_NOT_IMPLEMENTED'))
  else:
   require('receipt_reference' in b, 'Original receipt bytes required')
   receipt = document(take(store, b['receipt_reference']))
   require(receipt['content_sha256'] == b['reference']['sha256'], 'Receipt content association')
   if role == 'official_archive':
    require(receipt['dataset_type'] == 'security_pool_snapshot' and receipt['immutable_snapshot'] is True and receipt['historical_backtest_allowed'] is False and receipt['source_effective_date_known'] is False, 'Conditional official archive scope')
   elif role == 'target_nav':
    require(receipt['dataset_key'] == '012922' and receipt['dataset_type'] == 'fund_nav', 'Fund NAV role')
   else:
    require(type(receipt['schema_version']) is int and receipt['schema_version'] == 1 and receipt['manifest_type'] == 'ndx_dynamic_shadow_frozen_nominal_input', 'Nominal receipt schema')
    require(receipt['price_basis'] == 'UNADJUSTED_NOMINAL_TRADE_PRICE' and receipt['corporate_action_adjustment'] == 'none', 'Nominal basis')
    for k in ('rows_after_decision_date_included','historical_backfill_allowed','promotion_allowed','live_mutation'): require(receipt[k] is False, 'Nominal scope')
   header, rows = csv_rows(raw, role != 'official_archive', role == 'nominal_prices')
   if role == 'nominal_prices':
    require(type(receipt['rows']) is int and receipt['rows'] == len(rows), 'Nominal row count')
    require(receipt['data_start'] == rows[0]['Date'] and receipt['data_end'] == rows[-1]['Date'] == receipt['decision_date'], 'Nominal exact date range')
    require(type(receipt['ticker']) is str and receipt['ticker'].strip() == receipt['ticker'] and receipt['ticker'], 'Explicit ticker')
    gaps.append(dict(role=role, reason='SINGLE_TICKER_NOT_COMPLETE_ADJUSTED_NOMINAL_ACTION_UNIVERSE'))
   out.update(columns=header, rows=rows, csv_data_row_indices=list(range(len(rows))), original_receipt=receipt)
  projections[role] = out
 return dict(schema='PERSISTED_FRESH_SOURCE_FRAGMENTS_V1', status='INCOMPLETE_SEMANTIC_BINDING_NOT_EXECUTABLE', policy_id=POLICY, role_order=list(ROLES), projections=projections, blockers=gaps, external_byte_anchor_matches={p:h for p,(h,_) in store.items()}, byte_equality_scope='SUPPLIED_BYTES_TO_SUPPLIED_EXTERNAL_REFS_NOT_ORIGIN_OR_FRESHNESS', **FLAGS)

def validate_outer_registration(*, registration_reference, artifacts):
 """Validate a proposed outer contract, never approve/register its executor."""
 store = byte_store(artifacts); d = document(take(store, registration_reference))
 require(set(d) == {'schema','policy_id','computation_registration','independent_reader_reference','source_adapter_reference','managed_attempt_root','network_allowed','automatic_retry_allowed','old_outputs_mutation_allowed'}, 'Outer registration contract fields')
 require(d['schema'] == 'PERSISTED_FRESH_EXECUTOR_SOURCE_REGISTRATION_PROPOSAL_V1' and d['policy_id'] == POLICY, 'Explicit proposed registration')
 c = d['computation_registration']
 expected = dict(schema='OBSERVATION_CANDIDATE_EXECUTOR_REGISTRATION_V1', entry_point='backtest.ndx_persisted_fresh_snapshot_executor_research.execute_fresh_input_snapshot', operation='FRESH_INPUT_SNAPSHOT_ONLY', input_schema='PERSISTED_ALL_NDX_CANDIDATE_EXECUTION_INPUT_V1', output_schema='PERSISTED_ALL_NDX_FRESH_INPUT_SNAPSHOT_COMPUTATION_V1')
 # The frozen Windows core compares serialized references exactly, not path aliases.
 expected.update({k:dict(path=str(PureWindowsPath(ROOT+p)),sha256=h) for k,(p,h) in FROZEN.items()})
 require(c == expected, 'Frozen computation registration unchanged')
 for r in [*({k:c[k] for k in FROZEN}.values()), d['independent_reader_reference'], d['source_adapter_reference']]: take(store,r)
 # This outer-only declaration retains its own forward-slash contract; it is not
 # part of computation_registration and is never passed to the frozen core.
 require(d['managed_attempt_root'] == ROOT+'data/cache/research/prospective_observation_seal_events_v1', 'Fixed managed root')
 for k in ('network_allowed','automatic_retry_allowed','old_outputs_mutation_allowed'): require(d[k] is False,'No authority')
 return dict(schema='PERSISTED_FRESH_REGISTRATION_PROPOSAL_INSPECTION_V1', status='STRUCTURALLY_BOUND_PROPOSAL_NOT_REGISTERED', registration_reference=deepcopy(registration_reference), registration_preserved=deepcopy(d), **FLAGS)
