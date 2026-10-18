"""Pure compact adapter boundary attacks; no IO authentication or publication."""
from copy import deepcopy
from datetime import datetime,timedelta
from pathlib import Path
import base64,csv,io
import unittest
from unittest.mock import patch
from backtest import ndx_prospective_observation_compact_append_research_v2 as module
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from test_ndx_prospective_observation_compact_append_research_v2 import fixture

class IndependentCompactAdapterBoundaries(unittest.TestCase):
    def test_every_parent_and_capture_input_role_requires_payload_source_association(self):
        original,_=fixture()
        for group in ('parent','capture'):
            for role in module.ROLES:
                data=deepcopy(original);path=data['observation']['payload']['input_references'][group][role]['path']
                for doc in ('payload','receipt','audit'):data['observation'][doc]['source_hashes'].pop(path,None)
                with self.subTest(group=group,role=role),self.assertRaises(ValueError):module.append_observation_history(**data)

    def test_known_authority_fields_are_strict_false_across_all_observation_roles(self):
        original,_=fixture()
        for role in ('payload','receipt','audit','counts'):
            for key in ('future_independent_oos','source_authenticity_verified','final_durable_completion_time_verified'):
                for bad in (True,0):
                    data=deepcopy(original);target=data['observation']['audit']['counts']if role=='counts'else data['observation'][role];target[key]=bad
                    with self.subTest(role=role,key=key,bad=bad),self.assertRaises(ValueError):module.append_observation_history(**data)

    def test_prior_suffix_clock_equality_allowed_but_microsecond_regression_rejected(self):
        data,_=fixture();state=view.inspect_parent_history_v5(data['parent'])
        cutoff=max(datetime.fromisoformat(item['capture_completed_at_utc'])for item in state['pending_source_sessions']+state['excluded_not_completed_source_sessions'])
        data['observation']['payload']['capture_started_at_utc']=cutoff.isoformat()
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')):result=module.append_observation_history(**data)
        self.assertEqual(result['known_typed_rows'][:-1],state['known_typed_rows'])
        data['observation']['payload']['capture_started_at_utc']=(cutoff-timedelta(microseconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError,'regressed prior suffix'):module.append_observation_history(**data)

    def test_last_actual_baseline_cannot_replace_gap_advanced_accounted_baseline(self):
        data,args=fixture();state=view.inspect_parent_history_v5(data['parent'])
        self.assertNotEqual(state['baseline_references'],state['accounted_baseline_references'])
        for ticker in ('QQQ','SPY'):
            part=data['observation']['payload']['full_original_sources_preserved'][ticker]['baseline_sources']
            raw=args['actual_baseline_bytes'][ticker];part['reference']=deepcopy(state['baseline_references'][ticker])
            part['original_csv_bytes_base64']=base64.b64encode(raw).decode()
            part['rows']=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline='')))
        with self.assertRaises(ValueError):module.append_observation_history(**data)

if __name__=='__main__':unittest.main()
