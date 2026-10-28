"""Synthetic closed-domain integration; real isolated SQLite, no live IO.
Source coverage remains conditional. The test owns its entire generated identity
universe; this is not certification of historical issuer coverage or deployment.
"""
import tempfile, unittest
from pathlib import Path
from datetime import datetime, timedelta
from hashlib import sha256
from core.strategy_account_store import StrategyAccountStore
from core.strategy_account_ledger import canonical
from core.reentry_buy_scope_v1 import digest
from data.strategy_account_session_snapshot_v1 import account_session_snapshot
from data.monthly_peak_exit_reentry_store_v1 import MonthlyPeakExitReentryStore
from data import reentry_reference_evidence_v1 as source
from data.reentry_preview_projection_v1 import project_reference_preview
from data.strategy_account_preview import preview_scoped_account
from data.current_quantity_v2_paper_action_sources import daily_url, stamp
from scripts.current_research_official_alert_capture import URL

H='a'*64
DAYS=['2026-10-29','2026-10-30','2026-11-02','2026-11-03']
UNITS={s:'u'+s for s in 'ABC'}
def close(day): return day+('T21:00:00Z' if day>='2026-11-01' else 'T20:00:00Z')
def opening(day): return day+('T14:30:00Z' if day>='2026-11-01' else 'T13:30:00Z')

class CrossLayerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.clock=stamp('2026-10-28T19:00:00Z')
        self.account=StrategyAccountStore(self.root/'account.sqlite',clock=lambda:self.clock)
        self.state=self.account.initialize('synthetic',operation_id='init')
        self.append('CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED')
        for sid,q in [('A',4),('C',3)]:
            self.append('DIRECT_FILL',security_id=sid,side='BUY',quantity=q,price='100',fees='0',executed_at=self.clock.isoformat())
        self.risk=MonthlyPeakExitReentryStore(self.root/'risk.sqlite')
        self.risk.activate_reference(account_id='synthetic',activation_id=H,activation_at='2026-10-28T19:30:00Z',activation_session='2026-10-28',account_revision=self.state['revision'],source_configuration_sha256=H)
        self.contexts={};self.advance('2026-10-28',100)
    def append(self,kind,**kw):
        self.state,_=self.account.append(dict(kind=kind,event_id='event'+str(len(self.state['events'])),**kw),expected_revision=self.state['revision'])
    def snapshot(self,day):
        boundary=dict(schema='ARCHIVED_ACCOUNT_DECISION_BOUNDARY_V1',account_id='synthetic',session_date=day,session_close_at=close(day),decision_at=(stamp(close(day))+timedelta(minutes=5)).isoformat())
        self.clock=max(self.clock,stamp(close(day))+timedelta(minutes=10))
        raw=canonical(boundary)
        result=account_session_snapshot(self.account,account_id='synthetic',session_date=day,expected_latest_revision=self.state['revision'],decision_evidence=raw,decision_evidence_sha256=sha256(raw).hexdigest(),security_ids=list('ABC'))
        if 'shares' in result:
            self.assertFalse(result['decision_authority_verified']);self.assertFalse(result['units_certified'])
        return result
    def advance(self,day,price,recovery=()):
        epoch='2026-11-02' if day>='2026-11-02' else '2026-10-28'
        old=self.risk.read('synthetic');ref=self.risk.read_reference('synthetic')
        if day not in self.contexts:
            snap=self.snapshot(day);self.assertIn('shares',snap,snap)
            # Only this test's closed generated identity domain supplies units.
            self.contexts[day]=dict(completed_at=close(day),holdings=dict(snap,unit_ids=UNITS))
        observation=dict(decision_date=epoch,session_date=day,closes={'A':str(price),'B':'100','C':'100'},unit_ids=UNITS,evidence_sha256=digest([day,price,UNITS]))
        return self.risk.advance(account_id='synthetic',expected_previous_session=old['session_date'] if old else None,observations=[observation],baseline_targets={'A':4,'B':4,'C':1},expected_reference_version=ref['version'],activation_id=H,session_contexts={day:self.contexts[day]},recovery_evidence=recovery,authorized_monthly_reset=epoch if old and old['decision_date']!=epoch else None)
    def prepare(self,recovered=False):
        self.advance(DAYS[0],79)
        self.assertEqual(self.risk.read_reference('synthetic')['locks']['A']['held_quantity_at_exit'],4)
        self.clock=stamp('2026-10-30T14:01:00Z')
        self.append('DIRECT_FILL',security_id='A',side='SELL',quantity=4,price='79',fees='0',executed_at='2026-10-30T14:00:00Z')
        self.append('CASH_CONFIRM',amount='200',cash_basis='TOTAL_UNINVESTED')
        self.advance(DAYS[1],78);self.advance(DAYS[2],80 if recovered else 78);self.advance(DAYS[3],70)
        self.assertNotIn('A',self.risk.read('synthetic')['exited'])
        return self.make_source(recovered)
    def put(self,name,value):
        raw=value if isinstance(value,bytes) else canonical(value)
        (self.root/name).write_bytes(raw);return dict(path=name,sha256=sha256(raw).hexdigest())
    def make_source(self,recovered):
        identityraw=self.put('identity.txt',b'SYNTHETIC CLOSED UNIVERSE: ABC is A; no other identity or action exists.')
        identity=self.put('identity.json',dict(candidates=[dict(ticker='ABC',security_id='A',status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['identity.txt'])],source_hashes={'identity.txt':identityraw['sha256']}))
        prices=[79,78,80 if recovered else 78,70]
        series=dict(meta=dict(symbol='ABC',currency='USD',instrumentType='EQUITY',exchangeName='NMS',longName='Synthetic Corporation'),timestamp=[int(stamp(opening(d)).timestamp()) for d in DAYS],indicators={'quote':[{'close':prices}],'adjclose':[{'adjclose':prices}]},events={})
        raw=self.put('daily.json',{'chart':{'error':None,'result':[series]}})
        start=opening(DAYS[0]);end='2026-11-03T21:30:00Z'
        receipt=self.put('receipt.json',dict(security_id='A',ticker='ABC',http_status=200,body_truncated=False,transport_error=None,raw_sha256=raw['sha256'],stored_bytes=(self.root/'daily.json').stat().st_size,requested_from=start,requested_through=end,received_at='2026-11-03T21:31:00Z',interval='1d',events_requested=['dividends','splits'],url=daily_url('ABC',stamp(start),stamp(end)),request_period1=int(stamp(start).timestamp()),request_period2=int(stamp(end).timestamp())+1))
        rss=b'<rss><channel><pubDate>Tue, 03 Nov 2026 21:58:30 GMT</pubDate><item><title>Unrelated issuer ZZZ notice</title><description>ZZZ corporate notice</description><pubDate>Tue, 03 Nov 2026 21:58:30 GMT</pubDate><link>https://www.nasdaqtrader.com/TraderNews.aspx?id=TEST</link></item></channel></rss>'
        rssref=self.put('rss.xml',rss)
        rr=self.put('rss_receipt.json',dict(url=URL,http_status=200,body_truncated=False,transport_error=None,raw_sha256=rssref['sha256'],stored_bytes=len(rss),started_at='2026-11-03T21:59:00Z',received_at='2026-11-03T21:59:10Z'))
        config=dict(schema='SERVER_REFERENCE_INTERVAL_V1',reviewer_sha256=sha256(Path(source.__file__).read_bytes()).hexdigest(),origin_security_id='A',origin_unit_id='uA',exit_session=DAYS[0],decision_session=DAYS[-1],notice_scope_reviewer=self.put('notice_scope.py',Path(source.notice_scope.__file__).read_bytes()),calendar=self.put('calendar.json',dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=[dict(date=d,open=opening(d),close=close(d)) for d in DAYS])),approved_actions=self.put('actions.json',dict(schema='SERVER_APPROVED_REFERENCE_ACTIONS_V1',facts=[])),segments=[dict(identity=identity,ticker='ABC',security_id='A',exchange='NMS',unit_id='uA',start_session=DAYS[0],end_session=DAYS[-1],price_basis='ARCHIVED_SAME_UNIT_RAW_CLOSE',raw=raw,receipt=receipt)],official_rss=dict(raw=rssref,receipt=rr))
        return self.put('config.json',config)
    def review(self,config):
        return source.review_reference_interval(root=self.root,configuration_reference=config,lock=self.risk.read_reference('synthetic')['locks']['A'],decision_session=DAYS[-1],as_of='2026-11-03T22:00:00Z')
    def preview(self,review=None):
        now='2026-11-03T22:00:00Z';end='2026-11-03T22:01:00Z';targets={'A':4,'B':4,'C':1}
        marks={s:dict(security_id=s,currency='USD',price_basis='TEST',price='100',observed_at=now,source_hashes={'synthetic':H}) for s in targets}
        limits={s:dict(security_id=s,price_basis='TEST',buy='100',sell='100',observed_at=now,buy_evaluated=targets[s]>self.state['shares'].get(s,0),evaluated_account_revision=self.state['revision'],evaluated_net_gap=targets[s]-self.state['shares'].get(s,0),reference_valid_until=end,sell_reason='Authenticated synthetic sell',source_hashes={'synthetic':H}) for s in targets}
        difference=preview_scoped_account(state=self.state,legacy_shares={},marks=marks,limits=limits,target_quantities=targets,now=now,maximum_mark_age_seconds=120,fee_bps='0')
        original=dict(status='READY',account_revision=self.state['revision'],target_id='target',proposal_id='original',risk_valid_from=now,risk_valid_until=end,effective_target_quantities=targets,reference_quotes=limits,difference=difference,new_orders=difference['new_orders'])
        ref=self.risk.read_reference('synthetic');proofs=[]
        if review and ref['locks']:
            self.assertEqual(review['status'],'REFERENCE_SOURCE_REVIEWED_CONDITIONAL');self.assertFalse(review['coverage_complete'])
            # This closed synthetic universe is an additional test-only authority.
            authority=digest(dict(kind='SYNTHETIC_CLOSED_IDENTITY_DOMAIN_ONLY',source=review['identity_evidence_sha256'],members={'A':['A']}))
            proofs=[dict(origin_security_id='A',reference_version=ref['version'],reference_state_sha256=digest(ref),decision_session=DAYS[-1],buy_security_ids=['A','B'],original_binding=dict(account_id='synthetic',account_revision=self.state['revision'],target_id='target',proposal_id='original'),status='INTERSECTS_BUY_SCOPE',current_security_ids=['A'],identity_evidence_sha256=authority,price_status='LOCKED',price_evidence_sha256=review['evidence']['evidence_sha256'],price_completed_through=DAYS[-1])]
        before=(self.root/'account.sqlite').read_bytes()
        result=project_reference_preview(account=self.state,original_preview=original,reference_state=ref,decision_session=DAYS[-1],scope_proofs=proofs,now=now)
        self.assertEqual((self.root/'account.sqlite').read_bytes(),before)
        self.assertEqual([o for o in result['candidate_orders'] if o['side']=='SELL'],[o for o in difference['new_orders'] if o['side']=='SELL'])
        self.assertFalse(result['executable']);self.assertFalse(result['sell_proceeds_assumed'])
        return result,difference
    def test_cross_month_blocks_buy_preserves_sell_and_reallocates_real_cash(self):
        review=self.review(self.prepare());self.advance(DAYS[-1],70,[review['evidence']])
        result,original=self.preview(review)
        self.assertEqual([(o['security_id'],o['quantity']) for o in original['new_orders'] if o['side']=='BUY'],[('A',1),('B',1)])
        self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in result['candidate_orders']],[('C','SELL',2),('B','BUY',2)])
        self.assertEqual(result['difference']['new_buy_cash_required'],'200')
    def test_completed_recovery_commits_then_restores_cash_allocation(self):
        review=self.review(self.prepare(True));self.assertFalse(review['coverage_complete'])
        old=self.risk.read_reference('synthetic');self.advance(DAYS[-1],70,[review['evidence']]);new=self.risk.read_reference('synthetic')
        self.assertEqual(new['locks'],{});self.assertGreater(new['version'],old['version']);self.assertEqual(new['releases'][0]['recovered_session'],DAYS[2])
        result,original=self.preview();self.assertEqual(result['candidate_orders'],original['new_orders'])
        self.assertEqual([(o['security_id'],o['quantity']) for o in result['candidate_orders'] if o['side']=='BUY'],[('A',1),('B',1)])
    def test_missing_source_waits_only_buys_without_erasing_sell(self):
        config=self.prepare();before=self.risk.read_reference('synthetic');(self.root/'daily.json').write_bytes(b'corrupt')
        review=self.review(config);self.assertEqual(review['status'],'WAIT_REFERENCE_SOURCE')
        result,_=self.preview();self.assertEqual(result['status'],'WAIT_BUY_REFERENCE')
        self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in result['candidate_orders']],[('C','SELL',2)])
        self.assertEqual(self.risk.read_reference('synthetic'),before)
    def test_late_recorded_fill_stops_before_risk_reference_commit(self):
        before=(self.risk.read('synthetic'),self.risk.read_reference('synthetic'))
        self.clock=stamp('2026-10-30T14:00:00Z');self.append('DIRECT_FILL',security_id='A',side='SELL',quantity=1,price='79',fees='0',executed_at='2026-10-29T20:01:00Z')
        snapshot=self.snapshot(DAYS[0]);self.assertEqual(snapshot['reason'],'WAIT_LATE_RECORDED_FILL_RECONCILIATION');self.assertNotIn('shares',snapshot)
        self.assertEqual((self.risk.read('synthetic'),self.risk.read_reference('synthetic')),before)

if __name__=='__main__':unittest.main()
