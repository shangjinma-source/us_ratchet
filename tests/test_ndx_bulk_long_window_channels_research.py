from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from decimal import Context,Inexact,localcontext
import json,struct,unittest
from backtest import ndx_bulk_long_window_channels_research as m


def fixture():
    end=date(2026,9,21);days=[]
    while len(days)<253:
        if end.weekday()<5:days.append(end.isoformat())
        end-=timedelta(days=1)
    days.reverse()
    times=[int(datetime.fromisoformat(d+'T15:00:00').replace(tzinfo=timezone.utc).timestamp()) for d in days+['2026-09-22']]
    splits={str(times[150]):dict(date=times[150],numerator=2,denominator=1,splitRatio='2:1')}
    channel=dict(meta=dict(symbol='SYN',currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),timestamp=times,indicators=dict(quote=[dict(open=[10.125]*253+[None],close=[10.125]*253+[None],high=[11]*254,low=[9]*254,volume=[100]*254)]),events=dict(splits=splits,dividends={'d':dict(amount=1.25,date=times[170])}))
    raw=json.dumps(dict(chart=dict(error=None,result=[channel]))).encode();rawref=dict(path='synthetic.raw',sha256=m.sha(raw));receiptr=dict(path='receipt.json',sha256='a'*64)
    bridge=dict(ticker='SYN',new_raw_reference=deepcopy(rawref),new_receipt_reference=receiptr,new_decoded_sha256=m.sha(raw),new_returned_splits=deepcopy(splits),event_policy_bridge=dict(regular_floor=None,events=[dict(provider_event_key=str(times[150]),session=days[150],status='SPECIFIC_POLICY_MATCH',specific_event_reference=dict(path='policy',sha256='b'*64),policy=dict(session=days[150],numerator=2,denominator=1,kind='ORDINARY_SPLIT'))]))
    tzif=b'TZif\0'+b'\0'*15+struct.pack('>6l',0,0,0,0,1,4)+struct.pack('>lbb',0,0,0)+b'UTC\0'
    receipt=dict(ticker='SYN',raw_path=rawref['path'],raw_sha256=rawref['sha256'],raw_bytes=len(raw),http_status=200,promotion_allowed=False,point_in_time_verified=False,received_at_utc='2026-09-23T12:00:00+00:00')
    return dict(raw_bytes=raw,raw_reference=rawref,receipt=receipt,receipt_reference=receiptr,bridge_row=bridge,calendar253=days,tzif_bytes=tzif,window_contract=deepcopy(m.CONTRACT))


def modify_raw(args,change):
    body=json.loads(args['raw_bytes']);change(body['chart']['result'][0]);raw=json.dumps(body).encode();args['raw_bytes']=raw
    args['raw_reference']['sha256']=m.sha(raw);args['bridge_row']['new_raw_reference']=deepcopy(args['raw_reference']);args['bridge_row']['new_decoded_sha256']=m.sha(raw)
    args['receipt'].update(raw_sha256=m.sha(raw),raw_bytes=len(raw))


class ChannelsTests(unittest.TestCase):
    def test_split_equivalence_windows_dividends(self):
        args=fixture();r=m.reconstruct_long_channel(**args)
        self.assertEqual(r['status'],'CONDITIONAL_NUMERIC_RESULT');self.assertEqual(len(r['quote_rows']),253)
        self.assertEqual(r['quote_rows'][149]['nominal_close_exact'],'81/4');self.assertEqual(r['quote_rows'][150]['nominal_close_exact'],'81/8')
        self.assertTrue(all(x['split_only_return_exact']=='0' for x in r['return_rows']))
        self.assertEqual(len(r['training_returns']),126);self.assertEqual(len(r['evaluation_returns']),126)
        self.assertEqual(r['training_returns'][-1]['session'],r['evaluation_returns'][0]['previous_session'])
        self.assertFalse({x['session'] for x in r['training_returns']}&{x['session'] for x in r['evaluation_returns']})
        self.assertEqual(r['returned_events']['dividends']['d']['amount'],'1.25')
        self.assertFalse(r['provider_price_unit_verified']);self.assertFalse(r['dividend_cash_flows_included'])

    def test_hostile_context(self):
        args=fixture();expected=m.reconstruct_long_channel(**args);context=Context(prec=2);context.traps[Inexact]=True
        with localcontext(context):actual=m.reconstruct_long_channel(**args)
        self.assertEqual(actual,expected)

    def test_missing_predecessor_and_floor_block_without_compression(self):
        args=fixture();args['bridge_row']['event_policy_bridge']['regular_floor']=args['calendar253'][1]
        out=m.reconstruct_long_channel(**args);self.assertIsNone(out['quote_rows']);self.assertIn('REQUIRED_PREDECESSOR_BEFORE_REGULAR_FLOOR',out['reasons'])
        args=fixture()
        def remove(channel):
            channel['timestamp'].pop(126)
            for values in channel['indicators']['quote'][0].values():values.pop(126)
        modify_raw(args,remove);out=m.reconstruct_long_channel(**args)
        self.assertEqual(out['missing_price_dates'],[args['calendar253'][126]]);self.assertEqual(len(out['calendar']),253)
        args=fixture();modify_raw(args,lambda c:c['indicators']['quote'][0]['close'].__setitem__(0,None))
        self.assertEqual(m.reconstruct_long_channel(**args)['missing_price_fields'][0]['session'],args['calendar253'][0])

    def test_wrong_actions_metadata_ohlc_refs_rejected(self):
        mutations=[lambda a:a['bridge_row']['event_policy_bridge']['events'][0].update(status='UNRESOLVED'),lambda a:modify_raw(a,lambda c:c['meta'].update(symbol='RENAMED')),lambda a:modify_raw(a,lambda c:c['events'].update(spinoffs={})),lambda a:modify_raw(a,lambda c:c['indicators']['quote'][0]['high'].__setitem__(1,1)),lambda a:a['receipt'].update(raw_sha256='0'*64)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                args=fixture();mutate(args)
                with self.assertRaises(ValueError):m.reconstruct_long_channel(**args)

    def test_reverse_split_and_partition_at_first_date(self):
        args=fixture()
        def reverse(c):
            e=next(iter(c['events']['splits'].values()));e.update(numerator=1,denominator=5,splitRatio='1:5')
        modify_raw(args,reverse);args['bridge_row']['new_returned_splits']=json.loads(args['raw_bytes'])['chart']['result'][0]['events']['splits'];args['bridge_row']['event_policy_bridge']['events'][0]['policy'].update(numerator=1,denominator=5)
        out=m.reconstruct_long_channel(**args);self.assertEqual(out['quote_rows'][0]['nominal_close_exact'],'81/40')
        args=fixture();args['bridge_row']['event_policy_bridge']['regular_floor']=args['calendar253'][0]
        self.assertEqual(m.reconstruct_long_channel(**args)['status'],'CONDITIONAL_NUMERIC_RESULT')

if __name__=='__main__':unittest.main()
