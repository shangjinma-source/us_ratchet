from copy import deepcopy
from datetime import datetime,timedelta
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_current_quantity_v2_current_cash_pullback_sources as initial_fixture
import test_current_research_capital_decision_v2 as capital_fixture
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_current_cash_plan import build_current_cash_plan,canonical,BASIS
from data.current_quantity_v2_current_cash_ledger_adapter import freeze_current_cash_proposal
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from data.current_quantity_v2_paper_service import QuantityV2PaperService
from data.current_quantity_v2_monthly_sources import QuantityV2MonthlySources
from data.current_quantity_v2_monthly_service import QuantityV2MonthlySourceBridge
from data.current_quantity_v2_monthly_continuation_sources import QuantityV2MonthlyContinuationSources
from data.current_quantity_v2_continuation_service import QuantityV2ContinuationSourceBridge
from data.current_quantity_v2_monthly_retarget import active_proposal
from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account
from data.current_quantity_v2_pullback_cap_store import PullbackCapStore

POLICY=initial_fixture.POLICY


class MonthlyPullbackTests(unittest.TestCase):
    setUp=initial_fixture.CurrentCashPullbackSourceTests.setUp
    fetch=initial_fixture.CurrentCashPullbackSourceTests.fetch
    provider_arguments=initial_fixture.CurrentCashPullbackSourceTests.provider_arguments

    def record(self,state,kind,oid,identifier,**fields):
        return self.store.record_event(account_id=state['ledger']['account_id'],
            event=dict(type=kind,order_id=oid,event_id=identifier,expected_revision=state['ledger']['revision'],**fields),
            clock=lambda:self.current)

    def prepare(self):
        initial=CurrentQuantityV2CurrentCashSources(**self.provider_arguments(),pullback_policy=POLICY,pullback_cap_store=self.cap)
        initial.capture(self.view['decision_id']);supplied=initial.resolve(self.view['decision_id'])
        proposal=freeze_current_cash_proposal(build_current_cash_plan(**supplied,now=self.current.isoformat()),supplied['execution_package'])
        self.store=QuantityV2PaperStore(self.root/'paper.sqlite3');aid=proposal['account_id']
        state=self.store.accept(account_id=aid,proposal_id=proposal['proposal_id'],operation_id='initial',
            factory=lambda now:dict(proposal=proposal,account_state=supplied['account_state']),clock=lambda:self.current)
        self.current+=timedelta(seconds=1)
        oid=next(oid for oid,row in state['ledger']['orders'].items() if row['security_id']=='A')
        state=self.record(state,'FILL',oid,'fill-A',quantity=2,price='9',fees='0',executed_at=self.current.isoformat())
        for i,oid in enumerate(state['ledger']['orders']):
            state=self.record(state,'CANCEL',oid,'cancel-'+str(i),cancelled_at=self.current.isoformat())
        self.current=datetime.fromisoformat('2026-11-02T09:32:17-05:00');self.market_last=10
        files=deepcopy(supplied['execution_package']['files']);pins=deepcopy(supplied['execution_package']['source_hashes'])
        for name in ('quote','source'):
            files[name]=b'SYNTHETIC MONTHLY EVIDENCE';pins[name]=sha256(files[name]).hexdigest()
        arguments=capital_fixture.CapitalV2Tests().arguments();day='2026-10-30'
        arguments.update(decision_date=day,source_hashes=deepcopy(pins))
        arguments['account_state'].update(asof=day,revision=state['ledger']['revision'],cash=state['ledger']['cash'],shares=state['ledger']['shares'])
        arguments['search_arguments'].update(decision_date=day,quote_as_of=day,prices={'B':'1'},
            metadata={'B':deepcopy(proposal['securities']['B'])},training_scenarios=[{'B':'2'},{'B':'1/2'}],scenario_dates=['2026-09-30',day])
        arguments['valuation_quotes']=[dict(security_id=sid,as_of=day,price='1',price_basis='SYNTHETIC_USD',source_references=['quote']) for sid in ('A','B')]
        decision=decide_quantity_v2_for_account(**arguments)
        def put(name,value):
            files[name]=canonical(value);pins[name]=sha256(files[name]).hexdigest();return name
        mandate=dict(account_id=aid,capital_decision_id=decision['decision_id'],target_month='2026-11',active_date='2026-11-02',source_references=['source'])
        securities=deepcopy(proposal['securities'])
        documents={k:put('monthly/'+k+'.json',v) for k,v in [('capital_decision',decision),('target_mandate',mandate),
            ('identities',dict(securities=securities,source_references=['source']))]}
        self.base=dict(files=files,source_hashes=pins,documents=documents);self.decision=decision
        self.monthly=QuantityV2MonthlySources(storage_root=self.root/'monthly',decision_reader=lambda state:deepcopy(self.base),
            review_reader=self.review,fetch=self.monthly_fetch,clock=lambda:self.current,pullback_policy=POLICY,pullback_cap_store=self.cap)
        self.bridge=QuantityV2MonthlySourceBridge(store=self.store,resolver=self.monthly.resolve,clock=lambda:self.current)
        return state

    def monthly_fetch(self,ticker):
        self.fetches.append(ticker);day=self.current.date().isoformat()
        opened=datetime.fromisoformat(day+'T09:30:00-05:00');closed=datetime.fromisoformat(day+'T16:00:00-05:00')
        return canonical({'chart':{'error':None,'result':[{'meta':dict(symbol=ticker,currency='USD',instrumentType='EQUITY',
            exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=self.market_last,
            regularMarketTime=int(self.current.timestamp())-1,currentTradingPeriod={'regular':{'start':int(opened.timestamp()),'end':int(closed.timestamp())}}),
            'timestamp':[int(opened.timestamp()),int(opened.timestamp())+60,int(opened.timestamp())+120],
            'indicators':{'quote':[dict(open=[9,9.5,None],high=[10,10,None],low=[8,9.5,None],close=[9.5,10,None],volume=[100,100,0])]}}]}})

    def review(self,snapshot):
        ledger=snapshot['state']['ledger'];old=active_proposal(ledger);decision=snapshot['capital_decision'];now=self.current.isoformat()
        units={};held={};evidence='source'
        for sid,receipt in snapshot['current_receipts'].items():
            security=snapshot['identities']['securities'][sid]
            units[sid]=dict(security_id=sid,ticker=security['ticker'],price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
                capital_decision_id=decision['decision_id'],status='NO_UNPROCESSED_ACTIONS',reference_source_hashes=receipt['source_hashes'],
                source_references=[evidence],covered_from_date=decision['decision_date'],covered_through=receipt['captured_at'],reviewed_at=now,
                valuation_source_references=decision['binding']['valuation_quotes'][sid]['source_references'])
            if ledger['shares'].get(sid,0):
                initial=old['target_scope']=='NEW_CASH_CURRENT_QUOTE_ALLOCATION'
                prior=next(row for row in old['rows'] if row['security_id']==sid) if initial else old['causal_inputs']['execution_references'][sid]
                held[sid]=dict(prior_revision=ledger['revision'],security_id=sid,prior_active_proposal_id=old['proposal_id'],
                    prior_price_basis=BASIS if initial else prior['price_basis'],price_basis='CONDITIONAL_PROVIDER_REGULAR_QUOTE_UNITS',
                    security_class=security['security_class'],prior_reference_source_hashes=prior['source_hashes'],
                    reference_source_hashes=receipt['source_hashes'],covered_from=prior['captured_at'],covered_through=receipt['captured_at'],
                    reviewed_at=now,status='NO_UNPROCESSED_ACTIONS',source_references=[evidence])
        values=dict(unit_continuity=units,held_unit_continuity=held,
            account_review=dict(account_id=ledger['account_id'],state_revision=ledger['revision'],pending_rights=[],reviewed_at=now,source_references=[evidence]))
        prefix='review/'+sha256((ledger['revision']+now).encode()).hexdigest()+'/'
        files={prefix+key:canonical(value) for key,value in values.items()}
        return dict(files=files,source_hashes={p:sha256(raw).hexdigest() for p,raw in files.items()},documents={k:prefix+k for k in values})

    def monthly_preview(self,state):
        self.monthly.capture(state)
        return self.bridge.preview(account_id=state['ledger']['account_id'],decision_id=self.decision['decision_id'],expected_revision=state['ledger']['revision'])

    def test_new_month_accept_next_day_restart_and_same_day_cap(self):
        state=self.prepare()
        original_fetch=self.monthly_fetch
        def sell_without_opening_minute(ticker):
            raw=original_fetch(ticker)
            if ticker=='AAA':
                value=json.loads(raw);chart=value['chart']['result'][0]
                chart['timestamp']=chart['timestamp'][1:]
                for key in chart['indicators']['quote'][0]:chart['indicators']['quote'][0][key]=chart['indicators']['quote'][0][key][1:]
                return canonical(value)
            return raw
        self.monthly_fetch=sell_without_opening_minute;self.monthly.fetch=self.monthly_fetch
        view=self.monthly_preview(state);aid=state['ledger']['account_id']
        self.assertEqual(next(row['limit_price'] for row in view['orders'] if row['side']=='SELL'),'10')
        self.assertEqual({r['side'] for r in view['orders']},{'BUY','SELL'})
        self.assertTrue(all(Fraction(r['limit_price'])==9 for r in view['orders'] if r['side']=='BUY'))
        accepted=self.store.accept_monthly_retarget(account_id=aid,proposal_id=view['proposal_id'],operation_id='month',expected_revision=state['ledger']['revision'],
            factory=lambda chain,now:self.bridge.monthly_resolver(chain,view['proposal_id'],now),clock=lambda:self.current)
        self.assertEqual(accepted['ledger']['cash'],state['ledger']['cash'])
        self.assertLessEqual(Fraction(accepted['ledger']['reserved_cash']),Fraction(state['ledger']['cash']))
        sell=next(oid for oid,row in accepted['ledger']['orders'].items() if row['side']=='SELL')
        accepted=self.record(accepted,'FILL',sell,'partial-monthly-sell',quantity=1,price='10',fees='0',executed_at=self.current.isoformat())
        self.assertEqual(Fraction(accepted['ledger']['cash']),Fraction(state['ledger']['cash'])+10)
        self.assertEqual(accepted['ledger']['shares']['A'],1)
        for i,oid in enumerate(accepted['ledger']['orders']):
            accepted=self.record(accepted,'CANCEL',oid,'monthly-cancel'+str(i),cancelled_at=self.current.isoformat())
        self.current+=timedelta(days=1);self.market_last=12
        restarted=QuantityV2PaperStore(self.root/'paper.sqlite3');self.assertEqual(restarted.read(aid),accepted)
        cap=PullbackCapStore(self.database,clock=lambda:self.current.isoformat(),max_history_rows=100,max_history_bytes=1000000)
        source=QuantityV2MonthlyContinuationSources(storage_root=self.root/'monthly-next',monthly_blob_root=self.root/'monthly'/'blobs',
            review_reader=self.review,fetch=self.monthly_fetch,clock=lambda:self.current,pullback_policy=POLICY,pullback_cap_store=cap)
        source.capture(accepted);bridge=QuantityV2ContinuationSourceBridge(store=restarted,resolver=source.resolve,clock=lambda:self.current)
        daily=bridge.preview(account_id=aid,expected_revision=accepted['ledger']['revision'])
        self.assertTrue(all(Fraction(row['limit_price'])==10 for row in daily['orders'] if row['side']=='BUY'))
        self.assertLessEqual(Fraction(daily['reserved_buy_cash']),Fraction(daily['actual_cash']))
        self.assertEqual(next(row['quantity'] for row in daily['orders'] if row['side']=='SELL'),1)
        self.current+=timedelta(seconds=1);self.market_last=14;source.capture(accepted)
        later=bridge.preview(account_id=aid,expected_revision=accepted['ledger']['revision'])
        self.assertTrue(all(Fraction(row['limit_price'])==10 for row in later['orders'] if row['side']=='BUY'))
        with patch.object(cap,'candidate',side_effect=AssertionError('resolve wrote cap')):
            source.resolve(aid,self.decision['decision_id'])

    def test_zero_target_exit_still_requires_fresh_quote(self):
        state=self.prepare();original_fetch=self.monthly_fetch
        def stale_sell(ticker):
            value=json.loads(original_fetch(ticker))
            if ticker=='AAA':value['chart']['result'][0]['meta']['regularMarketTime']-=1000
            return canonical(value)
        self.monthly.fetch=stale_sell
        with self.assertRaises(ValueError):self.monthly_preview(state)

    def test_missing_positive_target_proof_still_rejected(self):
        state=self.prepare();self.monthly_preview(state)
        package=self.monthly.resolve(state['ledger']['account_id'],self.decision['decision_id'])
        package=deepcopy(package);package['documents']['pullback_proofs'].pop('B')
        bridge=QuantityV2MonthlySourceBridge(store=self.store,resolver=lambda *args:package,clock=lambda:self.current)
        with self.assertRaisesRegex(ValueError,'INVALID_PULLBACK_POLICY'):
            bridge.preview(account_id=state['ledger']['account_id'],decision_id=self.decision['decision_id'],expected_revision=state['ledger']['revision'])

    def test_policy_configuration_tampered_proof_and_limit_rejected(self):
        state=self.prepare();self.monthly.pullback_policy=None
        with self.assertRaisesRegex(ValueError,'PULLBACK_MONTHLY_POLICY_REQUIRED'):self.monthly.capture(state)
        self.monthly.pullback_policy=deepcopy(POLICY);view=self.monthly_preview(state)
        package=self.monthly.resolve(state['ledger']['account_id'],self.decision['decision_id'])
        path=package['documents']['pullback_proofs']['B'];proof=json.loads(package['files'][path]);proof['result']['candidate']['limit_price']='10'
        package['files'][path]=canonical(proof);package['source_hashes'][path]=sha256(package['files'][path]).hexdigest()
        bad=QuantityV2MonthlySourceBridge(store=self.store,resolver=lambda *args:deepcopy(package),clock=lambda:self.current)
        with self.assertRaisesRegex(ValueError,'PROOF_DIGEST_MISMATCH'):
            bad.preview(account_id=state['ledger']['account_id'],decision_id=self.decision['decision_id'],expected_revision=state['ledger']['revision'])
        self.assertEqual(self.store.read(state['ledger']['account_id']),state)
        from data.current_quantity_v2_monthly_retarget import build_monthly_retarget
        args,_=self.bridge._evidence(state,self.decision['decision_id'],self.current)
        args['execution_references']['B']['pullback']['limit_price']='10'
        with self.assertRaisesRegex(ValueError,'MONTHLY_PULLBACK_LIMIT_INVALID'):
            build_monthly_retarget(state,proposal_inputs=args,now=self.current)

    def test_constructor_rejects_invalid_policy_without_callbacks(self):
        def forbidden(*args):raise AssertionError('constructor IO')
        for change in ({'minimum_discount':'0'},{'rebound_fraction':'1'},
                       {'maximum_age_seconds':True},{'schema':'other'},{'status':'approved'}):
            with self.assertRaises(ValueError):
                QuantityV2MonthlySources(storage_root=self.root/'unused',decision_reader=forbidden,
                    review_reader=forbidden,fetch=forbidden,clock=forbidden,
                    pullback_policy={**POLICY,**change},pullback_cap_store=self.cap)
        self.assertFalse((self.root/'unused').exists())

    def test_legacy_account_ignores_enabled_server_policy(self):
        from test_current_quantity_v2_monthly_sources import fixture
        old,paper,state,did,clock,calls,_=fixture(self.root/'legacy')
        configured=QuantityV2MonthlySources(storage_root=self.root/'legacy-configured',
            decision_reader=old.decision_reader,review_reader=old.review_reader,fetch=old.fetch,
            clock=old.clock,pullback_policy=POLICY,pullback_cap_store=self.cap)
        with patch.object(self.cap,'candidate',side_effect=AssertionError('legacy created cap')):
            configured.capture(state)
            package=configured.resolve(state['ledger']['account_id'],did)
        self.assertNotIn('pullback_policy',package['documents'])


if __name__=='__main__':unittest.main()
