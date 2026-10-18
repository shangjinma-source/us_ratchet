from copy import deepcopy
import json,runpy,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts import ndx_observation_gap_frontier_20261002 as m
from test_ndx_observation_gap_frontier_20261002 import fixture

class WrapperIndependentReview(unittest.TestCase):
    def setUp(self):
        # Each fixture models a fresh CLI; restore the discovery import state afterward.
        isolation = patch.dict(m.sys.modules)
        isolation.start()
        self.addCleanup(isolation.stop)
        m.sys.modules.pop('backtest.ndx_observation_gap_frontier_research', None)

    def test_captured_sources_prefix_and_projected_types(self):
        with tempfile.TemporaryDirectory() as folder:
            raw,refs=fixture(Path(folder));p=m.prepare(raw,refs)
            callback=runpy.run_path(str(m.ROOT/'backtest/ndx_observation_gap_frontier_research.py'))['prepare_observation_frontier']
            result=callback(parent_session_dates=p['parent_dates'],gap_ledger=p['ledger'],common_source_session_dates=p['common_dates'])
            m.validate_result(result,p)
            for kind in ('captured_alias','late_missing','duplicate','receipt_authority'):
                r=deepcopy(raw)
                if kind=='captured_alias':
                    ledger=json.loads(r['ledger']);ledger['batches'][0]['classification_capture']['captured_source_references']['SPY']=refs['QQQ'];r['ledger']=json.dumps(ledger).encode()
                elif kind=='late_missing':r['QQQ']=r['QQQ'].replace(b'2026-09-29,100\n',b'')
                elif kind=='duplicate':r['SPY']+=b'2026-10-01,100\n'
                else:
                    pub=json.loads(r['publication']);pub['candidate_seal_allowed']=True;r['publication']=json.dumps(pub).encode()
                with self.subTest(kind=kind),self.assertRaises(ValueError):m.prepare(r,refs)
            for key,value in [('first_observed_session_of_month',0),('last_observed_session','2026-10-01'),('seal_increment',False),('month_first_semantics','ELIGIBLE')]:
                r=deepcopy(result);r[key]=value
                with self.assertRaises(ValueError):m.validate_result(r,p)

    def test_source_drift_failure_prevents_retry_and_existing_never_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw,refs=fixture(root)
            callback=runpy.run_path(str(m.ROOT/'backtest/ndx_observation_gap_frontier_research.py'))['prepare_observation_frontier']
            def drift(**kwargs):
                result=callback(**kwargs);Path(refs['QQQ']['path']).write_bytes(b'changed');return result
            fake=SimpleNamespace(__file__=refs['core']['path'],prepare_observation_frontier=drift)
            with patch.object(m,'OUTPUT',root/'out'),patch.object(m,'PINS',{k:(r['path'],r['sha256']) for k,r in refs.items()}),patch.object(m.importlib,'import_module',return_value=fake):
                with self.assertRaisesRegex(ValueError,'Source drift'):m.run()
                self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertFalse((m.OUTPUT/'publication.json').exists())
                with patch.object(m,'prepare') as prepare:
                    with self.assertRaisesRegex(ValueError,'no retry'):m.run()
                    prepare.assert_not_called()

if __name__=='__main__':unittest.main()
