from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_same_window_nav_reference_metrics_20261003 as m
from backtest import ndx_same_window_nav_reference_metrics_research as core

spec=importlib.util.spec_from_file_location('metricfixture',Path(__file__).with_name('test_ndx_same_window_nav_reference_metrics_research.py'));fixturemod=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixturemod)
def fixture():
    args=fixturemod.fixture();alignment=args['alignment'];days=alignment['session_dates'];refs={k:dict(path='/synthetic/'+k,sha256='a'*64) for k in m.BOUND};false=dict.fromkeys(('point_in_time_verified','benchmark_qualified','execution_authorized','account_executed'),False)
    req=dict(schema='LONG_WINDOW_BENCHMARK_REQUIREMENTS_V1',reference_calendar=dict(dates=days),evaluation_initial_close_date=days[126],evaluation_return_end_dates=days[127:]);req['content_sha256']=m.sha(m.encode(req))
    parent=dict(schema='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_DOCUMENT_V1',requirements=req,source_hashes={},**false)
    outer=dict(schema='NAV_USD_OBSERVATION_ALIGNMENT_DOCUMENT_V1',alignment=alignment,source_hashes={},requirements_reference_preserved=refs['requirements'],input_references={k:refs[k] for k in ('requirements','requirements_publication')},nav_manifest_preserved={'unchanged':True},nav_snapshot_preserved={},fx_capture_manifest_preserved={},**false)
    docs=dict(alignment=outer,alignment_publication=dict(schema='NAV_USD_OBSERVATION_ALIGNMENT_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_CONVERSION_ONLY',alignment_reference=refs['alignment'],source_hashes={},**false),alignment_audit=dict(schema='NAV_USD_ALIGNMENT_INDEPENDENT_READBACK_V1',status='PASS',alignment_sha256=refs['alignment']['sha256'],publication_sha256=refs['alignment_publication']['sha256'],reader_sha256=refs['alignment_audit_reader']['sha256'],**false),requirements=parent,requirements_publication=dict(schema='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_PUBLICATION_V1',status='PUBLISHED_REQUIREMENTS_ONLY',requirements_reference=refs['requirements'],source_hashes={},**false),panel=dict(schema='BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1',panel=dict(schema='LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1',returns=dict(index=[d+'T00:00:00' for d in days[127:]])),point_in_time_verified=False,fit_performed=False))
    return docs,refs

class Tests(unittest.TestCase):
    def test_synthetic_exact_new_window_and_source_provenance(self):
        docs,refs=fixture();before=deepcopy(docs);args=m.project_inputs(docs,refs);out=core.calculate_reference_metrics(**args);m.validate_result(out,args);self.assertEqual(docs,before);self.assertEqual(args['reference_calendar']['dates'][0],'2026-03-20');self.assertEqual(len(out['modes']),2)

    def test_parent_receipt_scope_and_authority_rejected(self):
        docs,refs=fixture()
        for change in (lambda d:d['alignment_publication']['alignment_reference'].update(sha256='b'*64),lambda d:d['alignment_audit'].update(status='FAILED'),lambda d:d['requirements']['requirements'].update(evaluation_initial_close_date='2026-03-19'),lambda d:d['panel']['panel']['returns']['index'].__setitem__(0,'2026-03-24T00:00:00'),lambda d:d['alignment'].update(point_in_time_verified=True)):
            bad=deepcopy(docs);change(bad)
            with self.assertRaises(ValueError):m.project_inputs(bad,refs)

    def test_started_failure_source_guard_and_no_retry(self):
        docs,refs=fixture()
        with tempfile.TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)/'new'),patch.object(m,'load_inputs',return_value=(docs,refs,{},core)) as load,patch.object(m,'guard',side_effect=ValueError('source drift')):
            with self.assertRaises(ValueError):m.run(execute=True)
            self.assertEqual({p.name for p in m.OUTPUT.iterdir()},{'started.json','failure.json'})
            with self.assertRaises(ValueError):m.run(execute=True)
            self.assertEqual(load.call_count,1)
        with patch.object(m,'CORE_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.load_inputs()
            read.assert_not_called()

if __name__=='__main__':unittest.main()
