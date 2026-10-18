from copy import deepcopy
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from unittest.mock import patch
import json
import unittest
from backtest import ndx_persisted_fresh_snapshot_sources_research as m


def encoded(d):
 return json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def fixture():
 artifacts=[]; bindings={}
 def add(name, raw):
  r=dict(path='E:/synthetic/'+name,sha256=sha256(raw).hexdigest())
  artifacts.append(dict(reference=r,raw_bytes=raw)); return r
 raw=b'Date,Open,High,Low,Close,Volume\n2026-10-01,10,11,9,10,123\n2026-10-02,11,12,10,11,456\n'
 nr=add('nominal.csv',raw)
 nd=dict(schema_version=1,manifest_type='ndx_dynamic_shadow_frozen_nominal_input',ticker='QQQ',decision_date='2026-10-02',price_basis='UNADJUSTED_NOMINAL_TRADE_PRICE',corporate_action_adjustment='none',rows=2,data_start='2026-10-01',data_end='2026-10-02',content_sha256=nr['sha256'],rows_after_decision_date_included=False,historical_backfill_allowed=False,promotion_allowed=False,live_mutation=False,source_errors_before_success=['original diagnostic'])
 bindings['nominal_prices']=dict(format='SINGLE_FROZEN_NOMINAL_CSV',reference=nr,receipt_reference=add('nominal.receipt',encoded(nd)))
 tr=add('nav.csv',b'Date,Close\n2026-10-01,1.234567890123456789\n2026-10-02,1.25\n')
 bindings['target_nav']=dict(format='FUND_NAV_CSV',reference=tr,receipt_reference=add('nav.receipt',encoded(dict(dataset_type='fund_nav',dataset_key='012922',content_sha256=tr['sha256'],source_time_basis='file_mtime_only'))))
 o=add('official.csv',b'ticker,name\nQQQ,Original Unicode\n')
 bindings['official_archive']=dict(format='OFFICIAL_IMMUTABLE_CSV',reference=o,receipt_reference=add('official.receipt',encoded(dict(dataset_type='security_pool_snapshot',content_sha256=o['sha256'],immutable_snapshot=True,historical_backtest_allowed=False,source_effective_date_known=False))))
 for role in ('generator_contract','membership_scope'):
  path,h=m.FROZEN[role+'_reference']; raw=Path(m.ROOT+path).read_bytes()
  r=dict(path=str(PureWindowsPath(m.ROOT+path)),sha256=h); artifacts.append(dict(reference=r,raw_bytes=raw)); bindings[role]=dict(format='FROZEN_BYTES',reference=r)
 return dict(artifacts=artifacts,role_bindings=bindings)

def resign(a, reference, change):
 item=next(x for x in a['artifacts'] if x['reference']==reference)
 d=json.loads(item['raw_bytes']); change(d); item['raw_bytes']=encoded(d)
 new=sha256(item['raw_bytes']).hexdigest(); item['reference']['sha256']=new
 # Fixture shares references deliberately; mutation remains externally anchored.


class Tests(unittest.TestCase):
 def test_original_bytes_rows_and_limitations_preserved_without_io(self):
  a=fixture(); before=deepcopy(a)
  with patch.object(Path,'read_bytes',side_effect=AssertionError('No IO')):
   out=m.inspect_source_bundle(**a)
  self.assertEqual(a,before); self.assertEqual(len(out['role_order']),16)
  self.assertEqual(out['projections']['target_nav']['rows'][0]['Close'],'1.234567890123456789')
  self.assertEqual(out['projections']['nominal_prices']['csv_data_row_indices'],[0,1])
  self.assertEqual(out['projections']['nominal_prices']['original_receipt']['source_errors_before_success'],['original diagnostic'])
  self.assertNotIn('execution_input',out); self.assertTrue(all(out[k] is False for k in m.FLAGS))
  self.assertEqual(len([x for x in out['blockers'] if x['reason']=='MISSING_ROLE_BINDING']),11)

 def test_resigned_receipt_role_count_permission_and_range_rejected(self):
  for field,value in [('rows',True),('promotion_allowed',0),('data_end','2026-10-01'),('content_sha256','0'*64),('price_basis','ADJUSTED')]:
   a=fixture(); resign(a,a['role_bindings']['nominal_prices']['receipt_reference'],lambda d:d.update({field:value}))
   with self.subTest(field=field),self.assertRaises(ValueError): m.inspect_source_bundle(**a)
  a=fixture(); resign(a,a['role_bindings']['target_nav']['receipt_reference'],lambda d:d.update(dataset_key='OTHER'))
  with self.assertRaises(ValueError): m.inspect_source_bundle(**a)

 def test_all_unsupported_roles_explicit_even_when_byte_bound(self):
  a=fixture()
  for role in m.ROLES:
   if role not in a['role_bindings']:
    raw=encoded({'schema':'CALLER_CLAIM_NOT_AUTHORITY'}); r=dict(path='E:/synthetic/'+role,sha256=sha256(raw).hexdigest())
    a['artifacts'].append(dict(reference=r,raw_bytes=raw)); a['role_bindings'][role]=dict(format='UNKNOWN',reference=r)
  # Original8 has a supported real schema and cannot be relabelled arbitrary JSON.
  del a['role_bindings']['original8']
  out=m.inspect_source_bundle(**a)
  self.assertEqual({x['role'] for x in out['blockers'] if x['reason']=='SEMANTIC_ADAPTER_NOT_IMPLEMENTED'},set(m.ROLES)-set(m.FORMATS))
  self.assertFalse(out['execution_input_ready'])

 def test_same_bytes_hash_duplicate_json_and_csv_holes(self):
  a=fixture(); a['artifacts'][0]['raw_bytes']+=b'\n'
  with self.assertRaises(ValueError):m.inspect_source_bundle(**a)
  a=fixture(); a['artifacts'].append(deepcopy(a['artifacts'][0]))
  with self.assertRaises(ValueError):m.inspect_source_bundle(**a)
  for raw in (b'{"x":{"a":1,"a":2}}',b'{"x":NaN}'):
   with self.assertRaises(ValueError):m.document(raw)
  for raw in (b'Date,Close\n2026-10-01\n',b'Date,Close,Close\n2026-10-01,1,1\n',b'Date,Close\n2026-10-01,NaN\n'):
   with self.assertRaises(ValueError):m.csv_rows(raw,True)

 def test_original8_literal_definition_is_not_complete_consensus_authentication(self):
  a=fixture(); securities=[dict(ticker=t,security_id='sid:'+t,issuer_id='issuer:'+t,target_weight='0.125') for t in ['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']]
  definition=dict(securities=securities)
  parentraw=b'{"original":"parent"}'; parent=dict(path='E:/synthetic/child.json',sha256=sha256(parentraw).hexdigest())
  a['artifacts'].append(dict(reference=parent,raw_bytes=parentraw))
  d=dict(manifest_type='ndx_original_8_frozen_research_control',status='FROZEN_RESEARCH_CONTROL_NOT_CURRENT_BROKER_OVERLAY',definition=definition,definition_sha256=sha256(encoded(definition)).hexdigest(),broker_current_overlay_included=False,inputs=dict(identity_manifest=parent))
  raw=encoded(d); r=dict(path='E:/synthetic/original8.json',sha256=sha256(raw).hexdigest())
  a['artifacts'].append(dict(reference=r,raw_bytes=raw)); a['role_bindings']['original8']=dict(format='FROZEN_ORIGINAL8_JSON',reference=r)
  out=m.inspect_source_bundle(**a)
  self.assertEqual(out['projections']['original8']['original_document'],d)
  self.assertTrue(any(x['reason']=='CANONICAL_CHILD_MANIFEST_CONSENSUS_RECONSTRUCTION_NOT_IMPLEMENTED' for x in out['blockers']))
  a['artifacts']=[x for x in a['artifacts'] if x['reference']!=parent]
  with self.assertRaises(ValueError):m.inspect_source_bundle(**a)

 def test_external_registration_is_proposal_not_approval(self):
  from backtest import ndx_persisted_fresh_snapshot_executor_research as frozen
  artifacts=[]
  c=dict(schema='OBSERVATION_CANDIDATE_EXECUTOR_REGISTRATION_V1',entry_point='backtest.ndx_persisted_fresh_snapshot_executor_research.execute_fresh_input_snapshot',operation='FRESH_INPUT_SNAPSHOT_ONLY',input_schema='PERSISTED_ALL_NDX_CANDIDATE_EXECUTION_INPUT_V1',output_schema='PERSISTED_ALL_NDX_FRESH_INPUT_SNAPSHOT_COMPUTATION_V1')
  actual_core_paths={'executor_reference':frozen.SOURCE,'computation_reference':frozen.COMPUTATION,'versioning_reference':frozen.VERSIONING,'generator_contract_reference':frozen.CONTRACT,'membership_scope_reference':frozen.SCOPE}
  for k,p in actual_core_paths.items():
   raw=p.read_bytes(); r=dict(path=str(p),sha256=sha256(raw).hexdigest()); artifacts.append(dict(reference=r,raw_bytes=raw)); c[k]=r
  # Direct compatibility with the unchanged core, not a clone of our expected dict.
  with patch.object(frozen,'execute_fresh_input_snapshot',side_effect=AssertionError('No computation')):
   self.assertEqual(frozen.validate_registration(c),c)
  wrong=deepcopy(c); wrong['executor_reference']['path']=wrong['executor_reference']['path'].replace('\\','/')
  with self.assertRaises(ValueError):frozen.validate_registration(wrong)
  # These are proposed, byte-bound code references, deliberately not approved code.
  code=b'# synthetic proposal only\n'; r=dict(path='E:/synthetic/reader.py',sha256=sha256(code).hexdigest()); artifacts.append(dict(reference=r,raw_bytes=code))
  d=dict(schema='PERSISTED_FRESH_EXECUTOR_SOURCE_REGISTRATION_PROPOSAL_V1',policy_id=m.POLICY,computation_registration=c,independent_reader_reference=r,source_adapter_reference=r,managed_attempt_root=m.ROOT+'data/cache/research/prospective_observation_seal_events_v1',network_allowed=False,automatic_retry_allowed=False,old_outputs_mutation_allowed=False)
  def args():
   raw=encoded(d); ref=dict(path='E:/synthetic/registration.json',sha256=sha256(raw).hexdigest())
   return dict(registration_reference=ref,artifacts=artifacts+[dict(reference=ref,raw_bytes=raw)])
  with patch.object(Path,'read_bytes',side_effect=AssertionError('No IO')):out=m.validate_outer_registration(**args())
  self.assertFalse(out['registration_approved']); self.assertFalse(out['candidate_seal_allowed'])
  for key,value in [('automatic_retry_allowed',0),('managed_attempt_root','E:/synthetic/other'),('unknown',True)]:
   saved=deepcopy(d); d[key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):m.validate_outer_registration(**args())
   d=saved

if __name__=='__main__':unittest.main()
