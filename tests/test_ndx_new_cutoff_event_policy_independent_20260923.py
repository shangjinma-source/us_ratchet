"""Independent event bridge counterexamples. No actual bridge build or publication."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_event_policy_20260923 as m


def event():
    return {'1654522200': dict(date=1654522200, numerator=20, denominator=1, splitRatio='20:1')}


class IndependentBridgeTests(unittest.TestCase):
    def test_ratio_metadata_and_registry_are_not_interchangeable(self):
        old = event()
        task = dict(event_policy=[dict(session='2022-06-06', kind='ORDINARY_SPLIT', numerator=20, denominator=1)])
        registry = {('AMZN','2022-06-06'):dict(eligible=True,ratio=Fraction(20),reference={'fixed':True})}
        for attack in ('wrong_ticker', 'wrong_day', 'ratio_text', 'negative_pair', 'duplicate_day'):
            new = deepcopy(old); reg = deepcopy(registry)
            if attack == 'wrong_ticker': reg = {('OTHER','2022-06-06'):next(iter(reg.values()))}
            elif attack == 'wrong_day': reg = {('AMZN','2022-06-07'):next(iter(reg.values()))}
            elif attack == 'ratio_text': new['1654522200']['splitRatio']='10:1'
            elif attack == 'negative_pair': new['1654522200']['splitRatio']='-20:-1'
            else: new['1654522260']=dict(date=1654522260,numerator=20,denominator=1,splitRatio='20:1')
            with self.subTest(attack=attack), self.assertRaises(ValueError): m.map_events('AMZN',old,new,task,reg)

    def test_equal_ratio_changed_payload_still_unresolved_and_dividends_not_splits(self):
        old=event(); new=deepcopy(old);new['1654522200']['numerator']=40;new['1654522200']['denominator']=2;new['1654522200']['splitRatio']='40:2'
        task=dict(event_policy=[dict(session='2022-06-06',kind='ORDINARY_SPLIT',numerator=20,denominator=1)])
        registry={('AMZN','2022-06-06'):dict(eligible=True,ratio=Fraction(20),reference={})}
        mapped=m.map_events('AMZN',old,new,task,registry)
        self.assertFalse(mapped['exact_payload_equal'])
        self.assertEqual(mapped['events'][0]['status'],'UNRESOLVED_RETURNED_EVENT')
        raw=json.dumps({'chart':{'error':None,'result':[{'meta':{'symbol':'AMZN'},'events':{'dividends':old}}]}}).encode()
        self.assertEqual(m.raw_events(raw,'AMZN')[0],{})

    def test_old_task_link_checks_payload_plan_and_nested_audit(self):
        planned=dict(ticker='X',reason=None,event_policy=[])
        old=dict(task=deepcopy(planned),plan_sha256='hard',status='CONDITIONAL_NUMERIC_RESULT')
        audit=dict(ticker='X',reason=None,status='CONDITIONAL_NUMERIC_RESULT',audit=dict(ticker='X'))
        for attack in ('plan_sha','payload','nested'):
            task=deepcopy(old);detail=deepcopy(audit)
            if attack=='plan_sha':task['plan_sha256']='other'
            elif attack=='payload':task['task']['event_policy']=[{'fake':True}]
            else:detail['audit']['ticker']='Y'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.old_task_link(task,planned,detail,'hard')

    def test_publication_source_drift_preserves_evidence_and_blocks_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'fixed/bridge.json'
            with patch.object(m,'OUTPUT',target),patch.object(m,'build',return_value={'source_hashes':{},'promotion_allowed':False}),\
                 patch.object(m,'guard',side_effect=[None,ValueError('source drift')]):
                with self.assertRaisesRegex(ValueError,'source drift'):m.publish()
            self.assertTrue(target.exists())
            with patch.object(m,'OUTPUT',target),patch.object(m,'build') as build:
                with self.assertRaisesRegex(ValueError,'Fresh fixed'):m.publish()
                build.assert_not_called()


if __name__=='__main__':unittest.main()
