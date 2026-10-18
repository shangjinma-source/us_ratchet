import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_single_replacement_selection_independent_readback_20261003 as m
from scripts import ndx_single_replacement_selection_20261003 as publisher
from test_ndx_single_replacement_selection_publisher_20261003 import physical
import test_ndx_single_replacement_preparation_20261003 as preparation_fixture


class Tests(unittest.TestCase):
    def test_true_positive_selected_journal_to_reader_without_parser_mock(self):
        original=preparation_fixture.fixture
        def declared_fixture():
            value=original()
            # Synthetic policy fixed before its inputs, preparation and journals
            # are created. No modification of saved results or actual policy.
            for r in value['original_rows']:
                r['input_row']['risk_parameters'].update(max_single_weight='1',min_single_weight='0.001',top_weight_cap='1',minimum_effective_n_ratio='0.001',risk_chain_top1_cap='1')
            return value
        with patch.object(preparation_fixture,'fixture',declared_fixture),tempfile.TemporaryDirectory() as t,physical(Path(t)) as rr:
            refs=publisher.run(registration_reference=rr,execute=True)
            saved=json.loads(Path(refs['selection']['path']).read_bytes())['selection']['document']
            self.assertEqual(saved['selected_case_count'],40)
            for row in saved['rows']:
                winner=row['selected'];r=winner['source_reference'];loc=r['record_locator']
                with Path(r['journal_reference']['path']).open('rb') as f:
                    f.seek(loc['byte_start']);raw=f.read(loc['byte_stop']-loc['byte_start'])
                record=json.loads(raw);self.assertEqual(record['record_sha256'],loc['record_sha256'])
                self.assertEqual(record['body']['task_id'],winner['task']['task_id'])
                self.assertEqual(record['body']['payload']['result'],winner['evaluation'])
                self.assertEqual(record['body']['global_ordinal'],winner['global_ordinal'])
            original_load=publisher.load_inputs
            def no_selector(*args,**kwargs):
                self.assertIs(kwargs.get('compile_selector'),False)
                c=original_load(*args,**kwargs);self.assertIsNone(c['core']);return c
            with patch.object(m,'OUTPUT',Path(t)/'positive_readback'),patch.object(publisher,'load_inputs',no_selector):
                result=m.readback(registration_reference=rr,selection_reference=refs['selection'],publication_reference=refs['publication'],execute=True)
            report=json.loads(Path(result['path']).read_bytes())
            self.assertEqual(report['counts']['selected_case_count'],40);self.assertGreater(report['counts']['feasible_count'],0)

    def test_true_journal_source_pure_independent_ranking(self):
        with tempfile.TemporaryDirectory() as t,physical(Path(t)) as rr:
            refs=publisher.run(registration_reference=rr,execute=True)
            with patch.object(m,'OUTPUT',Path(t)/'selection_readback'),patch.object(publisher,'run',side_effect=AssertionError('No publisher')):
                r=m.readback(registration_reference=rr,selection_reference=refs['selection'],publication_reference=refs['publication'],execute=True)
                report=json.loads(Path(r['path']).read_bytes());self.assertEqual(report['counts']['integer_count'],560);self.assertFalse(report['selector_called'])
                with self.assertRaises(ValueError):m.readback(registration_reference=rr,selection_reference=refs['selection'],publication_reference=refs['publication'],execute=True)

    def test_independent_reduction_rejects_resigned_selection_and_modes(self):
        with tempfile.TemporaryDirectory() as t,physical(Path(t)) as rr:
            refs=publisher.run(registration_reference=rr,execute=True);original=json.loads(Path(refs['selection']['path']).read_bytes())['selection']
            for mode in ('count','missing','authority','selected'):
                value=json.loads(json.dumps(original));d=value['document']
                if mode=='count':d['feasible_count']+=1
                elif mode=='missing':d['rows'].pop()
                elif mode=='authority':d['promotion_allowed']=True
                else:d['rows'][0]['scenario_id']='foreign'
                value['content_sha256']=publisher.sha(publisher.enc(d))
                with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_selection(publisher.load_inputs(rr,compile_selector=False),value)

    def test_pending_and_final_reader_drift(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No IO')):
            with self.assertRaises(ValueError):m.readback(execute=True)
        with tempfile.TemporaryDirectory() as t,physical(Path(t)) as rr:
            refs=publisher.run(registration_reference=rr,execute=True);save=m.save
            def changed(name,value):
                r=save(name,value)
                if name=='independent_readback.json':
                    with (m.OUTPUT/'started.json').open('ab') as f:f.write(b' ')
                return r
            with patch.object(m,'OUTPUT',Path(t)/'selection_readback'),patch.object(m,'save',changed),self.assertRaises(ValueError):m.readback(registration_reference=rr,selection_reference=refs['selection'],publication_reference=refs['publication'],execute=True)
            self.assertTrue((Path(t)/'selection_readback'/'failure.json').exists())


if __name__=='__main__':unittest.main()
