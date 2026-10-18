"""Pure helper fixtures; no real bridge build, publication or HTTP."""
from copy import deepcopy
from fractions import Fraction
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_event_policy_20260923 as m


def fixture():
    events={'1654522200':dict(date=1654522200,numerator=20.0,denominator=1.0,splitRatio='20:1')}
    task=dict(event_policy=[dict(session='2022-06-06',kind='ORDINARY_SPLIT',numerator=20,denominator=1)],regular_floor=None)
    registry={('AMZN','2022-06-06'):dict(eligible=True,ratio=Fraction(20),reference={'test':'fixed'})}
    return events,task,registry


class BridgeTests(unittest.TestCase):
    def test_specific_ratio_and_date_must_match_even_when_raw_equal(self):
        events,task,registry=fixture()
        result=m.map_events('AMZN',events,events,task,registry)
        self.assertTrue(result['exact_payload_equal'])
        self.assertEqual(result['events'][0]['policy']['kind'],'ORDINARY_SPLIT')
        for attack in ('ratio','eligible','missing'):
            reg=deepcopy(registry)
            if attack=='ratio':reg[('AMZN','2022-06-06')]['ratio']=Fraction(10)
            if attack=='eligible':reg[('AMZN','2022-06-06')]['eligible']=False
            if attack=='missing':reg={}
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.map_events('AMZN',events,events,task,reg)

    def test_changed_new_ratio_missing_and_added_are_gaps(self):
        old,task,registry=fixture();new=deepcopy(old)
        new['1654522200'].update(numerator=10.0,splitRatio='10:1')
        result=m.map_events('AMZN',old,new,task,registry)
        self.assertEqual(result['changed_event_keys'],['1654522200'])
        self.assertIsNone(result['events'][0]['policy'])
        self.assertEqual(m.map_events('AMZN',old,{},task,registry)['missing_event_keys'],['1654522200'])
        added=m.map_events('AMZN',{},old,dict(event_policy=[],regular_floor=None),{})
        self.assertEqual(added['added_event_keys'],['1654522200'])
        self.assertEqual(added['events'][0]['status'],'UNRESOLVED_RETURNED_EVENT')

    def test_complex_not_promoted_partition_requires_floor(self):
        events,task,registry=fixture()
        self.assertIsNone(m.map_events('X',events,events,dict(event_policy=[]),{})['events'][0]['policy'])
        task['event_policy'][0]['kind']='BEFORE_PARTITION_UNMODELLED';task['regular_floor']='2022-06-06'
        result=m.map_events('AMZN',events,events,task,{})
        self.assertFalse(result['events'][0]['event_economics_modelled'])
        task['regular_floor']='2022-06-03'
        with self.assertRaises(ValueError):m.map_events('AMZN',events,events,task,{})

    def test_raw_transport_hash_not_decoded_hash_and_wrong_symbol(self):
        events,_,_=fixture();raw=json.dumps({'chart':{'error':None,'result':[{'meta':{'symbol':'AMZN'},'events':{'splits':events}}]}}).encode()
        splits,decoded=m.raw_events(gzip.compress(raw),'AMZN')
        self.assertEqual(splits,events);self.assertEqual(decoded,m.hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError):m.raw_events(raw,'QCOM')
        bad=deepcopy(events);bad['1654522200']['numerator']=True
        with self.assertRaises(ValueError):m.normalized(bad)

    def test_new_window_reasons_are_independent_of_old_blocked_label(self):
        complete=dict(ticker='HON',status='OBSERVATION_NUMERICAL_COVERAGE_ONLY',latest_complete_ohlcv_date='2026-09-21',
            ohlc_127={'numerical_coverage_complete':True},volume_63={'numerical_coverage_complete':True})
        result=m.new_window('HON',complete,['2026-06-26','2026-06-29','2026-06-30'],'2026-06-29')
        self.assertEqual(result['post_floor_observed_day_count'],2)
        self.assertEqual(result['reasons'],['NEW_POST_ACTION_PARTITION_SHORT_OF_127'])
        complete['ticker']='SPCX';complete['ohlc_127']['numerical_coverage_complete']=False
        self.assertIn('NEW_127_OBSERVED_OHLC_COVERAGE_SHORT',m.new_window('SPCX',complete,[],None)['reasons'])

    def test_namespace_guard_before_build_and_pending_anchor(self):
        with patch.object(m,'build') as build:
            with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'bridge.json'):
                with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
        with patch.dict(m.BOUND,{'completeness':('x','PENDING')}):
            with self.assertRaises(ValueError):m.reference('completeness')

    def test_source_and_timezone_bytes_locked(self):
        with patch.object(m.Path,'read_bytes',return_value=b'changed'):
            with self.assertRaises(ValueError):m.guard({})

    def test_negative_ratio_text_and_unlinked_old_audit_rejected(self):
        events,_,_=fixture();events['1654522200']['splitRatio']='-20:-1'
        with self.assertRaises(ValueError):m.normalized(events)
        planned=dict(ticker='X',reason=None,mode='CALCULATE')
        task=dict(task=deepcopy(planned),plan_sha256='a',status='CONDITIONAL_NUMERIC_RESULT')
        audit=dict(ticker='X',reason=None,status='CONDITIONAL_NUMERIC_RESULT',audit={'ticker':'X'})
        m.old_task_link(task,planned,audit,'a')
        for field in ('ticker','status','reason'):
            wrong=deepcopy(audit);wrong[field]='WRONG'
            with self.subTest(field=field),self.assertRaises(ValueError):m.old_task_link(task,planned,wrong,'a')


if __name__=='__main__':unittest.main()
