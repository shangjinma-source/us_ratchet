from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from test_ndx_original_eight_scoring_inputs_20261003 import fixture
from test_ndx_original_eight_scoring_inputs_research import fixture as purefixture
from scripts import ndx_original_eight_scoring_inputs_20261003 as m
from backtest import ndx_original_eight_scoring_inputs_research as core

class Review(unittest.TestCase):
    def test_roles_typed_audit_counts_and_original_targets(self):
        docs,refs=fixture()
        for mutate in (lambda d:d['index_audit']['rows'][0]['inspection'].update(window_count=78.),
                       lambda d:d['tsm_audit'].update(point_in_time_verified=0),
                       lambda d:d['index_publication'].update(index_reference=refs['tsm']),
                       lambda d:d['index']['rows'][0]['coordinate'].update(issuer_id='foreign'),
                       lambda d:d['index_audit']['rows'][0].update(channel_reference={'path':'elsewhere','sha256':'a'*64})):
            d=deepcopy(docs);mutate(d)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):m.prepare_bindings(d,refs)
        a=m.prepare_bindings(docs,refs)
        self.assertEqual(a['channel_bindings'][4]['channel_reference']['json_pointer'],'/channel')
        self.assertEqual(a['channel_bindings'][0]['independent_readback_reference']['json_pointer'],'/rows/0/inspection')

    def test_post_publication_output_mutation_is_failure_not_retry(self):
        args=purefixture();docs,refs=fixture()
        docs['index'].update(original_provenance_and_missing={'full101':'preserved'},preserved_evidence_sidecars={'seven':'preserved'})
        docs['tsm']['complete_tsm_metadata']={'role':'control'}
        with TemporaryDirectory() as td:
            output=Path(td)/'out';calls=[]
            def guard(sources):
                calls.append(1)
                if len(calls)==2:(output/'inputs.json').write_bytes(b'changed')
            with patch.object(m,'OUTPUT',output),patch.object(m,'space'),patch.object(m,'guard',side_effect=guard),patch.object(m,'load_inputs',return_value=(docs,refs,{},args,core)):
                with self.assertRaisesRegex(ValueError,'Output drift'):m.run(execute=True)
                self.assertTrue((output/'publication.json').exists())
                self.assertTrue((output/'failure.json').exists())
                with self.assertRaisesRegex(ValueError,'Immutable'):m.run(execute=True)

if __name__=='__main__':unittest.main()
