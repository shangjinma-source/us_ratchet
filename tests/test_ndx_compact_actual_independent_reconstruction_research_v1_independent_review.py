"""Independent compact result reconstruction boundary tests; synthetic blobs only."""
import base64,hashlib
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_compact_actual_independent_reconstruction_research_v1 as module
from backtest import ndx_prospective_gap_history_research_v5 as gap
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from backtest import ndx_prospective_observation_receipt_research as payload_core
from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy
from test_ndx_compact_actual_independent_reconstruction_research_v1 import arguments
from test_ndx_prospective_gap_history_research_v5 import arguments as gap_arguments,reference
from test_ndx_prospective_history_parent_view_research_v5 import wrap
from test_ndx_prospective_observation_parent_history_research_v4 import observation_for,fixture as old_fixture
from test_ndx_prospective_observation_compact_append_research_v2 import fixture
from test_ndx_prospective_observation_gap_parent_payload_20261009_v3 import arguments as old_arguments

class IndependentCompactResultBoundaries(unittest.TestCase):
    def test_hidden_unfinished_rejected_before_independent_append_formula(self):
        original,_=fixture();raw=gap_arguments(dates=('2026-10-09','2026-10-12','2026-10-13'))
        parent=wrap(gap.extend_gap_history(**raw),'independent_hidden13');state=view.inspect_parent_history_v5(parent)
        self.assertEqual([item['session']for item in state['excluded_not_completed_source_sessions']],['2026-10-13'])
        capture=dict(reference=reference('synthetic/independent_hidden13/capture'),started_at_utc='2026-10-12T20:03:00+00:00',completed_at_utc='2026-10-12T20:03:01+00:00',
            sources={},baseline_sources={},tzif=dict(reference=raw['tzif_reference'],bytes=raw['tzif_bytes']))
        for ticker in ('QQQ','SPY'):
            parts=original['observation']['payload']['full_original_sources_preserved'][ticker]
            old=base64.b64decode(parts['baseline_sources']['original_csv_bytes_base64']);current=base64.b64decode(parts['sources']['original_csv_bytes_base64'])
            capture['baseline_sources'][ticker]=dict(reference=state['accounted_baseline_references'][ticker],bytes=old)
            capture['sources'][ticker]=dict(reference=reference('synthetic/independent_hidden13/'+ticker,current),bytes=current)
        obsargs=dict(parent_reference=parent['reference'],parent_readback_reference=parent['readback_reference'],known_typed_rows=state['known_typed_rows'],parent_attempt_inventory=state['parent_attempt_inventory'],
            capture=capture,session='2026-10-12',writer_started_at_utc='2026-10-12T20:04:00+00:00',writer_completed_at_utc='2026-10-12T20:04:01+00:00')
        observation=observation_for(parent,payload_core,obsargs)
        for role in ('payload','receipt','audit'):observation[role].update(writer_adapter_schema='REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V5',actual_parent_schema=view.GAP_SCHEMA)
        args=arguments(dict(parent=parent,observation=observation),raw['actual_baseline_bytes'])
        with patch.object(args['independent_formula'],'reconstruct_history',side_effect=AssertionError('Premature formula')):
            with self.assertRaisesRegex(ValueError,'Every original unconsumed'):module.reconstruct_compact_actual(**args)

    def test_last_actual_blob_cannot_be_replaced_by_advanced_accounted_blob(self):
        args=arguments();state=view.inspect_parent_history_v5(args['parent'])
        for ticker in ('QQQ','SPY'):
            actual=state['baseline_references'][ticker]['path'];accounted=state['accounted_baseline_references'][ticker]['path']
            self.assertNotEqual(args['blobs'][actual],args['blobs'][accounted])
            changed=deepcopy(args['blobs']);changed[actual]=changed[accounted]
            with self.subTest(ticker=ticker),self.assertRaises(ValueError):module.reconstruct_compact_actual(**dict(args,blobs=changed))

    def test_coordinated_same_rows_different_raw_prefix_is_rejected(self):
        args=arguments();observation=deepcopy(args['observation']);part=observation['payload']['full_original_sources_preserved']['QQQ']['sources'];path=part['reference']['path']
        raw=args['blobs'][path].replace(b'\n',b'\r\n',1);self.assertNotEqual(raw,args['blobs'][path]);digest=hashlib.sha256(raw).hexdigest()
        def resign(value):
            if isinstance(value,dict):
                if value.get('path')==path and 'sha256'in value:value['sha256']=digest
                if path in value:value[path]=digest
                for item in value.values():resign(item)
            elif isinstance(value,list):
                for item in value:resign(item)
        resign(observation);part['original_csv_bytes_base64']=base64.b64encode(raw).decode();blobs=dict(args['blobs']);blobs[path]=raw
        with self.assertRaisesRegex(ValueError,'Complete accounted byte prefix'):module.reconstruct_compact_actual(**dict(args,observation=observation,blobs=blobs))

    def test_authority_is_strict_false_in_payload_receipt_audit_and_counts(self):
        args=arguments()
        for role in ('payload','receipt','audit','counts'):
            for value in (True,0):
                observation=deepcopy(args['observation']);target=observation['audit']['counts']if role=='counts'else observation[role];target['source_authenticity_verified']=value
                with self.subTest(role=role,value=value),self.assertRaises(ValueError):module.reconstruct_compact_actual(**dict(args,observation=observation))

    def test_true_legacy_v3_entire_result_compatibility_without_producer_or_io(self):
        data=old_fixture();expected=legacy.append_observation_history_v4(**deepcopy(data));_,original,_=old_arguments();args=arguments(data,original['actual_baseline_bytes'])
        with patch.object(legacy,'append_observation_history_v4',side_effect=AssertionError('Producer executed')),patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')):
            actual=module.reconstruct_compact_actual(**args)
        self.assertEqual(actual,expected);self.assertEqual(data['parent']['document']['history']['schema'],'PROSPECTIVE_GAP_EXTENSION_HISTORY_V3')

if __name__=='__main__':unittest.main()
