"""Root whole compact formulas on a genuinely registered V5 observation chain."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backtest import ndx_prospective_observation_compact_append_research_v2 as producer
from backtest import ndx_compact_actual_independent_reconstruction_research_v1 as independent
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from backtest import ndx_capture_source_csv_independent_reconstruction_research_v1 as csv_checker
from scripts import ndx_registered_compact_history_independent_readback_20261009_v1 as formula
from ndx_registered_v5_parent_fixture import envelope
from ndx_registered_v5_observation_fixture import physical_registered_v5_observation


class RegisteredChainCompactFormulaRootReview(unittest.TestCase):
    def test_entire_v4_result_from_true_registered_v5_and_immutable_original_bytes(self):
        with TemporaryDirectory(prefix='ROOT_REGISTERED_COMPACT_FORMULA_ONLY_') as folder:
            root=Path(folder);research=root/'research';research.mkdir()
            parent_refs,observation_refs,_=physical_registered_v5_observation(root,research)
            parent=envelope(parent_refs)
            observation=dict(observation_refs)
            for key,role in [('payload','payload_reference'),('receipt','receipt_reference'),('audit','audit_reference')]:
                observation[key]=formula.decode(Path(observation[role]['path']).read_bytes())
            original=formula.encode(parent)
            state=view.inspect_parent_history_v5(parent)
            blobs={}
            for parts in observation['payload']['full_original_sources_preserved'].values():
                for part in parts.values():
                    item=part['reference'];blobs[item['path']]=Path(item['path']).read_bytes()
            for item in (*state['baseline_references'].values(),*state['accounted_baseline_references'].values(),observation['payload']['tzif_reference']):
                blobs[item['path']]=Path(item['path']).read_bytes()
            result=producer.append_observation_history(parent=parent,observation=observation)
            expected=independent.reconstruct_compact_actual(parent=parent,observation=observation,blobs=blobs,parent_checker=view,
                csv_rows=csv_checker.csv_rows,independent_formula=formula)
            self.assertEqual(formula.encode(result),formula.encode(expected))
            self.assertEqual(formula.encode(parent),original)
            self.assertEqual(result['parent_references'],parent_refs)
            self.assertEqual(result['schema'],'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4')
            self.assertEqual((result['typed_row_count'],result['observation_count'],result['gap_count']),(73,3,10))
            self.assertEqual(result['last_accounted_session'],'2026-10-13')
            self.assertEqual(result['baseline_references'],result['accounted_baseline_references'])
            self.assertEqual(result['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
            for path,digest in result['source_hashes'].items():self.assertEqual(formula.sha(Path(path).read_bytes()),digest)
            self.summary=dict(typed_rows=73,actual_observations=3,gaps=10,whole_result_equal=True,true_parent_schema=state['parent_schema'],
                original_parent_unchanged=True,source_count=len(result['source_hashes']))


if __name__=='__main__':unittest.main()
