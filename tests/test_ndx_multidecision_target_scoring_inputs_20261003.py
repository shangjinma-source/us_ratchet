from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_target_scoring_inputs_20261003 as m
from backtest import ndx_nav_usd_observation_alignment_research as alignment_core
from backtest import ndx_multidecision_target_scoring_inputs_research as target_core
from test_ndx_nav_usd_observation_alignment_20261003 import fixture as old_fixture
from test_ndx_multidecision_scoring_history_research import fixture as history_fixture


def fixture():
    docs,refs=old_fixture()
    for name in ('history','history_publication'):refs[name]=dict(path='/synthetic/'+name,sha256='c'*64)
    docs['history']=dict(schema='BULK_HISTORY_REQUIREMENTS_DOCUMENT_V1',source_hashes={},point_in_time_verified=False,execution_authorized=False,fit_performed=False,requirements=dict(schema='BULK_CONDITIONAL_HISTORY_REQUIREMENTS_V1',reference_calendar=dict(ticker='AAPL',dates=history_fixture()['reference_calendar'],source_reference=dict(path='calendar',sha256='d'*64))))
    docs['history_publication']=dict(schema='BULK_HISTORY_REQUIREMENTS_PUBLICATION_V1',status='PUBLISHED_REQUIREMENTS_ONLY',requirements_reference=refs['history'],source_hashes={})
    return docs,refs


class Tests(unittest.TestCase):
    def test_two_real_pure_integration_full_union_and_blocked_modes(self):
        docs,refs=fixture();args=m.project_inputs(docs,refs);a=alignment_core.align_nav_usd_observations(**args);m.validate_result(a,args)
        ar=dict(path='saved/alignment.json',sha256=m.sha(m.encode(a)))
        r=target_core.prepare_target_scoring_inputs(alignment=a,alignment_reference=ar,reference_calendar=m.full_calendar(docs,refs),contract=m.TARGET_CONTRACT)
        m.validate_targets(r,ar,m.full_calendar(docs,refs),a)
        self.assertEqual(len(r['modes']),2);self.assertEqual(len(r['modes'][0]['decisions']),6)
        self.assertTrue(any(w['status']=='BLOCKED_WINDOW' for d in r['modes'][0]['decisions'] for w in d['windows']))
        self.assertTrue(all(w['status']=='CONDITIONAL_NUMERIC_WINDOW' for d in r['modes'][1]['decisions'] for w in d['windows']))
        self.assertEqual(len(a['nav_rows_preserved']),1101);self.assertEqual(len(a['fx_rows_preserved']),6975)

    def test_calendar_parent_and_original_values_not_changed(self):
        docs,refs=fixture();before=deepcopy(docs);m.project_inputs(docs,refs);self.assertEqual(docs,before)
        for change in (lambda d:d['history_publication']['requirements_reference'].update(sha256='e'*64),lambda d:d['history']['requirements']['reference_calendar']['dates'].remove('2026-03-31'),lambda d:d['nav_csv'][0].update(Close='99'),lambda d:d['fx_readback'].update(point_in_time_verified=0)):
            b=deepcopy(docs);change(b)
            with self.assertRaises(ValueError):m.project_inputs(b,refs)

    def test_pending_and_failed_attempt_preserved(self):
        with patch.object(m,'TARGET_CORE_SHA',None),patch.object(Path,'exists') as exists,patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.run(execute=True)
            exists.assert_not_called();read.assert_not_called()
        docs,refs=fixture()
        with tempfile.TemporaryDirectory() as t,patch.object(m,'OUTPUT',Path(t)/'out'),patch.object(m,'TARGET_CORE_SHA','a'*64),patch.object(m,'load_inputs',return_value=(docs,refs,{},alignment_core,target_core)),patch.object(m,'guard',side_effect=ValueError('post arithmetic source drift')),patch('shutil.disk_usage',return_value=type('D',(),{'free':10**12})()):
            with self.assertRaises(ValueError):m.run(execute=True)
            self.assertTrue((m.OUTPUT/'target_inputs.json').exists());self.assertTrue((m.OUTPUT/'failure.json').exists())
            with self.assertRaises(ValueError):m.run(execute=True)

if __name__=='__main__':unittest.main()
