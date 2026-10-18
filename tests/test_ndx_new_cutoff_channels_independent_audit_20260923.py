import copy
from datetime import datetime,timedelta,timezone
from decimal import Decimal, Context, localcontext
import gzip
import json
import unittest
from scripts import ndx_new_cutoff_channels_independent_audit_20260923 as m


def fixture(event_index=10,future=False):
    start=datetime(2026,1,1,15,tzinfo=timezone.utc)
    stamps=[int((start+timedelta(days=i)).timestamp()) for i in range(127)]
    calendar=[m.day(t) for t in stamps]
    event=dict(date=stamps[event_index],numerator=2,denominator=1,splitRatio='2:1')
    events={'splits':{str(event['date']):event},'dividends':{str(stamps[20]):dict(date=stamps[20],amount=7.5)}}
    policies=[dict(session=calendar[event_index],kind='ORDINARY_SPLIT',numerator=2,denominator=1)]
    if future:
        stamp=stamps[-1]+86400;events['splits'][str(stamp)]=dict(date=stamp,numerator=3,denominator=1,splitRatio='3:1')
        policies.append(dict(session=m.day(stamp),kind='ORDINARY_SPLIT',numerator=3,denominator=1))
    body={'chart':{'error':None,'result':[dict(meta=dict(symbol='TEST',currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),timestamp=stamps,events=events,
        indicators={'quote':[dict(open=[100.25]*127,high=[101]*127,low=[100]*127,close=[100.5]*127,volume=[1000000]*127)]})]}}
    return json.dumps(body).encode(),calendar,policies


class OracleTests(unittest.TestCase):
    def test_nonzero_return_rounding_is_subtract_inside_float(self):
        raw,calendar,policy=fixture();body=json.loads(raw)
        quote=body['chart']['result'][0]['indicators']['quote'][0]
        quote['close'][-2:]=[10,11]
        value=m.derive(json.dumps(body).encode(),'TEST',calendar,policy)
        actual=value['price_returns'][-1]['price_return']
        self.assertEqual(actual,0.1)
        self.assertNotEqual(actual,float(m.Fraction(11,10))-1)

    def test_nonterminating_factor_declared_decimal_rounding_boundaries(self):
        raw,calendar,policy=fixture();body=json.loads(raw)
        event=next(iter(body['chart']['result'][0]['events']['splits'].values()))
        event.update(numerator=2,denominator=3,splitRatio='2:3')
        policy[0].update(numerator=2,denominator=3)
        # JSON exact long coefficient, no float conversion in the fixture input.
        raw=json.dumps(body).replace('100.25','12345678901234567890123456789012345678901234567890123456789012345678901234567890123.12345').encode()
        value=m.derive(raw,'TEST',calendar,policy)
        source=Decimal('12345678901234567890123456789012345678901234567890123456789012345678901234567890123.12345')
        with localcontext(Context(prec=80)):
            expected=source*Decimal(2)/Decimal(3)
        self.assertEqual(Decimal(value['quote_rows'][0]['nominal_open']),expected)
        with localcontext(Context(prec=50)):
            expected50=source*Decimal(2)/Decimal(3)
            error=abs(expected-expected50)
        self.assertGreater(error,0)
        self.assertGreaterEqual(Decimal(value['maximum_nominal_reconstruction_error']),error)

    def test_dollar_volume_uses_declared_50_digit_boundary(self):
        raw,calendar,policy=fixture()
        raw=raw.replace(b'100.5',b'123456789012345678901234567890123456789012345678901234567890.12345')
        value=m.derive(raw,'TEST',calendar,policy)
        row=value['quote_rows'][-1]
        with localcontext(Context(prec=50)):
            expected=Decimal(row['nominal_close'])*Decimal(1000000)
        self.assertEqual(Decimal(value['liquidity']['rows'][-1]['dollar_volume']),expected)

    def test_saved_numeric_tampering_and_permission_upgrade(self):
        raw,calendar,policy=fixture();expected=m.derive(raw,'TEST',calendar,policy)
        channel={key:copy.deepcopy(expected[key]) for key in ('price_rows','price_returns','liquidity','returned_events')}
        channel.update(schema='CONDITIONAL_PROVIDER_CHANNEL_INPUT_V1',ticker='TEST',calendar=calendar,cutoff=calendar[-1],
            regular_floor=None,event_policy=policy,minimum_median_dollar_volume_usd=50000000,
            coordinate_kind='PROVIDER_TICKER_CHANNEL_NOT_SECURITY_ID',event_policy_is_external_unverified_assertion=True,
            zero_unreported_events_is_explicit_research_condition=True,maximum_nominal_reconstruction_error='0')
        channel.update(dict.fromkeys(('source_assertions_authenticated','security_identity_verified','volume_units_independently_certified',
            'complete_actions_verified','exchange_calendar_verified','dividend_cash_flows_included','legal_training_input_admitted',
            'fit_performed','point_in_time_verified','promotion_allowed'),False))
        m.inspect_numeric(raw,'TEST',calendar,policy,None,expected['quote_rows'],channel)
        for attack in ('return_bool','dividend','volume','authority','nominal'):
            copied=copy.deepcopy(channel);rows=copy.deepcopy(expected['quote_rows'])
            if attack=='return_bool':copied['price_returns'][0]['price_return']=False
            if attack=='dividend':copied['returned_events']['dividends']={}
            if attack=='volume':copied['liquidity']['rows'][0]['raw_volume']=True
            if attack=='authority':copied['promotion_allowed']=True
            if attack=='nominal':rows[0]['nominal_open']='999'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_numeric(raw,'TEST',calendar,policy,None,rows,copied)

    def test_fraction_split_return_and_dividend_exclusion(self):
        raw,calendar,policy=fixture();v=m.derive(raw,'TEST',calendar,policy)
        self.assertEqual(v['quote_rows'][0]['nominal_close'],'201')
        self.assertEqual(v['quote_rows'][10]['nominal_close'],'100.5')
        self.assertEqual(v['price_returns'][9]['price_return'],0.0)
        self.assertTrue(all(r['price_return']==0.0 for r in v['price_returns']))
        self.assertEqual(v['liquidity']['median_dollar_volume_usd'],'100500000')
        self.assertEqual(len(v['liquidity']['rows']),63)
        self.assertTrue(v['returned_events']['dividends'])

    def test_all_later_events_and_volume_restriction(self):
        raw,calendar,policy=fixture(future=True);v=m.derive(gzip.compress(raw),'TEST',calendar,policy)
        self.assertEqual(v['quote_rows'][0]['split_factor_numerator'],'6')
        self.assertEqual(v['quote_rows'][-1]['split_factor_numerator'],'3')
        self.assertEqual(v['liquidity']['status'],'BLOCKED_VOLUME_UNIT_UNKNOWN')
        self.assertIsNone(v['liquidity']['rows'])
        raw,calendar,policy=fixture(event_index=90)
        self.assertIsNone(m.derive(raw,'TEST',calendar,policy)['liquidity']['median_dollar_volume_usd'])

    def test_partition_calendar_and_ratio_attack(self):
        raw,calendar,policy=fixture()
        with self.assertRaises(ValueError):m.derive(raw,'TEST',calendar,policy,calendar[1])
        with self.assertRaises(ValueError):m.derive(raw,'TEST',calendar[1:],policy)
        bad=copy.deepcopy(policy);bad[0]['numerator']=20
        with self.assertRaises(ValueError):m.derive(raw,'TEST',calendar,bad)
        body=json.loads(raw);next(iter(body['chart']['result'][0]['events']['splits'].values()))['splitRatio']='-2:-1'
        with self.assertRaises(ValueError):m.derive(json.dumps(body).encode(),'TEST',calendar,policy)

    def test_decimal_context_and_raw_missing_not_filled(self):
        raw,calendar,policy=fixture()
        expected=m.derive(raw,'TEST',calendar,policy)
        with localcontext() as context:
            context.prec=6
            self.assertEqual(expected,m.derive(raw,'TEST',calendar,policy))
        body=json.loads(raw);body['chart']['result'][0]['indicators']['quote'][0]['close'][-1]=None
        with self.assertRaises(ValueError):m.derive(json.dumps(body).encode(),'TEST',calendar,policy)


if __name__=='__main__':unittest.main()

