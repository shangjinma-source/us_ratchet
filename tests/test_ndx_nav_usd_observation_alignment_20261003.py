"""Synthetic projection and temporary publication lifecycle only."""
from copy import deepcopy
from datetime import date,timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_nav_usd_observation_alignment_20261003 as m
from backtest import ndx_nav_usd_observation_alignment_research as core


def fixture():
    refs={k:dict(path='/synthetic/'+k,sha256='a'*64) for k in m.BOUND}
    def weekdays(a,b):
        d=date.fromisoformat(a);out=[]
        while d<=date.fromisoformat(b):
            if d.weekday()<5:out.append(d.isoformat())
            d+=timedelta(days=1)
        return out
    a=weekdays('2025-09-18','2026-03-20');b=weekdays('2026-03-23','2026-09-21');calendar=a[:126]+[a[-1]]+b[:125]+[b[-1]]
    nav=[]
    for i in range(1101):
        d=(date(2026,9,21)-timedelta(days=1100-i)).isoformat();nav.append(dict(Date=d,UnitNav='1.25',AccumNav='2.5',DailyPct='0',Close='1.25'))
    req=dict(schema='LONG_WINDOW_BENCHMARK_REQUIREMENTS_V1',reference_calendar=dict(dates=calendar),nav_metadata_preserved=dict(source_reference=refs['nav_csv'],publication_time_known=False,selected_value_column='Close',rows=[dict(date=r['Date'],row_index=i,source_reference=refs['nav_csv']) for i,r in enumerate(nav)]),point_in_time_verified=False,benchmark_qualified=False,execution_authorized=False)
    req['content_sha256']=m.sha(m.encode(req));parent=dict(schema='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_DOCUMENT_V1',requirements=req,source_hashes={},point_in_time_verified=False,benchmark_qualified=False,execution_authorized=False)
    pub=dict(status='PUBLISHED_REQUIREMENTS_ONLY',requirements_reference=refs['requirements'],source_hashes={},point_in_time_verified=False,benchmark_qualified=False,execution_authorized=False)
    sources={name:dict(name=name,raw=dict(path=name+'.html',sha256='a'*64),receipt=dict(path=name+'.receipt',sha256='b'*64)) for name in ('country_data','china_history','fred_series')}
    rows=[]
    for i in range(6975):
        d=(date(2026,9,25)-timedelta(days=6974-i)).isoformat();nd=d in ('2025-10-13','2025-11-11')
        rows.append(dict(date=d,date_literal=d,status='NOT_AVAILABLE_ND' if nd else 'REPORTED_RATE',rate_decimal=None if nd else '7.25',rate_literal='ND' if nd else '7.25',historical_available_at=None,source_reference=dict(sources['china_history']['raw'],table_row_index=i,html_line=i+1)))
    fx=dict(schema='OFFICIAL_FX_INDEPENDENT_SAVED_READBACK_V1',status='PASS',manifest_sha256=refs['fx_manifest']['sha256'],source_references=sources,table_rows=rows,summary=dict(table_row_count=6975),window_253=[dict(session=d) for d in calendar],rate_direction='CNY_PER_USD',historical_available_at_verified=False,point_in_time_verified=False,benchmark_qualified=False,page_release_label='Current vintage',limitations=['CURRENT_PAGE_VINTAGE_NOT_HISTORICAL_RELEASE_ARCHIVE','OBSERVATION_DATE_NOT_PUBLICATION_TIMESTAMP','NOON_BUYING_NOT_CLOSE_OR_EXECUTABLE_FX'],frequency='DAILY',official_clauses={},receipts={})
    docs=dict(requirements=parent,requirements_publication=pub,nav_csv=nav,nav_manifest=dict(content_sha256=refs['nav_csv']['sha256'],publication_time_known=False,row_count=1101),nav_snapshot=dict(schema='NEW_CUTOFF_LOCAL_NAV_BYTES_SNAPSHOT_V1',dataset_key='012922',nav_publication_time_verified=False,immutable_copies={'nav.csv':refs['nav_csv'],'original_manifest.json':refs['nav_manifest']}),fx_readback=fx,fx_manifest=dict(schema='OFFICIAL_FX_SOURCE_CAPTURE_V1',status='SAVED_SOURCE_ONLY',historical_available_at_verified=False,point_in_time_verified=False,benchmark_qualified=False,sources=list(sources.values())))
    return docs,refs


class WrapperTests(unittest.TestCase):
    def test_full_synthetic_projection_and_two_modes(self):
        docs,refs=fixture();before=deepcopy(docs);args=m.project_inputs(docs,refs)
        self.assertEqual(docs,before);self.assertEqual(len(args['nav_rows']),1101);self.assertEqual(len(args['fx_rows']),6975)
        result=core.align_nav_usd_observations(**args);m.validate_result(result,args)
        self.assertEqual(len(result['rows']),253);self.assertEqual(result['mode_missing_counts']['STRICT_SAME_SESSION_FX'],2)
        self.assertEqual(result['mode_missing_counts']['BACKWARD_LATEST_VALID_FX'],0)
        self.assertEqual(args['nav_rows'][0]['original_csv_row'],docs['nav_csv'][0])

    def test_metadata_binding_attacks(self):
        changes=[lambda d:d['requirements_publication'].update(status='FAILED'),lambda d:d['nav_csv'][0].update(Close='2.5'),lambda d:d['fx_readback']['table_rows'][0]['source_reference'].update(table_row_index=False),lambda d:d['fx_readback'].update(historical_available_at_verified=True),lambda d:d['fx_readback']['window_253'].pop()]
        for change in changes:
            with self.subTest(change=change):
                docs,refs=fixture();change(docs)
                with self.assertRaises(ValueError):m.project_inputs(docs,refs)

    def test_execute_false_and_existing_namespace_reject_early(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)/'new'),patch.object(m,'load_inputs',side_effect=AssertionError('must not load')):
            self.assertEqual(m.run()['status'],'NOT_EXECUTED')
            with self.assertRaises(ValueError):m.run(execute=1)
            m.OUTPUT.mkdir()
            with self.assertRaises(ValueError):m.run(execute=True)

    def test_postpublication_drift_leaves_failure_no_retry(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)/'new'),patch.object(m,'load_inputs',return_value=({'requirements':{'source_hashes':{}},'nav_manifest':{},'nav_snapshot':{},'fx_manifest':{}},{'requirements':{'path':'synthetic','sha256':'a'*64}},{},core)),patch.object(m,'project_inputs',return_value={}),patch.object(core,'align_nav_usd_observations',return_value={}),patch.object(m,'validate_result'),patch.object(m,'guard',side_effect=[None,None,ValueError('post publication drift')]):
            with self.assertRaises(ValueError):m.run(execute=True)
            self.assertTrue((m.OUTPUT/'publication.json').exists());self.assertTrue((m.OUTPUT/'failure.json').exists())
            with self.assertRaises(ValueError):m.run(execute=True)

if __name__=='__main__':unittest.main()
