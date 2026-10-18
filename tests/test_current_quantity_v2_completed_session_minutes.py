from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse, parse_qs
import json
import unittest

from data.current_quantity_v2_completed_session_minutes import capture, decode


ARGS = dict(security_id='synthetic-A', ticker='AAA', session='2026-10-14',
            session_open='2026-10-14T09:30:00-04:00', session_close='2026-10-14T09:33:00-04:00')
NOW = datetime.fromisoformat('2026-10-15T10:00:00-04:00')


def raw():
    start = int(datetime.fromisoformat(ARGS['session_open']).timestamp())
    value = dict(chart=dict(error=None,result=[dict(meta=dict(symbol='AAA',currency='USD',
        instrumentType='EQUITY',dataGranularity='1m',exchangeTimezoneName='America/New_York',
        currentTradingPeriod={'regular':{'start':int(NOW.timestamp()),'end':int(NOW.timestamp())+390*60}}),
        timestamp=[start,start+60,start+120], indicators={'quote':[dict(open=[1,1,1],
        high=[2,2,2],low=[1,1,1],close=[1,1,1],volume=[1,0,1])]}, events={})]))
    return json.dumps(value).replace('"close": [1, 1, 1]', '"close": [1.1234567890123456789, 1, 1]').encode()


class CompletedMinutesTests(unittest.TestCase):
    def test_explicit_prior_session_capture_decimal_and_later_timestamp(self):
        with TemporaryDirectory() as folder:
            output = Path(folder)/'capture'; calls=[]; body=raw()
            def fetch(url): calls.append(url); return body
            result=capture(directory=output,**ARGS,calendar_source_reference='synthetic-test-calendar',fetch=fetch,clock=lambda:NOW)
            self.assertEqual(result['status'],'COMPLETE_SESSION_MINUTES')
            self.assertEqual(result['minutes'][0]['close'],'1.1234567890123456789')
            self.assertEqual(result['observed_through'],'2026-10-15T14:00:00+00:00')
            self.assertEqual(result['minutes'][0]['session'],'2026-10-14')
            self.assertNotIn('fees',result)
            query=parse_qs(urlparse(calls[0]).query)
            self.assertNotIn('range',query);self.assertEqual(query['interval'],['1m'])
            self.assertEqual(query['events'],['div,splits'])
            self.assertEqual(int(query['period1'][0]),int(datetime.fromisoformat(ARGS['session_open']).timestamp()))
            receipt=json.loads((output/'receipt.json').read_bytes())
            self.assertEqual(receipt['raw_sha256'],sha256(body).hexdigest())
            self.assertEqual((output/'response.bin').read_bytes(),body)
            with self.assertRaises(FileExistsError):capture(directory=output,**ARGS,calendar_source_reference='synthetic-test-calendar',fetch=fetch,clock=lambda:NOW)
            self.assertEqual(len(calls),1)

    def test_missing_null_and_wrong_identity_or_action(self):
        for mode in ('missing','null','symbol','currency','split','duplicate'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                value=json.loads(raw());c=value['chart']['result'][0]
                if mode=='missing':
                    c['timestamp'].pop(1)
                    for values in c['indicators']['quote'][0].values():values.pop(1)
                elif mode=='null':c['indicators']['quote'][0]['close'][1]=None
                elif mode=='symbol':c['meta']['symbol']='BBB'
                elif mode=='currency':c['meta']['currency']='CAD'
                elif mode=='split':c['events']={'splits':{'s':{'date':c['timestamp'][0]}}}
                else:c['timestamp'][1]=c['timestamp'][0]
                body=json.dumps(value).encode();output=Path(folder)/'capture'
                call=lambda:capture(directory=output,**ARGS,calendar_source_reference='synthetic',fetch=lambda _:body,clock=lambda:NOW)
                if mode in ('missing','null'):
                    result=call();self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(len(result['missing_minute_starts']),1)
                else:
                    with self.assertRaises(ValueError):call()
                self.assertEqual((output/'response.bin').read_bytes(),body)
                self.assertEqual(json.loads((output/'receipt.json').read_bytes())['status'],'UNKNOWN')

    def test_unfinished_session_no_fetch_or_output(self):
        with TemporaryDirectory() as folder:
            output=Path(folder)/'capture'
            with self.assertRaisesRegex(ValueError,'SESSION_NOT_COMPLETED'):
                capture(directory=output,**ARGS,calendar_source_reference='synthetic',
                    fetch=lambda _:self.fail('future fetch'),clock=lambda:datetime.fromisoformat(ARGS['session_open']))
            self.assertFalse(output.exists())

    def test_clock_rollback_preserves_received_raw_without_usable_minutes(self):
        with TemporaryDirectory() as folder:
            output=Path(folder)/'capture';times=iter([NOW,NOW-timedelta(seconds=1)]);body=raw()
            with self.assertRaisesRegex(ValueError,'CLOCK_ROLLBACK'):
                capture(directory=output,**ARGS,calendar_source_reference='synthetic',
                    fetch=lambda _:body,clock=lambda:next(times))
            self.assertEqual((output/'response.bin').read_bytes(),body)
            receipt=json.loads((output/'receipt.json').read_bytes())
            self.assertEqual(receipt['raw_sha256'],sha256(body).hexdigest())
            self.assertEqual(receipt['status'],'UNKNOWN');self.assertFalse((output/'minutes.json').exists())

    def test_captured_identity_with_explicit_fees_consumed_by_actual_settlement(self):
        from test_current_quantity_v2_simulated_settlement import fixture
        from backtest.current_quantity_v2_simulated_settlement import settle
        state, _, args=fixture(); evidence={}
        observed=datetime.fromisoformat('2026-10-16T10:00:00-04:00')
        with TemporaryDirectory() as folder:
            for oid,order in state['chain']['ledger']['orders'].items():
                sid=order['security_id'];ref=args['execution_references'][sid]
                opening=datetime.fromisoformat(ref['session_open']);closing=datetime.fromisoformat(ref['session_close'])
                count=int((closing-opening).total_seconds()/60)
                value=json.loads(raw());chart=value['chart']['result'][0]
                chart['meta']['symbol']=ref['ticker']
                chart['timestamp']=[int(opening.timestamp())+60*i for i in range(count)]
                price=51 if order['side']=='SELL' else 0.9
                chart['indicators']['quote']=[{**{k:[price]*count for k in ('open','high','low','close')},'volume':[1]*count}]
                body=json.dumps(value).encode()
                item=capture(directory=Path(folder)/sid,security_id=sid,ticker=ref['ticker'],
                    session=ref['session'],session_open=ref['session_open'],session_close=ref['session_close'],
                    calendar_source_reference='synthetic',fetch=lambda _,body=body:body,clock=lambda:observed)
                self.assertEqual(item['status'],'COMPLETE_SESSION_MINUTES')
                item['fees']='0'  # Explicit test assumption; adapter supplies none.
                evidence[oid]=item
            settled=settle(simulation=state,evidence=evidence,observed_through=observed.isoformat(),evaluated_at=observed.isoformat())
            self.assertTrue(all(o['closed']=='FILLED' for o in settled['chain']['ledger']['orders'].values()))


if __name__=='__main__':unittest.main()
