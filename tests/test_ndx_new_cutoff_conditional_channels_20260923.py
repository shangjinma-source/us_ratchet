"""Synthetic raw channels only: never build the real 101-channel artifact."""
from copy import deepcopy
from datetime import date,datetime,timedelta
from decimal import Context,Inexact,ROUND_DOWN,localcontext
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_conditional_channels_20260923 as m


def fixture(split=True,ticker='TEST'):
    end=date(2026,9,21);calendar=[(end-timedelta(days=i)).isoformat() for i in range(126,-1,-1)]
    times=[int(datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=m.NY).timestamp()) for day in calendar+['2026-09-22']]
    splits={str(times[80]):dict(date=times[80],numerator=2.0,denominator=1.0,splitRatio='2:1')} if split else {}
    events={'splits':splits,'dividends':{str(times[100]):dict(date=times[100],amount=1.25)}}
    data=dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),
        timestamp=times,indicators=dict(quote=[dict(open=[10.125]*127+[None],high=[11.0]*128,low=[9.0]*128,
            close=[10.125]*127+[None],volume=[10000000]*128)]),events=events)
    raw=json.dumps(dict(chart=dict(error=None,result=[data]))).encode()
    policies=[dict(provider_event_key=str(times[80]),session=calendar[80],policy=dict(session=calendar[80],numerator=2,denominator=1,kind='ORDINARY_SPLIT'),
        status='SPECIFIC_POLICY_MATCH',specific_event_reference={'synthetic':True})] if split else []
    bridge=dict(ticker=ticker,new_raw_reference={'path':'synthetic','sha256':hashlib.sha256(raw).hexdigest()},
        new_receipt_reference={'path':'syntheticreceipt','sha256':'a'*64},new_decoded_sha256=hashlib.sha256(raw).hexdigest(),
        new_returned_splits=splits,event_policy_bridge=dict(events=policies,regular_floor=None),
        new_window_derivation=dict(reasons=[],policy_floor=None))
    return raw,bridge,calendar


class ChannelTests(unittest.TestCase):
    def test_unsupported_json_value_is_not_silently_null(self):
        with self.assertRaises(TypeError):m.encode({'unsupported':object()})

    def test_later_factor_split_return_dividends_and_latest_null(self):
        raw,bridge,calendar=fixture()
        result=m.reconstruct(raw,bridge,calendar)
        self.assertEqual(result['quote_rows'][79]['nominal_close'],'20.250')
        self.assertEqual(result['quote_rows'][80]['nominal_close'],'10.125')
        self.assertEqual(len(result['quote_rows']),127)
        self.assertEqual(len(result['channel_input']['price_returns']),126)
        self.assertTrue(all(row['price_return']==0 for row in result['channel_input']['price_returns']))
        self.assertTrue(result['returned_events']['dividends'])
        self.assertFalse(result['channel_input']['dividend_cash_flows_included'])
        self.assertEqual(result['channel_input']['liquidity']['status'],'BLOCKED_VOLUME_UNIT_UNKNOWN')

    def test_no_split_volume_is_conditional_not_certified(self):
        result=m.reconstruct(*fixture(False))
        self.assertEqual(len(result['channel_input']['liquidity']['rows']),63)
        self.assertFalse(result['volume_units_independently_certified'])
        self.assertTrue(result['channel_input']['zero_unreported_events_is_explicit_research_condition'])

    def test_explicit_context_does_not_inherit_traps(self):
        args=fixture();expected=m.reconstruct(*args)
        context=Context(prec=3,rounding=ROUND_DOWN);context.traps[Inexact]=True
        with localcontext(context):actual=m.reconstruct(*args)
        self.assertEqual(actual,expected)

    def test_price_gap_does_not_call_kernel_and_volume_gap_does(self):
        raw,bridge,calendar=fixture()
        bridge['new_window_derivation']['reasons']=['NEW_127_OBSERVED_OHLC_COVERAGE_SHORT']
        with patch.object(m.kernel,'build_channel_input',side_effect=AssertionError('called')):
            result=m.reconstruct(raw,bridge,calendar)
        self.assertEqual(result['status'],'BLOCKED_PRICE_INPUT');self.assertIsNone(result['channel_input'])
        bridge['new_window_derivation']['reasons']=['SAVED_VOLUME_UNIT_RESTRICTION_RETAINED']
        self.assertEqual(m.reconstruct(raw,bridge,calendar)['status'],'CONDITIONAL_NUMERIC_RESULT')

    def test_metadata_hash_policy_and_calendar_tamper_fail(self):
        for attack in ('decoded','policy','calendar','metadata'):
            raw,bridge,calendar=fixture()
            if attack=='decoded':bridge['new_decoded_sha256']='0'*64
            elif attack=='policy':bridge['event_policy_bridge']['events']=[]
            elif attack=='calendar':calendar[0]='2020-01-01'
            else:
                data=json.loads(raw);data['chart']['result'][0]['meta']['currency']='EUR';raw=json.dumps(data).encode()
                bridge['new_decoded_sha256']=hashlib.sha256(raw).hexdigest()
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.reconstruct(raw,bridge,calendar)

    def test_namespace_and_source_guard(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'channels.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
        with patch.object(m.Path,'read_bytes',return_value=b'drift'):
            with self.assertRaises(ValueError):m.guard({})


if __name__=='__main__':unittest.main()
