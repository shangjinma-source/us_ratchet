"""Synthetic true V5 parent to unchanged V4 actual output, no IO or authority."""
import base64
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from backtest import ndx_prospective_observation_compact_append_research_v2 as module
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from backtest import ndx_prospective_observation_parent_history_research_v4 as legacy
from backtest import ndx_prospective_observation_receipt_research as payload_core
from backtest import ndx_prospective_gap_history_research_v5 as gap
from backtest import ndx_accounted_source_prefix_research_v1 as prefix
from test_ndx_prospective_gap_history_research_v5 import arguments,reference
from test_ndx_prospective_history_parent_view_research_v5 import wrap as wrap_gap
from test_ndx_prospective_observation_parent_history_research_v4 import observation_for,wrap as wrap_actual,fixture as legacy_fixture


def fixture():
    args=arguments();h=gap.extend_gap_history(**args);parent=wrap_gap(h,'pending12')
    normalized=view.inspect_parent_history_v5(parent);known=[r['session']for r in normalized['known_typed_rows']]
    capture=dict(reference=reference('synthetic/actual12/capture'),started_at_utc='2026-10-12T20:03:00+00:00',
        completed_at_utc='2026-10-12T20:03:01+00:00',sources={},baseline_sources={},
        tzif=dict(reference=args['tzif_reference'],bytes=args['tzif_bytes']))
    for ticker in ('QQQ','SPY'):
        baseline,_=prefix.derive_accounted_prefix(source_bytes=args['source_bytes'][ticker],source_reference=args['source_references'][ticker],
            accounted_sessions=known,scope_start=known[0])
        capture['baseline_sources'][ticker]=dict(reference=normalized['accounted_baseline_references'][ticker],bytes=baseline)
        capture['sources'][ticker]=dict(reference=reference('synthetic/actual12/full/'+ticker,args['source_bytes'][ticker]),bytes=args['source_bytes'][ticker])
    obsargs=dict(parent_reference=parent['reference'],parent_readback_reference=parent['readback_reference'],known_typed_rows=normalized['known_typed_rows'],
        parent_attempt_inventory=normalized['parent_attempt_inventory'],capture=capture,session='2026-10-12',
        writer_started_at_utc='2026-10-12T20:04:00+00:00',writer_completed_at_utc='2026-10-12T20:04:01+00:00')
    observation=observation_for(parent,payload_core,obsargs)
    for doc in ('payload','receipt','audit'):
        observation[doc].update(writer_adapter_schema='REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V5',actual_parent_schema=view.GAP_SCHEMA)
    return dict(parent=parent,observation=observation),args


def next_actual(previous,prior_observation,session='2026-10-13'):
    parent=wrap_actual(previous);normalized=view.inspect_parent_history_v5(parent)
    capture=dict(reference=reference('synthetic/actual/'+session+'/capture'),started_at_utc=session+'T20:03:00+00:00',
        completed_at_utc=session+'T20:03:01+00:00',sources={},baseline_sources={},
        tzif=dict(reference=prior_observation['payload']['tzif_reference'],bytes=base64.b64decode(prior_observation['payload']['tzif_bytes_base64'])))
    for ticker in ('QQQ','SPY'):
        part=prior_observation['payload']['full_original_sources_preserved'][ticker]['sources'];raw=base64.b64decode(part['original_csv_bytes_base64'])
        capture['baseline_sources'][ticker]=dict(reference=part['reference'],bytes=raw)
        current=raw+(session+',10,12,8,10,100\n').encode();capture['sources'][ticker]=dict(reference=reference('synthetic/actual/'+session+'/'+ticker,current),bytes=current)
    args=dict(parent_reference=parent['reference'],parent_readback_reference=parent['readback_reference'],known_typed_rows=normalized['known_typed_rows'],
        parent_attempt_inventory=normalized['parent_attempt_inventory'],capture=capture,session=session,
        writer_started_at_utc=session+'T20:04:00+00:00',writer_completed_at_utc=session+'T20:04:01+00:00')
    return dict(parent=parent,observation=observation_for(parent,payload_core,args))


class TrueV5CompactAdapterTests(unittest.TestCase):
    def test_actual_consumes_only_pending_and_is_genuine_v4_output_without_fake_parent(self):
        data,_=fixture();before=deepcopy(data)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')),patch.object(legacy,'append_observation_history_v4',side_effect=AssertionError('Frozen append called')),patch.object(payload_core,'prepare_observation_payload',side_effect=AssertionError('Payload called')):
            h=module.append_observation_history(**data)
        self.assertEqual(data,before);self.assertEqual(h['schema'],legacy.SCHEMA)
        self.assertEqual((h['typed_row_count'],h['observation_count'],h['gap_count']),(72,3,9))
        self.assertEqual(h['parent_references'],{role:data['parent'][role]for role in module.ROLES})
        self.assertEqual(h['observations'][:-1],data['parent']['document']['history']['observations'])
        self.assertEqual(h['parent_attempt_inventory'][:-1],data['parent']['document']['history']['parent_attempt_inventory'])
        self.assertEqual(h['known_typed_rows'][:-1],data['parent']['document']['history']['known_typed_rows'])
        self.assertEqual(h['baseline_references'],h['accounted_baseline_references'])
        child=wrap_actual(h);legacy_normalized=legacy.inspect_parent_history_v4(child);normalized=view.inspect_parent_history_v5(child)
        self.assertEqual(legacy_normalized['parent_schema'],legacy.SCHEMA)
        self.assertEqual(normalized['pending_source_sessions'],[]);self.assertEqual(normalized['excluded_not_completed_source_sessions'],[])
        self.assertEqual(normalized['full_capture_source_references'],h['baseline_references'])
        self.assertEqual(normalized['accounted_prefix_role'],view.LEGACY_PREFIX_ROLE)
        self.assertEqual(h['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
        self.assertFalse(h['observations'][-1]['month_first_actual_observation']);self.assertNotIn('original_csv_bytes_base64',str(h))
        for key in module.FLAGS:self.assertIs(h[key],False)

    def test_repeat_actual_then_gap_has_supported_true_v4_parent_and_preserved_counts(self):
        data,_=fixture();first=module.append_observation_history(**data)
        second_data=next_actual(first,data['observation']);second=module.append_observation_history(**second_data)
        self.assertEqual((second['typed_row_count'],second['observation_count'],second['gap_count']),(73,4,9))
        self.assertEqual(second['observations'][-2]['sequence'],72);self.assertEqual(second['observations'][-1]['sequence'],73)
        parent=wrap_actual(second);normalized=view.inspect_parent_history_v5(parent);days=[row['session']for row in normalized['known_typed_rows']]
        source={};source_refs={};prefixes={};evidence_refs={};baseline={}
        for ticker in ('QQQ','SPY'):
            baseline[ticker]=base64.b64decode(second_data['observation']['payload']['full_original_sources_preserved'][ticker]['sources']['original_csv_bytes_base64'])
            source[ticker]=baseline[ticker]+b'2026-10-14,10,12,8,10,100\n2026-10-15,10,12,8,10,100\n'
            source_refs[ticker]=reference('synthetic/afteractual/full/'+ticker,source[ticker])
            derived,evidence=prefix.derive_accounted_prefix(source_bytes=source[ticker],source_reference=source_refs[ticker],accounted_sessions=days+['2026-10-14'],scope_start=days[0])
            prefixes[ticker]=reference('synthetic/afteractual/prefix/'+ticker,derived);evidence_refs[ticker]=reference('synthetic/afteractual/evidence/'+ticker,gap.prefix_evidence_bytes(evidence))
        args=dict(parent=parent,capture_references={role:reference('synthetic/afteractual/capture/'+role)for role in module.ROLES},source_bytes=source,source_references=source_refs,
            accounted_baseline_bytes=baseline,actual_baseline_bytes=deepcopy(baseline),prefix_references=prefixes,prefix_evidence_references=evidence_refs,
            capture_started_at='2026-10-15T20:03:00+00:00',capture_completed_at='2026-10-15T20:03:01+00:00',
            tzif_bytes=base64.b64decode(second_data['observation']['payload']['tzif_bytes_base64']),tzif_reference=second['tzif_reference'])
        result=gap.extend_gap_history(**args);final=view.inspect_parent_history_v5(wrap_gap(result,'afteractual'))
        self.assertEqual((final['typed_row_count'],final['observation_count'],final['gap_count']),(74,4,10))
        self.assertEqual(final['last_observed_session'],'2026-10-13');self.assertEqual(final['last_accounted_session'],'2026-10-14')
        self.assertEqual([item['session']for item in final['pending_source_sessions']],['2026-10-15'])
        self.assertEqual(result['prior_state_preserved']['parent_schema'],legacy.SCHEMA)

    def test_legacy_v3_case_preserves_entire_frozen_result(self):
        data=legacy_fixture();expected=legacy.append_observation_history_v4(**deepcopy(data))
        actual=module.append_observation_history(**data);self.assertEqual(actual,expected)

    def test_forged_parent_suffix_adapter_timing_sequence_and_flags_fail_closed(self):
        cases=[]
        data,_=fixture();data['observation']['payload']['sequence']=True;cases.append(data)
        data,_=fixture();data['observation']['audit']['actual_parent_schema']=legacy.SCHEMA;cases.append(data)
        data,_=fixture();data['observation']['receipt']['writer_adapter_schema']='REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V4';cases.append(data)
        data,_=fixture();data['observation']['payload']['capture_started_at_utc']='2026-10-12T19:00:00+00:00';cases.append(data)
        data,_=fixture();data['observation']['payload']['selected_original_rows']['QQQ']['Date']='2026-10-13';cases.append(data)
        data,_=fixture();data['observation']['payload']['source_row_locations']['QQQ']['original_data_row_index']=True;cases.append(data)
        data,_=fixture();data['observation']['audit']['counts']['candidate_seal_allowed']=True;cases.append(data)
        data,_=fixture();data['observation']['payload']['receipt_published']=True;cases.append(data)
        for data in cases:
            with self.subTest(data=data['observation']['payload']['session']),self.assertRaises(ValueError):module.append_observation_history(**data)

    def test_extra_unfinished_parent_tail_cannot_be_silently_consumed(self):
        original,_=fixture()
        args=arguments(dates=('2026-10-09','2026-10-12','2026-10-13'));parent=wrap_gap(gap.extend_gap_history(**args),'extra13')
        normalized=view.inspect_parent_history_v5(parent)
        self.assertEqual([item['session']for item in normalized['excluded_not_completed_source_sessions']],['2026-10-13'])
        # Coordinate every original parent identity/ref/claim while hiding13 only in supplied current CSV.
        # Old payload core accepts its local known+[12] contract; the new adapter must compare the REAL prior suffix too.
        capture=dict(reference=reference('synthetic/coordinated-hidden13/capture'),started_at_utc='2026-10-12T20:03:00+00:00',
            completed_at_utc='2026-10-12T20:03:01+00:00',sources={},baseline_sources={},
            tzif=dict(reference=args['tzif_reference'],bytes=args['tzif_bytes']))
        for ticker in ('QQQ','SPY'):
            parts=original['observation']['payload']['full_original_sources_preserved'][ticker]
            old=base64.b64decode(parts['baseline_sources']['original_csv_bytes_base64'])
            current=base64.b64decode(parts['sources']['original_csv_bytes_base64'])
            capture['baseline_sources'][ticker]=dict(reference=normalized['accounted_baseline_references'][ticker],bytes=old)
            capture['sources'][ticker]=dict(reference=reference('synthetic/coordinated-hidden13/full/'+ticker,current),bytes=current)
        obsargs=dict(parent_reference=parent['reference'],parent_readback_reference=parent['readback_reference'],known_typed_rows=normalized['known_typed_rows'],
            parent_attempt_inventory=normalized['parent_attempt_inventory'],capture=capture,session='2026-10-12',
            writer_started_at_utc='2026-10-12T20:04:00+00:00',writer_completed_at_utc='2026-10-12T20:04:01+00:00')
        observation=observation_for(parent,payload_core,obsargs)
        for doc in ('payload','receipt','audit'):observation[doc].update(writer_adapter_schema='REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V5',actual_parent_schema=view.GAP_SCHEMA)
        with self.assertRaisesRegex(ValueError,'Whole prior suffix'):
            module.append_observation_history(parent=parent,observation=observation)


if __name__=='__main__':unittest.main()
