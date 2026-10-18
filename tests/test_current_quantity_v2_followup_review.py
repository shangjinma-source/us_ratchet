import json
import unittest
from datetime import datetime,date,timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo
import test_current_quantity_v2_touch_review as touch_fixtures
from data import current_quantity_v2_followup_review as module
from data.current_quantity_v2_paper_action_sources import daily_url
from scripts.current_research_official_alert_capture import URL
from data.current_research_intraday_execution import decode_intraday_reference


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        args,save,event=touch_fixtures.TouchTests().fixture();self.files=args['files'];self.pins=args['source_hashes']
        self.binding=dict(decision_id='a'*64,research_version='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH',available_cash_exact='20000')
        event.update(decision_id='a'*64,research_context=dict(research_id='a'*24,**{k:v for k,v in self.binding.items() if k!='decision_id'}),generated_not_confirmed_displayed=True,actual_fill_inferred=False)
        save('event',event);self.event=event
        self.days=[];day=date(2026,10,15)
        while len(self.days)<21:
            if day.weekday()<5:self.days.append(day.isoformat())
            day+=timedelta(days=1)
        self.calendar=dict(schema='OFFICIAL_SCHEDULED_US_EQUITY_CLOSES_V1',session_dates=self.days,
            closes={d:datetime.fromisoformat(d+'T16:00:00').replace(tzinfo=ZoneInfo('America/New_York')).isoformat() for d in self.days},source_hashes={})
        raw=json.dumps(self.calendar).encode();(self.root/'calendar.json').write_bytes(raw)
        self.addCleanup(patch.stopall);patch.object(module,'CALENDAR_PATH','calendar.json').start();patch.object(module,'CALENDAR_SHA',sha256(raw).hexdigest()).start()
        self.observations=[]
        self.action_evidence=None
        for day in self.days[1:]:self.daily(day)

    def daily(self,day,events=None,received=None):
        directory=self.root/day;directory.mkdir(exist_ok=True)
        stamp=int(datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York')).timestamp())
        channel=dict(meta=dict(symbol='AAA',currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),timestamp=[stamp],indicators={'quote':[dict(open=[11],high=[12],low=[10],close=[11])]},events=events or {})
        raw=json.dumps(dict(chart=dict(error=None,result=[channel]))).encode()
        receipt=json.dumps(dict(http_status=200,ticker='AAA',raw_sha256=sha256(raw).hexdigest(),received_at_utc=received or self.calendar['closes'][day])).encode()
        decoded=json.dumps(dict(ticker='AAA',receipt_sha256=sha256(receipt).hexdigest(),decoded_sha256=sha256(raw).hexdigest(),raw_returned_events=channel['events'])).encode()
        entry={}
        for suffix,key,value in [('.response.bin','raw_sha256',raw),('.receipt.json','receipt_sha256',receipt),('.decoded.json','decoded_sha256',decoded)]:
            path=day+'/AAA'+suffix;(self.root/path).write_bytes(value);self.pins[path]=sha256(value).hexdigest();entry[key]=self.pins[path]
        self.observations=[r for r in self.observations if r['date']!=day]+[dict(security_id='A',ticker='AAA',date=day,relative_directory=day,entry=entry)]

    def run_review(self,now='2026-11-13T22:00:00+00:00'):
        return module.review_reference_followup(root=self.root,binding=self.binding,event_path='event',files=self.files,source_hashes=self.pins,daily_observations=self.observations,now=datetime.fromisoformat(now),action_evidence=self.action_evidence)

    def test_complete_real_quote_format_never_infers_trade_or_unverified_change(self):
        result=self.run_review()
        self.assertFalse(result['performance_computed'])
        for row in result['orders'][0]['horizons']:
            self.assertEqual(row['status'],'PENDING_INTERVAL_ACTION_SOURCES')
            self.assertIsNone(row['price_change_vs_reference']);self.assertEqual(row['execution_status'],'NOT_PROVIDED')

    def test_binding_missing_calendar_and_missing_bar(self):
        self.binding['available_cash_exact']='30000'
        with self.assertRaisesRegex(ValueError,'BINDING'):self.run_review()
        self.binding['available_cash_exact']='20000';self.observations.pop(0)
        self.assertEqual(self.run_review()['orders'][0]['horizons'][0]['status'],'PENDING_BARS')
        (self.root/'calendar.json').unlink()
        self.assertTrue(all(r['status']=='PENDING_VERIFIED_CALENDAR' for r in self.run_review()['orders'][0]['horizons']))

    def test_order_subset_rows_are_matched_by_sid(self):
        self.event['rows'].insert(0,dict(security_id='UNORDERED',ticker='OTHER'))
        raw=json.dumps(self.event).encode();self.files['event']=raw;self.pins['event']=sha256(raw).hexdigest()
        self.assertEqual(self.run_review()['orders'][0]['ticker'],'AAA')
        self.event['rows'].append(dict(self.event['rows'][1]))
        raw=json.dumps(self.event).encode();self.files['event']=raw;self.pins['event']=sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'ORIGINAL_REFERENCE_UNVERIFIED'):self.run_review()

    def test_split_and_preclose_capture_are_blocked(self):
        day=self.days[1];stamp=int(datetime.fromisoformat(day+'T12:00:00+00:00').timestamp())
        self.daily(day,events={'splits':{'x':dict(date=stamp,numerator=2,denominator=1)}})
        self.assertEqual(self.run_review()['orders'][0]['horizons'][0]['status'],'BLOCKED_KNOWN_CORPORATE_ACTION')
        self.daily(day,received=day+'T19:59:59+00:00')
        self.assertEqual(self.run_review()['orders'][0]['horizons'][0]['status'],'BLOCKED_DAILY_SOURCE_VALIDATION')

    def test_dst_close_boundary_and_no_calendar_extrapolation(self):
        target=self.days[-1]
        self.assertTrue(self.calendar['closes'][target].endswith('-05:00'))
        self.assertEqual(self.run_review(target+'T20:59:59+00:00')['orders'][0]['horizons'][2]['status'],'PENDING_SESSION_CLOSE')
        self.assertEqual(self.run_review(target+'T21:00:00+00:00')['orders'][0]['horizons'][2]['status'],'PENDING_INTERVAL_ACTION_SOURCES')
        short=dict(self.calendar,session_dates=self.days[:2],closes={d:self.calendar['closes'][d] for d in self.days[:2]})
        raw=json.dumps(short).encode();(self.root/'calendar.json').write_bytes(raw)
        with patch.object(module,'CALENDAR_SHA',sha256(raw).hexdigest()):
            self.assertEqual(self.run_review()['orders'][0]['horizons'][1]['status'],'PENDING_CALENDAR_HORIZON')

    def actions(self,title='Unrelated issuer news',events=None):
        def save(path,value):
            raw=value if isinstance(value,bytes) else json.dumps(value).encode()
            self.files[path]=raw;self.pins[path]=sha256(raw).hexdigest()
        first=datetime.fromisoformat('2026-10-15T00:00:00+00:00');last=datetime.fromisoformat('2026-11-12T22:00:00+00:00')
        channel=dict(meta=dict(symbol='AAA',longName='Example Corporation',currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),
            timestamp=[int(datetime.fromisoformat(day+'T15:00:00+00:00').timestamp()) for day in self.days[1:]],
            indicators={'quote':[dict(close=[11]*20)]},events=events or {})
        save('actions.raw',dict(chart=dict(error=None,result=[channel])))
        save('actions.receipt',dict(security_id='A',ticker='AAA',raw_path='actions.raw',raw_sha256=self.pins['actions.raw'],http_status=200,body_truncated=False,transport_error=None,requested_from=first.isoformat(),requested_through=last.isoformat(),received_at=last.isoformat(),events_requested=['dividends','splits'],interval='1d',url=daily_url('AAA',first,last),request_period1=int(first.timestamp()),request_period2=int(last.timestamp())+1))
        save('rss.raw',('<rss><channel><item><title>'+title+'</title><pubDate>Thu, 12 Nov 2026 21:00:00 GMT</pubDate></item></channel></rss>').encode())
        save('rss.receipt',dict(url=URL,http_status=200,started_at=last.isoformat(),received_at=last.isoformat(),raw_sha256=self.pins['rss.raw'],stored_bytes=len(self.files['rss.raw'])))
        self.action_evidence={'A':dict(daily_receipt_path='actions.receipt',rss_raw_path='rss.raw',rss_receipt_path='rss.receipt')}

    def test_bounded_sources_allow_conditional_price_change_but_not_return(self):
        self.actions();result=self.run_review()
        for row in result['orders'][0]['horizons']:
            self.assertEqual(row['status'],'CONDITIONAL_PRICE_CHANGE')
            self.assertEqual(row['price_change_vs_reference'],'1/10')
            self.assertEqual(row['execution_status'],'NOT_PROVIDED')
            self.assertFalse(row['action_review']['coverage_complete'])
        self.assertFalse(result['performance_computed'])
        for title in ('Example Corporation announces corporate action',
                      'Example&#160;Corporation announces split',
                      'Example  Corporation announces split',
                      'Example &lt;b&gt;Corporation&lt;/b&gt; announces split'):
            with self.subTest(title=title):
                self.actions(title=title)
                self.assertEqual(self.run_review()['orders'][0]['horizons'][0]['status'],'BLOCKED_OFFICIAL_ACTION_CANDIDATE')
        self.actions();self.files['rss.raw']+=b' '
        self.assertEqual(self.run_review()['orders'][0]['horizons'][0]['status'],'BLOCKED_ACTION_SOURCE_VALIDATION')

    def test_real_sealed_forward_calendar_works_without_old_calendar(self):
        repo=Path(__file__).resolve().parents[1]
        with patch.object(module,'CALENDAR_PATH','absent-calendar.json'):
            result=module.review_reference_followup(root=repo,binding=self.binding,event_path='event',files=self.files,source_hashes=self.pins,daily_observations=[],now=datetime.fromisoformat('2026-10-16T20:00:00+00:00'))
        self.assertEqual(result['orders'][0]['horizons'][0]['target_session'],'2026-10-16')
        self.assertEqual(result['orders'][0]['horizons'][0]['status'],'PENDING_BARS')
        schedule=json.loads((repo/module.FORWARD_PATH).read_bytes())
        sessions={r['date']:r for r in schedule['sessions']}
        self.assertEqual(datetime.fromisoformat(sessions['2026-11-02']['close_at']).hour,21)
        self.assertEqual(datetime.fromisoformat(sessions['2026-11-27']['close_at']).hour,18)
        self.assertTrue(sessions['2026-11-27']['early_close'])
        # Also check the following reference day through the same sealed reader.
        def shifted(value):
            if isinstance(value,dict):return {k:shifted(v) for k,v in value.items()}
            if isinstance(value,list):return [shifted(v) for v in value]
            if type(value)is int and value>1000000000:return value+86400
            if isinstance(value,str):return value.replace('2026-10-15','2026-10-16')
            return value
        raw=json.dumps(shifted(json.loads(self.files['o.raw']))).encode();self.files['o.raw']=raw;self.pins['o.raw']=sha256(raw).hexdigest()
        receipt=shifted(json.loads(self.files['o.receipt']));receipt['raw_sha256']=self.pins['o.raw']
        self.files['o.receipt']=json.dumps(receipt).encode();self.pins['o.receipt']=sha256(self.files['o.receipt']).hexdigest()
        event=shifted(self.event)
        for capture in event['captures']:capture['sha256']=self.pins[capture['path']]
        event['rows'][0]['reference']=decode_intraday_reference(raw,ticker='AAA',now=datetime.fromisoformat(event['observed_at']))
        event['reference_valid_until']=event['rows'][0]['reference']['refresh_by']
        self.files['event']=json.dumps(event).encode();self.pins['event']=sha256(self.files['event']).hexdigest()
        repo=Path(__file__).resolve().parents[1]
        with patch.object(module,'CALENDAR_PATH','absent-calendar.json'):
            result=module.review_reference_followup(root=repo,binding=self.binding,event_path='event',files=self.files,source_hashes=self.pins,daily_observations=[],now=datetime.fromisoformat('2026-10-19T21:00:00+00:00'))
        row=result['orders'][0]['horizons'][0]
        self.assertEqual(row['target_session'],'2026-10-19');self.assertEqual(row['status'],'PENDING_BARS')
        self.assertIn(module.FORWARD_PATH,result['source_hashes'])

    def test_interval_price_mismatch_short_request_and_future_receipt(self):
        def replace(path,value):
            self.files[path]=json.dumps(value).encode();self.pins[path]=sha256(self.files[path]).hexdigest()
        self.actions();raw=json.loads(self.files['actions.raw']);raw['chart']['result'][0]['indicators']['quote'][0]['close'][0]=22
        replace('actions.raw',raw);receipt=json.loads(self.files['actions.receipt']);receipt['raw_sha256']=self.pins['actions.raw'];replace('actions.receipt',receipt)
        self.assertEqual(self.run_review()['orders'][0]['horizons'][0]['status'],'BLOCKED_INTERVAL_PRICE_COORDINATE_MISMATCH')
        self.actions();receipt=json.loads(self.files['actions.receipt']);receipt['requested_from']='2026-10-16T00:00:00+00:00';replace('actions.receipt',receipt)
        self.assertEqual(self.run_review()['orders'][0]['horizons'][0]['status'],'BLOCKED_ACTION_SOURCE_VALIDATION')
        self.actions();receipt=json.loads(self.files['actions.receipt']);receipt['received_at']='2027-01-01T00:00:00+00:00';replace('actions.receipt',receipt)
        self.assertEqual(self.run_review()['orders'][0]['horizons'][0]['status'],'BLOCKED_ACTION_SOURCE_VALIDATION')

    def test_post_horizon_split_blocks_but_future_split_and_cash_dividend_differ(self):
        late=int(datetime.fromisoformat('2026-10-20T13:30:00+00:00').timestamp())
        future=int(datetime.fromisoformat('2026-12-01T14:30:00+00:00').timestamp())
        for kind,timestamp,expected in [('splits',late,'BLOCKED_POST_HORIZON_UNIT_CHANGE'),
                                        ('splits',future,'CONDITIONAL_PRICE_CHANGE'),
                                        ('dividends',late,'CONDITIONAL_PRICE_CHANGE')]:
            self.actions(events={kind:{'event':dict(date=timestamp,numerator=2,denominator=1)}})
            self.assertEqual(self.run_review()['orders'][0]['horizons'][0]['status'],expected)
        self.actions()
        # Independently check late corporate actions in the saved-close triple,
        # even when the separate interval action source does not report them.
        self.daily(self.days[1],events={'splits':{'event':dict(date=late,numerator=2,denominator=1)}},received='2026-11-12T22:00:00+00:00')
        self.assertEqual(self.run_review()['orders'][0]['horizons'][0]['status'],'BLOCKED_POST_HORIZON_UNIT_CHANGE')
        self.daily(self.days[1],received='2026-11-13T21:00:00+00:00')
        self.actions()
        self.assertEqual(self.run_review()['orders'][0]['horizons'][0]['status'],'BLOCKED_ACTION_INTERVAL_BEFORE_PRICE_CAPTURE')


if __name__=='__main__':unittest.main()
