"""Synthetic split/partition arithmetic only, never full101 build."""
from copy import deepcopy
from datetime import datetime
import gzip
import hashlib
import json
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_conditional_channels_20260923 as fixture

m=fixture.m


def repack(data,bridge,compressed=False):
    decoded=json.dumps(data).encode();raw=gzip.compress(decoded) if compressed else decoded
    bridge['new_decoded_sha256']=hashlib.sha256(decoded).hexdigest()
    bridge['new_returned_splits']=deepcopy(data['chart']['result'][0]['events']['splits'])
    bridge['new_raw_reference']['sha256']=hashlib.sha256(raw).hexdigest()
    return raw


class IndependentReview(unittest.TestCase):
    def test_missing_numeric_volume_is_closed_before_any_reconstruction(self):
        _,_,calendar=fixture.fixture(False)
        members=['S'+str(i) for i in range(101)]
        complete=dict(promotion_allowed=False,observed_reference_calendar_127=calendar,
            rows=[dict(ticker=t,role='OBSERVED_MEMBER_PROVIDER_CHANNEL',
                       volume_63=dict(numerical_coverage_complete=True)) for t in members])
        bridge=dict(schema='NEW_CUTOFF_101_EVENT_POLICY_BRIDGE_V1',
            input_references=dict(completeness=m.reference('completeness')),
            price_generation_allowed=False,promotion_allowed=False,observed_reference_calendar_127=calendar,
            rows=[dict(ticker=t,new_window_derivation=dict(reasons=[])) for t in members])
        # Build's fixed end-date contract is separate from this synthetic fixture.
        calendar[-1]='2026-09-21'
        for attack in ('coverage','reason'):
            c,b=deepcopy(complete),deepcopy(bridge)
            if attack=='coverage':c['rows'][0]['volume_63']['numerical_coverage_complete']=False
            else:b['rows'][0]['new_window_derivation']['reasons']=['NEW_63_RAW_VOLUME_COVERAGE_SHORT']
            with self.subTest(attack=attack),patch.object(m,'guard'),patch.object(m,'read',side_effect=[m.encode(b),m.encode(c)]),patch.object(m,'reconstruct') as reconstruct:
                with self.assertRaisesRegex(ValueError,'volume'):m.build()
                reconstruct.assert_not_called()

    def test_two_later_factors_and_reverse_split_day_once(self):
        raw,bridge,calendar=fixture.fixture();data=json.loads(raw);result=data['chart']['result'][0]
        stamp=result['timestamp'][100];day=calendar[100]
        result['events']['splits'][str(stamp)]=dict(date=stamp,numerator=1,denominator=5,splitRatio='1:5')
        bridge['event_policy_bridge']['events'].append(dict(provider_event_key=str(stamp),session=day,
            policy=dict(session=day,numerator=1,denominator=5,kind='ORDINARY_SPLIT'),status='SPECIFIC_POLICY_MATCH',specific_event_reference={'synthetic':True}))
        raw=repack(data,bridge,True);value=m.reconstruct(raw,bridge,calendar)
        rows=value['quote_rows']
        self.assertEqual((rows[79]['split_factor_numerator'],rows[79]['split_factor_denominator']),('2','5'))
        self.assertEqual((rows[80]['split_factor_numerator'],rows[80]['split_factor_denominator']),('1','5'))
        self.assertEqual((rows[100]['split_factor_numerator'],rows[100]['split_factor_denominator']),('1','1'))
        self.assertTrue(all(r['price_return']==0 for r in value['channel_input']['price_returns']))
        self.assertEqual(len(value['channel_input']['price_returns']),126)

    def test_unmodelled_floor_equal_first_day_not_ordinary(self):
        raw,bridge,calendar=fixture.fixture(False);data=json.loads(raw);result=data['chart']['result'][0]
        stamp=result['timestamp'][0]
        result['events']['splits']={str(stamp):dict(date=stamp,numerator=3,denominator=1,splitRatio='3:1')}
        bridge['event_policy_bridge'].update(regular_floor=calendar[0],events=[dict(provider_event_key=str(stamp),session=calendar[0],
            status='SPECIFIC_POLICY_MATCH',policy=dict(session=calendar[0],numerator=3,denominator=1,kind='BEFORE_PARTITION_UNMODELLED'))])
        bridge['new_window_derivation']['policy_floor']=calendar[0]
        raw=repack(data,bridge);value=m.reconstruct(raw,bridge,calendar)
        self.assertTrue(all(r['split_factor_numerator']=='1' for r in value['quote_rows']))
        bridge['new_window_derivation']['policy_floor']=calendar[1]
        with self.assertRaisesRegex(ValueError,'partition floor'):m.reconstruct(raw,bridge,calendar)

    def test_missing_middle_row_cannot_compress_or_reuse_old_output(self):
        raw,bridge,calendar=fixture.fixture(False);data=json.loads(raw);result=data['chart']['result'][0]
        result['timestamp'].pop(50)
        for values in result['indicators']['quote'][0].values():values.pop(50)
        raw=repack(data,bridge)
        with self.assertRaisesRegex(ValueError,'127 dates'):m.reconstruct(raw,bridge,calendar)

    def test_complex_short_history_reasons_block_price_before_kernel(self):
        for ticker,reason in (('CMCSA','COMPLEX_RETURNED_EVENT_NOT_ORDINARY_CERTIFICATE'),('TRI','UNRESOLVED_RETURNED_EVENTS'),
            ('HON','NEW_POST_ACTION_PARTITION_SHORT_OF_127'),('SPCX','NEW_127_OBSERVED_OHLC_COVERAGE_SHORT'),('HONA','NEW_127_OBSERVED_OHLC_COVERAGE_SHORT')):
            raw,bridge,calendar=fixture.fixture(False,ticker)
            bridge['new_window_derivation']['reasons']=[reason]
            with self.subTest(ticker=ticker),patch.object(m.kernel,'build_channel_input') as kernel:
                value=m.reconstruct(raw,bridge,calendar);kernel.assert_not_called()
                self.assertEqual(value['status'],'BLOCKED_PRICE_INPUT');self.assertIsNone(value['quote_rows'])
                self.assertFalse(value['legal_training_input_admitted'])


if __name__=='__main__':unittest.main()
