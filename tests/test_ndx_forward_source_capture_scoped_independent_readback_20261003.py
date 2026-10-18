from copy import deepcopy
from decimal import localcontext, Inexact
from unittest import mock
import unittest
from scripts import ndx_forward_source_capture_scoped_independent_readback_20261003 as m
from backtest import ndx_forward_source_capture_scoped_research as producer
from test_ndx_forward_source_capture_scoped_research import args
from test_ndx_forward_source_capture_research import fixture

def verify(a,p=None):
    p=producer.plan_scoped_forward_source_capture(**a) if p is None else p
    return m.inspect_plan(p,a['frontier'],a['source_csv_bytes'],a['baseline_csv_bytes'],a['tzif_bytes'],a['capture_started_at_utc'],a['observed_at_utc'])

class ReaderTests(unittest.TestCase):
    def test_no_new_and_whole_interval(self):
        a=args();a['source_csv_bytes']=deepcopy(a['baseline_csv_bytes'])
        r=verify(a);self.assertEqual(r['status_observed'],'NO_NEW_SOURCE_SESSION');self.assertIsNone(r['candidate'])
        r=verify(args());self.assertIsNotNone(r['candidate']);self.assertFalse(r['candidate_seal_allowed'])
        for a in [fixture(start='2026-09-25T19:59:00+00:00',end='2026-09-25T20:01:00+00:00'),fixture(start='2026-09-28T13:29:00+00:00',end='2026-09-28T13:30:00+00:00')]:self.assertIsNone(verify(a)['candidate'])
    def test_all_four_groups_preserved_and_tamper_rejected(self):
        a=args();p=producer.plan_scoped_forward_source_capture(**a)
        r=verify(a,p)
        for role in ('source','baseline'):
            for ticker in ('QQQ','SPY'):
                self.assertEqual(len(r['details'][role][ticker]['out_of_scope_ohlc_diagnostics']),1)
                for field,value in [('original_csv_bytes_base64','YQ=='),('included_original_row_indexes',[True]),('scoped_sha256','0'*64),('original_byte_count',False)]:
                    q=deepcopy(p);q['csv_scope_evidence'][role][ticker][field]=value
                    with self.subTest(role=role,ticker=ticker,field=field),self.assertRaises(ValueError):verify(a,q)
        q=deepcopy(p);q['capture_plan']['fresh_observation']=0
        with self.assertRaises(ValueError):verify(a,q)
    def test_revision_encoding_and_scope_damage(self):
        a=args();a['source_csv_bytes']['QQQ']=a['source_csv_bytes']['QQQ'].replace(b',10,12,8,10,100',b',10.00,12,8,1E1,100')
        with localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True
            self.assertEqual(verify(a)['revision_count'],0)
        a=args();p=producer.plan_scoped_forward_source_capture(**a)
        a['source_csv_bytes']['SPY']=a['source_csv_bytes']['SPY'].replace(b'2026-09-25,10,12,8',b'2026-09-25,7,12,8')
        with self.assertRaises(ValueError):verify(a,p)
    def test_all_scoped_authority_and_parent_roles(self):
        a=args();p=producer.plan_scoped_forward_source_capture(**a)
        for key,value in p.items():
            if value is False:
                q=deepcopy(p);q[key]=True
                with self.subTest(key=key),self.assertRaises(ValueError):verify(a,q)
        from datetime import date,timedelta
        days=[];d=date(2026,7,1)
        while d<date(2026,9,24):
            if d.weekday()<5:days.append(d.isoformat())
            d+=timedelta(days=1)
        days=days[:59]+['2026-09-24'];gaps=['2026-09-25','2026-09-28','2026-09-29','2026-09-30','2026-10-01']
        rows=[dict(session=d,kind='SEALED_PARENT_OBSERVED_SESSION',parent_session_index=i,eligibility_reverified=False) for i,d in enumerate(days)]
        rows += [dict(session=d,kind='MISSED_OBSERVATION',gap_event_index=i,gap_event_sha256='a'*64,counts_as_observed_session=False,decision_eligible=False) for i,d in enumerate(gaps)]
        refs={k:dict(path=k,sha256='b'*64) for k in ('frontier','baseline_QQQ','baseline_SPY')}
        flags=dict.fromkeys(('candidate_seal_allowed','cohort_registration_allowed','canonical_calendar_append_allowed','point_in_time_verified','promotion_allowed','oos_recovery_completed'),False)
        f=dict(schema='OBSERVATION_GAP_FRONTIER_RESEARCH_V1',source_hashes={},last_observed_session='2026-09-24',last_accounted_session='2026-10-01',last_accounted_gap_session='2026-10-01',unaccounted_source_dates=[],input_references={t:refs['baseline_'+t] for t in ('QQQ','SPY')},known_accounted_rows=rows,parent_observed_session_count=60,accounted_gap_count=5,**flags)
        r=dict(schema='OBSERVATION_GAP_FRONTIER_PUBLICATION_V1',status='PUBLISHED_ACCOUNTED_FRONTIER_ONLY_NO_ELIGIBILITY',source_hashes={},frontier_reference=refs['frontier'],**flags)
        m.validate_saved_frontier(f,r,refs)
        for index,key,value in [(0,'parent_session_index',False),(60,'counts_as_observed_session',True),(60,'kind','SEALED_PARENT_OBSERVED_SESSION')]:
            bad=deepcopy(f);bad['known_accounted_rows'][index][key]=value
            with self.assertRaises(ValueError):m.validate_saved_frontier(bad,r,refs)

    def test_pending_no_reads(self):
        with mock.patch.object(m,'CAPTURE_SHA',None),mock.patch.object(m.Path,'read_bytes',side_effect=AssertionError('No reads')):
            with self.assertRaises(ValueError):m.readback(execute=True)
        with self.assertRaises(ValueError):m.readback(execute=False)

if __name__=='__main__':unittest.main()
