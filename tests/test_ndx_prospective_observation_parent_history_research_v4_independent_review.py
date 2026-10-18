"""Pure compact V4 adversarial review; no output or actual entrypoints."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_prospective_observation_parent_history_research_v4 as module
from scripts import ndx_prospective_observation_independent_readback_v3_20261009 as observation_reader
from test_ndx_prospective_observation_parent_history_research_v4 import fixture, wrap, next_fixture


class IndependentCompactV4Tests(unittest.TestCase):
    def test_two_appends_preserve_every_gap_pointer_and_inputs_without_io(self):
        a=fixture();before=deepcopy(a)
        with (patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')),
              patch.object(Path,'write_bytes',side_effect=AssertionError('Pure output'))):
            first=module.append_observation_history_v4(**a)
        self.assertEqual(a,before)
        b=next_fixture(first,a['observation']);second=module.append_observation_history_v4(**b)
        self.assertEqual((first['typed_row_count'],second['typed_row_count']),(70,71))
        self.assertEqual((first['observation_count'],second['observation_count']),(2,3))
        self.assertEqual(second['gap_count'],8)
        self.assertEqual(second['known_typed_rows'][:69],before['parent']['document']['history']['known_typed_rows'])
        self.assertEqual([e['sequence'] for e in second['observations']],[66,70,71])
        self.assertEqual(second['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
        self.assertNotIn('original_csv_bytes_base64',str(second))

    def test_known_observation_authority_flags_cannot_contradict_reader_contract(self):
        cases=(('payload',set(observation_reader.PAYLOAD_FALSE)|set(observation_reader.WRITER_FALSE)),
               ('receipt',observation_reader.WRITER_FALSE),('audit',observation_reader.WRITER_FALSE))
        a=fixture()
        for role,keys in cases:
            for key in keys:
                original=a['observation'][role].get(key,'MISSING')
                a['observation'][role][key]=True
                with self.subTest(role=role,key=key),self.assertRaises(ValueError):module.append_observation_history_v4(**a)
                if original=='MISSING':a['observation'][role].pop(key)
                else:a['observation'][role][key]=original

    def test_known_audit_count_authority_must_remain_false_if_present(self):
        for key in ('clock_authenticity_verified','final_durable_completion_time_verified','candidate_seal_allowed','cohort_registration_allowed'):
            a=fixture();a['observation']['audit']['counts'][key]=True
            with self.subTest(key=key),self.assertRaises(ValueError):module.append_observation_history_v4(**a)

    def test_own_v4_new_row_cannot_claim_unrecorded_seal(self):
        original=module.append_observation_history_v4(**fixture())
        for status in ('SEALED','FAILED','UNKNOWN'):
            h=deepcopy(original);h['known_typed_rows'][-1]['seal_status']=status
            with self.subTest(status=status),self.assertRaises(ValueError):module.inspect_parent_history_v4(wrap(h))

    def test_v3_pending_and_wrong_accounted_baseline_cannot_be_actual_baseline(self):
        for mode in ('pending','unfinished','wrongbaseline'):
            a=fixture();h=a['parent']['document']['history']
            if mode=='pending':h['pending_source_sessions']=[{'session':'2026-10-08'}]
            elif mode=='unfinished':h['excluded_not_completed_source_sessions']=[{'session':'2026-10-08'}]
            else:
                for ticker in ('QQQ','SPY'):
                    a['observation']['payload']['full_original_sources_preserved'][ticker]['baseline_sources']['reference']=deepcopy(h['baseline_references'][ticker])
            with self.subTest(mode=mode),self.assertRaises(ValueError):module.append_observation_history_v4(**a)

    def test_actual_attempt_bijection_and_original_genesis_are_immutable(self):
        h=module.append_observation_history_v4(**fixture())
        changes=(lambda x:x['parent_attempt_inventory'].append(deepcopy(x['parent_attempt_inventory'][-1])),
                 lambda x:x['observations'][-1].update(sequence=69),
                 lambda x:x['known_typed_rows'][0].update(seal_status='UNKNOWN'),
                 lambda x:x['observations'][-1]['original_source_hash_claims']['audit'].clear())
        for mutate in changes:
            changed=deepcopy(h);mutate(changed)
            with self.assertRaises(ValueError):module.inspect_parent_history_v4(wrap(changed))

    def test_replay_and_false_integer_counts_or_late_upgrade_rejected(self):
        a=fixture();h=module.append_observation_history_v4(**a)
        with self.assertRaises(ValueError):module.append_observation_history_v4(parent=wrap(h),observation=a['observation'])
        for mode in ('count','late','rawhash'):
            a=fixture()
            if mode=='count':a['observation']['audit']['counts']['new_observation_count']=True
            elif mode=='late':a['observation']['payload']['timing_classification']='LATE_OBSERVATION'
            else:a['observation']['payload']['full_original_sources_preserved']['QQQ']['sources']['original_csv_bytes_base64']='AA=='
            with self.subTest(mode=mode),self.assertRaises(ValueError):module.append_observation_history_v4(**a)


if __name__=='__main__':unittest.main()
