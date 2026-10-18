from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from decimal import Context,Inexact,localcontext
import gzip,json,unittest
from backtest import ndx_multidecision_scoring_history_research as m
from test_ndx_bulk_long_window_channels_research import fixture as small


def fixture():
    a=small();start=date(2023,1,2);end=date(2026,9,21);days=[]
    while start<=end:
        if start.weekday()<5:days.append(start.isoformat())
        start+=timedelta(days=1)
    times=[int(datetime.fromisoformat(d+'T15:00:00').replace(tzinfo=timezone.utc).timestamp()) for d in days]
    splitday='2026-06-12';stamp=times[days.index(splitday)]
    splits={str(stamp):dict(date=stamp,numerator=10,denominator=1,splitRatio='10:1')}
    body=json.loads(a['raw_bytes']);c=body['chart']['result'][0];c['timestamp']=times
    c['indicators']['quote']=[dict(open=[10.125]*len(days),close=[10.125]*len(days),high=[11]*len(days),low=[9]*len(days),volume=[100]*len(days))]
    c['events']=dict(splits=splits,dividends={'d':dict(date=stamp,amount=1.25)})
    a['bridge_row']['new_returned_splits']=splits;a['bridge_row']['event_policy_bridge']['events']=[dict(provider_event_key=str(stamp),session=splitday,status='SPECIFIC_POLICY_MATCH',specific_event_reference=dict(path='event',sha256='b'*64),policy=dict(session=splitday,numerator=10,denominator=1,kind='ORDINARY_SPLIT'))]
    a.pop('calendar253');a['reference_calendar']=days;a['window_contract']=deepcopy(m.CONTRACT)
    a['outer_inventory_contract']=dict(inventory_reference=dict(path='panel',sha256='c'*64),security_count=77,issuer_count=76,observed_provenance_count=101,preserved_sidecar_references={k:dict(path='panel',sha256='c'*64,json_pointer='/'+k) for k in m.SIDECARS})
    bind(a,body);return a


def bind(a,body,compressed=False):
    decoded=json.dumps(body).encode();raw=gzip.compress(decoded,mtime=0) if compressed else decoded
    a['raw_bytes']=raw;a['raw_reference']['sha256']=m.sha(raw);a['bridge_row']['new_raw_reference']=deepcopy(a['raw_reference']);a['bridge_row']['new_decoded_sha256']=m.sha(decoded);a['receipt'].update(raw_sha256=m.sha(raw),raw_bytes=len(raw))


class HistoryTests(unittest.TestCase):
    def test_full_windows_actions_and_context(self):
        a=fixture();before=deepcopy(a);r=m.materialize_scoring_history_channel(**a);self.assertEqual(a,before)
        self.assertEqual(r['raw_decode_count'],1);self.assertEqual(len(r['decisions']),6)
        for d in r['decisions']:
            self.assertEqual(len(d['required_price_dates']),505);self.assertEqual(len(d['windows']),13)
            for w in d['windows']:
                self.assertEqual(w['training_return_index_stop'],w['evaluation_return_index_start'])
                self.assertEqual(w['evaluation_return_index_stop']-w['evaluation_return_index_start'],126)
                self.assertLessEqual(w['evaluation_last_return_end'],d['cutoff'])
            self.assertEqual(d['windows'][-1]['evaluation_last_return_end'],d['cutoff'])
        old=next(q for q in r['quote_rows'] if q['session']=='2026-06-11');new=next(q for q in r['quote_rows'] if q['session']=='2026-06-12')
        self.assertEqual(old['nominal_close_exact'],'405/4');self.assertEqual(new['nominal_close_exact'],'81/8')
        self.assertTrue(all(v['split_only_return_exact']=='0' for v in r['return_rows']))
        self.assertEqual(r['returned_events']['dividends']['d']['amount'],'1.25')
        self.assertFalse(r['decision_time_action_knowledge_verified'])
        ctx=Context(prec=2);ctx.traps[Inexact]=True
        with localcontext(ctx):self.assertEqual(m.materialize_scoring_history_channel(**a),r)

    def test_floor_missing_slots_and_no_unequal_pooling(self):
        a=fixture();a['bridge_row']['event_policy_bridge']['regular_floor']='2025-02-24'
        r=m.materialize_scoring_history_channel(**a)
        self.assertFalse(r['decisions'][0]['complete_thirteen_window_numeric_supply'])
        self.assertEqual(len(r['decisions'][0]['windows']),13)
        self.assertTrue(any(w['status']=='CONDITIONAL_NUMERIC_WINDOW' for w in r['decisions'][-1]['windows']))
        self.assertEqual(len(r['return_rows']),len(r['calendar'])-1)
        floor=r['calendar'].index('2025-02-24');self.assertIsNone(r['return_rows'][floor-1]['split_only_return_exact'])
        self.assertEqual(r['return_rows'][floor]['split_only_return_exact'],'0')
        self.assertFalse(r['decisions'][0]['pooling_only_unblocked_windows_allowed'])
        a=fixture();body=json.loads(a['raw_bytes']);c=body['chart']['result'][0];i=a['reference_calendar'].index('2026-03-31');c['indicators']['quote'][0]['close'][i]=None;bind(a,body)
        r=m.materialize_scoring_history_channel(**a);self.assertIsNone(r['return_rows'][r['calendar'].index('2026-03-31')-1]['split_only_return_exact'])
        self.assertEqual(r['decisions'][0]['windows'][-1]['status'],'BLOCKED_WINDOW')

    def test_action_calendar_and_receipt_rejections(self):
        mutations=[lambda a:a['bridge_row']['event_policy_bridge']['events'][0].update(status='UNKNOWN'),lambda a:a['reference_calendar'].remove('2026-06-12'),lambda a:a['window_contract'].update(price_count_per_decision=253),lambda a:a['receipt'].update(point_in_time_verified=0),lambda a:a['outer_inventory_contract'].update(security_count=True)]
        for mutation in mutations:
            a=fixture();mutation(a)
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):m.materialize_scoring_history_channel(**a)
        a=fixture();body=json.loads(a['raw_bytes']);body['chart']['result'][0]['indicators']['quote'][0]['close'][-25]=True;bind(a,body)
        # Attack an in-union date, not unused provider suffix.
        body=json.loads(a['raw_bytes']);i=a['reference_calendar'].index('2026-08-31');body['chart']['result'][0]['indicators']['quote'][0]['close'][i]=True;bind(a,body)
        with self.assertRaises(ValueError):m.materialize_scoring_history_channel(**a)

    def test_gzip_one_decode_and_future_quote_not_training(self):
        a=fixture();body=json.loads(a['raw_bytes']);bind(a,body,True);out=m.materialize_scoring_history_channel(**a)
        body['chart']['result'][0]['indicators']['quote'][0]['close'][-1]=1
        bind(a,body,True);changed=m.materialize_scoring_history_channel(**a)
        self.assertEqual(out['quote_rows_sha256'],changed['quote_rows_sha256']);self.assertEqual(out['return_rows_sha256'],changed['return_rows_sha256'])
        self.assertNotEqual(out['raw_reference'],changed['raw_reference'])
        self.assertEqual(out['calendar'][-1],'2026-08-31')

if __name__=='__main__':unittest.main()
