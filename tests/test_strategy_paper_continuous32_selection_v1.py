from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.strategy_account_ledger import canonical
from data.current_quantity_v2_monthly_training import compile_saved_training
from data.strategy_paper_continuous32_selection_v1 import (
    CODE_PATHS, PROFILE_ID, VERSION, SCOPE, select_paper_target, verify_paper_target)
from backtest.continuous_guided_account_decision import enhanced_search
from test_current_quantity_v2_monthly_training import fixture
from test_current_strategy_paper_slice_v1 import book, proposal, accept, settle

ROOT=Path(__file__).resolve().parents[1]


def arguments(folder, state=None, two_candidates=False):
    state=state or book()
    _,_,package,days=fixture(folder)
    def put(path,value):
        raw=canonical(value);package['files'][path]=raw;package['source_hashes'][path]=sha256(raw).hexdigest()
    if two_candidates:
        raw=json.loads(package['files']['B.daily'])
        raw['chart']['result'][0]['meta']['symbol']='DDD'
        put('D.daily',raw)
        manifest=json.loads(package['files']['manifest.json'])
        row=deepcopy(manifest['candidates'][0]);row.update(ticker='DDD',security_id='D',issuer_id='ID',training_source='D.daily')
        manifest['candidates'].append(row);manifest['members'].append('DDD');manifest['admission']['members'].append('DDD')
        manifest['source_hashes']['D.daily']=package['source_hashes']['D.daily']
        put('manifest.json',manifest)
    historical=compile_saved_training(package,'manifest.json')['input']['search_arguments']
    now='2026-11-02T15:00:00+00:00'
    needed=set(historical['prices'])|{s for s,q in state['shares'].items() if q}
    needed|={o['security_id'] for o in state['orders'].values() if o['closed'] is None}
    marks={sid:dict(security_id=sid,currency='USD',price='200' if sid=='A' else '1000',
        price_basis='CURRENT_UNIT',observed_at=now,source_references=['calendar-source']) for sid in needed}
    put('marks.paper.json',marks)
    review=dict(schema='STRATEGY_TARGET_UNIT_REVIEW_V1',status='CONDITIONAL_CURRENT_UNITS_REVIEWED',
        account_revision=state['revision'],training_manifest_sha256=package['source_hashes']['manifest.json'],
        historical_search_arguments_sha256=sha256(canonical(historical)).hexdigest(),
        marks_sha256=package['source_hashes']['marks.paper.json'],training_cutoff_date='2026-10-30',
        training_closed_at='2026-10-30T20:00:00+00:00',reviewed_at=now,source_references=['calendar-source'],
        unresolved=[],pending_rights=[],securities={})
    for sid,mark in marks.items():
        review['securities'][sid]=dict(security_id=sid,current_price_basis='CURRENT_UNIT',
            current_mark_sha256=sha256(canonical(mark)).hexdigest(),historical_price_basis=historical['price_basis'],
            training_manifest_sha256=package['source_hashes']['manifest.json'],
            historical_scenarios_usable_in_current_units=True,held_quantities_in_current_units=True,
            covered_through=now,source_references=['calendar-source'])
    put('review.paper.json',review)
    for path in CODE_PATHS:
        raw=(ROOT/path).read_bytes();package['files'][path]=raw;package['source_hashes'][path]=sha256(raw).hexdigest()
    calendar=canonical(dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',sessions=[
        dict(date=day,open=day+'T13:30:00+00:00',close=day+'T20:00:00+00:00') for day in days]+[
        dict(date='2026-11-02',open='2026-11-02T14:30:00+00:00',close='2026-11-02T21:00:00+00:00')]))
    app=dict(schema='CURRENT_STRATEGY_PAPER_SELECTION_APPLICATION_V1',scope=SCOPE,
        approved_for_selection=True,automatic_acceptance_allowed=False,account_id=state['application']['account_id'],
        ledger_schema=state['schema'],account_genesis_sha256=sha256(canonical(state['application'])).hexdigest(),
        approved_at='2026-10-30T20:01:00+00:00',valid_from='2026-11-02T14:30:00+00:00',
        valid_until='2026-11-02T21:00:00+00:00',selector_profile=PROFILE_ID,selection_method=VERSION,
        continuous_iterations=32,code_sha256={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in CODE_PATHS},
        calendar_sha256=sha256(calendar).hexdigest(),fee_bps=historical['fee_bps'],
        admitted_source_hashes_sha256=sha256(canonical(package['source_hashes'])).hexdigest())
    raw=canonical(app)
    return dict(book=state,application_bytes=raw,trusted_application_sha256=sha256(raw).hexdigest(),
        calendar_bytes=calendar,source_package=package,manifest_path='manifest.json',
        marks_path='marks.paper.json',unit_review_path='review.paper.json',now=now,maximum_mark_age_seconds=120)


class PaperSelectionTests(unittest.TestCase):
    def test_real_compiler_and_selector_20k_zero_holdings_no_writes(self):
        with TemporaryDirectory() as folder:
            args=arguments(folder);before=deepcopy(args)
            with patch('data.strategy_paper_continuous32_selection_v1.enhanced_search',wraps=enhanced_search) as search:
                result=select_paper_target(**args)
            self.assertEqual(search.call_count,1)
            self.assertEqual(result['status'],'TARGET_READY')
            binding=result['payload']['input_binding']
            self.assertEqual(binding['strategy_equity'],'20000')
            self.assertEqual(binding['strategy_shares'],{})
            self.assertEqual(binding['continuous_iterations'],32)
            self.assertEqual(result['payload']['target_quantities'],{'B':20})
            self.assertEqual(args,before)
            self.assertFalse(result['target_published'])
            saved=Path(folder)/'paper-target.json';saved.write_bytes(canonical(result))
            with patch('data.strategy_paper_continuous32_selection_v1.enhanced_search',side_effect=AssertionError('no new search')):
                verified=verify_paper_target(json.loads(saved.read_bytes()),**args)
            self.assertEqual(verified['target_quantities'],{'B':20})
            self.assertEqual(verified['target_month'],'2026-11')

    def test_existing_paper_holdings_and_cash_jointly_value_equity(self):
        state=book();state=settle(accept(state,proposal(state,{'A':14})))
        with TemporaryDirectory() as folder:
            args=arguments(folder,state)
            result=select_paper_target(**args)
            binding=result['payload']['input_binding']
            self.assertEqual(binding['total_uninvested_cash'],'18600')
            self.assertEqual(binding['holding_market_values'],{'A':'2800'})
            self.assertEqual(binding['strategy_equity'],'21400')
            self.assertEqual(result['payload']['target_quantities'],{'B':21})
            self.assertNotIn('A',binding['search_arguments']['prices'])

    def test_pending_reservation_does_not_reduce_equity_or_create_shares(self):
        state=book();state=accept(state,proposal(state,{'A':14}))
        with TemporaryDirectory() as folder:
            result=select_paper_target(**arguments(folder,state))
            binding=result['payload']['input_binding']
            self.assertEqual(binding['strategy_equity'],'20000')
            self.assertEqual(binding['holding_market_values'],{})
            self.assertEqual(binding['execution_context']['reserved_cash'],'1400')
            self.assertEqual(binding['execution_context']['available_cash'],'18600')
            self.assertEqual(result['payload']['target_quantities'],{'B':20})

    def test_variable_support_search_is_not_fixed_one_stock(self):
        with TemporaryDirectory() as folder:
            result=select_paper_target(**arguments(folder,two_candidates=True))
            search=result['payload']['search_result']
            self.assertEqual(set(result['payload']['input_binding']['search_arguments']['prices']),{'B','D'})
            self.assertTrue(search['continuous_comparison'])
            self.assertTrue(any(str(k)=='2' for k in search['best_by_k']))

    def test_scope_calendar_and_account_admission_reject_before_search(self):
        for mode in ('web','calendar','account','sources','code','expiry'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args=arguments(folder);app=json.loads(args['application_bytes'])
                if mode=='web':app['scope']='WEB_MANUAL_ADVICE_RULE_ONLY'
                elif mode=='calendar':
                    value=json.loads(args['calendar_bytes']);value['exchange']='NYSE';args['calendar_bytes']=canonical(value)
                    app['calendar_sha256']=sha256(args['calendar_bytes']).hexdigest()
                elif mode=='account':app['account_id']='real-account'
                elif mode=='sources':app['admitted_source_hashes_sha256']='0'*64
                elif mode=='code':app['code_sha256'][next(iter(CODE_PATHS))]='0'*64
                else:args['now']='2026-11-03T15:00:00+00:00'
                args['application_bytes']=canonical(app);args['trusted_application_sha256']=sha256(args['application_bytes']).hexdigest()
                with patch('data.strategy_paper_continuous32_selection_v1.enhanced_search') as search:
                    with self.assertRaises(ValueError):select_paper_target(**args)
                    search.assert_not_called()

    def test_tampered_raw_bytes_fail_even_when_outer_application_rebound(self):
        with TemporaryDirectory() as folder:
            args=arguments(folder)
            args['source_package']['files']['B.daily']+=b' '
            with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):
                select_paper_target(**args)

    def test_changed_source_code_with_rehashed_outer_review_rejected(self):
        with TemporaryDirectory() as folder:
            args=arguments(folder);path='data/strategy_continuous32_target_decision.py'
            package=args['source_package'];package['files'][path]+=b'\n'
            package['source_hashes'][path]=sha256(package['files'][path]).hexdigest()
            app=json.loads(args['application_bytes'])
            app['admitted_source_hashes_sha256']=sha256(canonical(package['source_hashes'])).hexdigest()
            args['application_bytes']=canonical(app);args['trusted_application_sha256']=sha256(args['application_bytes']).hexdigest()
            with self.assertRaisesRegex(ValueError,'SOURCE_CODE_BINDING'):
                select_paper_target(**args)

    def test_saved_target_tamper_and_different_paper_revision_rejected(self):
        with TemporaryDirectory() as folder:
            args=arguments(folder);result=select_paper_target(**args)
            for mode in ('quantity','month','application'):
                bad=deepcopy(result)
                if mode=='quantity':bad['payload']['target_quantities']={'B':999}
                elif mode=='month':bad['payload']['target_month']='2026-12'
                else:bad['automatic_acceptance_allowed']=True
                bad['decision_id']=sha256(canonical(bad['payload'])).hexdigest()
                with self.assertRaises(ValueError):verify_paper_target(bad,**args)
            args['book']=settle(accept(args['book'],proposal(args['book'])))
            with self.assertRaisesRegex(ValueError,'FULL_CANDIDATE_HELD_MARKS_REQUIRED'):
                verify_paper_target(result,**args)

    def test_same_economics_match_current_tool_inputs_and_actual_selector(self):
        # The real ledger is solely the existing tool's reference-test input.
        # The paper implementation never imports or receives these real events.
        from core.strategy_account_ledger import create_account, apply_event
        from data.strategy_account_target_inputs import build_target_inputs
        from data.strategy_continuous32_target_decision import decide_target
        for mode in ('empty','held','pending'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                paper=book()
                if mode!='empty':
                    paper=accept(paper,proposal(paper,{'A':14}))
                    if mode=='held':paper=settle(paper)
                args=arguments(folder,paper,two_candidates=True)
                paper_result=select_paper_target(**args)
                reference=create_account('reference-only-real-test')
                def add(event):
                    nonlocal reference
                    reference,_=apply_event(reference,event,expected_revision=reference['revision'])
                if mode=='held':
                    add(dict(event_id='reference-fill',kind='DIRECT_FILL',security_id='A',side='BUY',
                        quantity=14,price='100',fees='0',executed_at='2026-02-02T10:01:59-05:00'))
                if mode=='pending':
                    add(dict(event_id='reference-order',kind='ORDER_OPEN',order_id='reference-pending',
                        security_id='A',side='BUY',quantity=14,limit_price='100',fee_per_share='0'))
                add(dict(event_id='reference-cash',kind='CASH_CONFIRM',amount=paper['cash'],cash_basis='TOTAL_UNINVESTED'))
                package=deepcopy(args['source_package'])
                review=json.loads(package['files']['review.paper.json']);review['account_revision']=reference['revision']
                package['files']['review.paper.json']=canonical(review)
                package['source_hashes']['review.paper.json']=sha256(package['files']['review.paper.json']).hexdigest()
                original=dict(state=reference,source_package=package,manifest_path=args['manifest_path'],
                    marks_path=args['marks_path'],unit_review_path=args['unit_review_path'],
                    now=args['now'],maximum_mark_age_seconds=args['maximum_mark_age_seconds'])
                current_input=build_target_inputs(**original)['binding']
                current_target=decide_target(**original)
                paper_input=paper_result['payload']['input_binding']
                for field in ('search_arguments','historical_search_arguments','strategy_equity',
                              'holding_market_values','total_uninvested_cash','strategy_shares'):
                    self.assertEqual(paper_input[field],current_input[field],field)
                for field in ('available_cash','reserved_cash','reserved_shares','sell_proceeds_available'):
                    self.assertEqual(paper_input['execution_context'][field],current_input['execution_context'][field],field)
                self.assertEqual(paper_result['payload']['search_result'],current_target['payload']['search_result'])
                self.assertEqual(paper_result['payload']['target_quantities'],current_target['payload']['target_quantities'])

    def test_saved_target_fixed_evidence_flags_cannot_be_promoted(self):
        with TemporaryDirectory() as folder:
            args=arguments(folder);result=select_paper_target(**args)
            for field,value in [('source_authenticated',True),('full_pit_verified',True),
                                ('source_bytes_verified',False),('core_calls',999),('core_calls',True)]:
                with self.subTest(field=field,value=value):
                    bad=deepcopy(result);bad[field]=value
                    saved=Path(folder)/'mutated-result.json';saved.write_bytes(canonical(bad))
                    with self.assertRaisesRegex(ValueError,'PAPER_TARGET_EVIDENCE_FLAGS_CHANGED'):
                        verify_paper_target(json.loads(saved.read_bytes()),**args)


if __name__=='__main__':unittest.main()
