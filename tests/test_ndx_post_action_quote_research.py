from copy import deepcopy
from datetime import datetime
import json
import unittest
from backtest import ndx_post_action_quote_research as core


def fixture():
    days=['2026-06-26','2026-06-29','2026-06-30','2026-07-01']
    times=[int(datetime.fromisoformat(d+'T13:30:00+00:00').timestamp()) for d in days]
    end=int(datetime.fromisoformat('2026-07-01T18:00:00+00:00').timestamp())
    data=dict(meta=dict(symbol='HON',currency='USD',exchangeTimezoneName='America/New_York',instrumentType='EQUITY',dataGranularity='1d'),
        timestamp=times,indicators=dict(quote=[dict(open=[100.,90.25,91.5,92.],close=[101.,91.25,92.5,93.])],adjclose=[dict(adjclose=[1,2,3,4])]),
        events=dict(splits={str(times[1]):dict(date=times[1],numerator=1907.,denominator=2000.,splitRatio='1907:2000')},
            dividends={str(times[2]):dict(date=times[2],amount=1.5)}))
    args=dict(ticker='HON',calendar=days[1:3],official_boundary=dict(ticker='HON',first_post_action_session='2026-06-29',post_action_cusip='438516205',role='POST_REVERSE_SPLIT_NEW_CUSIP'),
        request=dict(method='GET',credentials_sent=False,url=f'https://query1.finance.yahoo.com/v8/finance/chart/HON?period1={times[0]-86400}&period2={end}&interval=1d&events=div%2Csplits'),
        received_at_utc='2026-07-01T18:00:01+00:00',quote_field_basis=core.BASIS)
    return dict(chart=dict(error=None,result=[data])),args


def run(body,args):return core.reconstruct_post_action_quote(raw=json.dumps(body).encode(),**args)


class Tests(unittest.TestCase):
    def test_complex_events_retained_no_multiplier_and_decimal_exact(self):
        body,args=fixture();result=run(body,args)
        self.assertEqual([r['nominal_open'] for r in result['rows']],[90.25,91.5])
        self.assertEqual(result['returned_events'],body['chart']['result'][0]['events'])
        self.assertEqual(result['pre_boundary_provider_dates'],['2026-06-26'])
        self.assertEqual(result['receipt_or_later_dates_excluded'],['2026-07-01'])
        self.assertFalse(result['returned_split_like_events_were_share_multipliers'])
        self.assertEqual(core.decimal_quote_audit(json.dumps(body).encode(),result)['maximum_absolute_decimal_error'],'0')

    def test_dividend_and_adjclose_do_not_change_quote(self):
        body,args=fixture();expected=run(body,args)['rows']
        body['chart']['result'][0]['events']['dividends']={}
        body['chart']['result'][0]['indicators']['adjclose']=[dict(adjclose=[None]*4)]
        self.assertEqual(expected,run(body,args)['rows'])

    def test_later_action_even_outside_requested_completed_interval_rejected(self):
        body,args=fixture();data=body['chart']['result'][0];t=data['timestamp'][-1]
        data['events']['splits'][str(t)]=dict(date=t,numerator=2,denominator=1,splitRatio='2:1')
        with self.assertRaises(ValueError):run(body,args)

    def test_bad_raw_horizon_calendar_identity_ratio_or_basis_rejected(self):
        for mode in ('basis','ticker','currency','null','bool','ratio','duplicate','calendar','floor','blankdup','oldhorizon','missingevent'):
            body,args=fixture();data=body['chart']['result'][0]
            if mode=='basis':args['quote_field_basis']='UNKNOWN'
            if mode=='ticker':data['meta']['symbol']='HONA'
            if mode=='currency':data['meta']['currency']='CAD'
            if mode=='null':data['indicators']['quote'][0]['open'][0]=None
            if mode=='bool':data['indicators']['quote'][0]['open'][0]=True
            if mode=='ratio':next(iter(data['events']['splits'].values()))['splitRatio']='2:1'
            if mode=='duplicate':data['timestamp'][1]=data['timestamp'][0]
            if mode=='calendar':args['calendar']=args['calendar'][:1]
            if mode=='floor':args['calendar'].insert(0,'2026-06-26')
            if mode=='blankdup':args['request']['url']+='&period2='
            if mode=='oldhorizon':args['received_at_utc']='2026-07-02T18:00:01+00:00'
            if mode=='missingevent':data['events']['splits']={}
            with self.subTest(mode=mode),self.assertRaises(ValueError):run(body,args)

    def test_decimal_oracle_detects_edited_price(self):
        body,args=fixture();result=run(body,args);result['rows'][0]['nominal_close']+=1
        with self.assertRaises(ValueError):core.decimal_quote_audit(json.dumps(body).encode(),result)

    def test_decimal_oracle_rejects_missing_row_even_resigned_count(self):
        body,args=fixture();result=run(body,args);result['rows'].pop();result['row_count']=1
        with self.assertRaises(ValueError):core.decimal_quote_audit(json.dumps(body).encode(),result)


if __name__=='__main__':unittest.main()
