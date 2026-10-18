from copy import deepcopy
from pathlib import Path
from decimal import Context,Inexact,localcontext
import tempfile,unittest
from unittest.mock import patch
from backtest import ndx_multidecision_target_inputs_inspection_research as m
from scripts import ndx_multidecision_target_inputs_independent_readback_20261003 as r
from test_ndx_multidecision_target_scoring_inputs_20261003 import fixture
from scripts import ndx_multidecision_target_scoring_inputs_20261003 as w
from backtest import ndx_nav_usd_observation_alignment_research as align_fixture
from backtest import ndx_multidecision_target_scoring_inputs_research as target_fixture


def case():
    docs,refs=fixture();args=w.project_inputs(docs,refs);alignment=align_fixture.align_nav_usd_observations(**args);ar=dict(path='saved/alignment.json',sha256=m.sha(m.enc(alignment)));calendar=w.full_calendar(docs,refs)
    target=target_fixture.prepare_target_scoring_inputs(alignment=alignment,alignment_reference=ar,reference_calendar=calendar,contract=w.TARGET_CONTRACT)
    args.pop('session_dates');return dict(alignment=alignment,target=target,alignment_reference=ar,reference_calendar=calendar,**args)


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a=case()
    def test_real_pointers_complete_modes_and_hostile_context(self):
        with localcontext(Context(prec=2,traps=[Inexact])):out=m.inspect_target_inputs(**self.a)
        self.assertEqual(out['window_count_per_mode'],78);self.assertEqual(out['mode_missing_counts']['STRICT_SAME_SESSION_FX'],2)
        self.assertIn('csv_record_number',self.a['nav_rows'][0]['source_reference']);self.assertIn('html_line',self.a['fx_rows'][0]['source_reference'])
    def test_resigned_numeric_and_pointer_attacks_rejected(self):
        for change in (lambda a:a['target']['modes'][1]['return_slots'][0].update(return_exact='2',return_float=2.),lambda a:a['target']['modes'][0]['decisions'][0]['windows'][0].update(training_return_index_stop=999),lambda a:a['alignment']['rows'][0]['conversions']['BACKWARD_LATEST_VALID_FX'].update(nav_usd_exact='2'),lambda a:a['nav_rows'][0]['source_reference'].update(row_index=False),lambda a:a['fx_rows'][0]['source_reference'].update(table_row_index=False)):
            a=deepcopy(self.a);change(a)
            for name in ('target','alignment'):a[name]['content_sha256']=m.sha(m.enc({k:v for k,v in a[name].items() if k!='content_sha256'}))
            with self.assertRaises(ValueError):m.inspect_target_inputs(**a)
    def test_pending_reader_no_io_and_post_output_source_failure(self):
        with patch.object(r,'INDEX_SHA',None),patch.object(Path,'exists') as exists,patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):r.readback(execute=True)
            exists.assert_not_called();read.assert_not_called()
        args=deepcopy(self.a);ref=dict(path='source',sha256='a'*64)
        with tempfile.TemporaryDirectory() as t,patch.object(r,'OUTPUT',Path(t)/'out'),patch.multiple(r,INDEX_SHA='a'*64,PUBLICATION_SHA='b'*64,PRODUCER_SHA='c'*64),patch.object(r,'load_inputs',return_value=(args,{},m,ref,ref,{})),patch.object(r,'parent_namespace'),patch.object(r,'guard',side_effect=[None,ValueError('source drift')]),patch('shutil.disk_usage',return_value=type('D',(),{'free':10**12})()):
            with self.assertRaises(ValueError):r.readback(execute=True)
            self.assertTrue((r.OUTPUT/'independent_readback.json').exists());self.assertTrue((r.OUTPUT/'failure.json').exists())
            with self.assertRaises(ValueError):r.readback(execute=True)

if __name__=='__main__':unittest.main()
