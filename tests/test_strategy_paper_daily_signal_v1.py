from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical, create_account, apply_event
from data.strategy_paper_daily_signal_v1 import verify_paper_daily_signal, CODE_PATHS, SCOPE
from data.strategy_daily_signal_common_v1 import verify_real_daily_signal_bundle
from data.strategy_daily_signal_verifier import verify_daily_signal_bundle, CODE_PATHS as RULE_PINS, POLICY
from data.strategy_paper_continuous32_selection_v1 import select_paper_target
from test_strategy_paper_continuous32_selection_v1 import arguments
from test_current_strategy_paper_slice_v1 import book, proposal, accept, settle, bar
from backtest.current_strategy_paper_slice_v1 import transact

ROOT=Path(__file__).resolve().parents[1]


def setup(folder, held=False, on=False):
    state=book()
    if held:state=settle(accept(state,proposal(state,{'A':14})))
    selection=arguments(folder,state)
    calendar=json.loads(selection['calendar_bytes'])
    calendar['sessions'].append(dict(date='2026-11-03',open='2026-11-03T14:30:00+00:00',close='2026-11-03T21:00:00+00:00'))
    raw_calendar=canonical(calendar);selection['calendar_bytes']=raw_calendar
    selection_app=json.loads(selection['application_bytes']);selection_app['calendar_sha256']=sha256(raw_calendar).hexdigest()
    selection['application_bytes']=canonical(selection_app);selection['trusted_application_sha256']=sha256(selection['application_bytes']).hexdigest()
    target=select_paper_target(**selection)
    quantities=target['payload']['target_quantities'];sessions=calendar['sessions'][:-1]
    dates=[s['date'] for s in sessions];cutoff=dates[-1]
    histories={sid:dict(units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',unit_asof=cutoff,
        currency='USD',basis_id='unit:'+sid,review_reference='fixture-reviewed-unit'),source_reference='fixture-raw',
        closes=[dict(date=s['date'],completed_at=s['close'],close='101' if on and i==19 else '100')
                for i,s in enumerate(sessions[-20:])]) for sid in quantities}
    inputs=dict(base_target=dict(quantities=quantities,price_units={s:'unit:'+s for s in quantities},
        origin_reference=target['decision_id'],monthly_decision_date=cutoff), signal_date=cutoff,
        observed_at=sessions[-1]['close'],session_dates=dates,
        session_close_times=dict(review_reference='fixture-calendar',closes={s['date']:s['close'] for s in sessions}),
        histories=histories)
    release=dict(schema='PAPER_DAILY_POLICY_RELEASE_V1',scope='PAPER_DAILY_SIGNAL_RULE_ONLY',approved=True,
        policy_id=POLICY,approved_at='2026-10-30T20:01:00+00:00',calendar_sha256=sha256(raw_calendar).hexdigest(),
        code_sha256={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in RULE_PINS})
    release_bytes=canonical(release);release_sha=sha256(release_bytes).hexdigest()
    app=dict(schema='PAPER_DAILY_SIGNAL_APPLICATION_V1',scope=SCOPE,authorized=True,automatic_acceptance_allowed=False,
        approved_at='2026-10-30T20:01:00+00:00',valid_from='2026-11-02T14:30:00+00:00',valid_until='2026-11-04T23:00:00+00:00',
        code_sha256={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in CODE_PATHS},account_id=state['application']['account_id'],
        account_genesis_sha256=sha256(canonical(state['application'])).hexdigest(),target_id=target['decision_id'],
        selection_application_sha256=selection['trusted_application_sha256'],calendar_sha256=sha256(raw_calendar).hexdigest(),
        start_session='2026-11-03',release_sha256=release_sha)
    files={'normalized.json':canonical(inputs),'raw-history.json':canonical({'fixture':'not vendor attestation'})}
    receipt=dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',release_sha256=release_sha,
        account_id=state['application']['account_id'],account_revision=state['revision'],target_id=target['decision_id'],
        normalized_inputs_path='normalized.json',normalization_reviewed=True,unresolved_units=[],pending_rights=[],
        raw_source_paths=['raw-history.json'],available_at=sessions[-1]['close'],valid_from=calendar['sessions'][-1]['open'],
        valid_until=calendar['sessions'][-1]['close'],market_asof=sessions[-1]['close'],source_received_at=sessions[-1]['close'],
        research_observed_at_semantics='MARKET_ASOF_NOT_RECEIPT',execution_session=calendar['sessions'][-1],
        source_sha256={p:sha256(raw).hexdigest() for p,raw in files.items()})
    args=dict(book=state,selection_result=target,selection_arguments=selection,application_bytes=canonical(app),
        trusted_application_sha256=sha256(canonical(app)).hexdigest(),now='2026-11-03T15:00:00+00:00',
        release_bytes=release_bytes,trusted_release_sha256=release_sha,calendar_bytes=raw_calendar,
        receipt_bytes=canonical(receipt),trusted_receipt_sha256=sha256(canonical(receipt)).hexdigest(),files=files)
    return args


def reference(paper):
    state=create_account('reference-real-daily')
    for sid,q in paper['book']['shares'].items():
        state,_=apply_event(state,dict(event_id='reference-'+sid,kind='DIRECT_FILL',security_id=sid,
            side='BUY',quantity=q,price='100',fees='0',executed_at='2026-02-02T10:01:59-05:00'),expected_revision=state['revision'])
    release=json.loads(paper['release_bytes']);release['schema']='SERVER_DAILY_POLICY_RELEASE_V1';release['scope']='WEB_MANUAL_ADVICE_RULE_ONLY'
    release_bytes=canonical(release);release_sha=sha256(release_bytes).hexdigest()
    receipt=json.loads(paper['receipt_bytes'])
    receipt.update(account_id=state['account_id'],account_revision=state['revision'],release_sha256=release_sha)
    target=dict(target_id=paper['selection_result']['decision_id'],payload=dict(account_id=state['account_id'],
        target_month='2026-11',target_quantities=paper['selection_result']['payload']['target_quantities']))
    return dict(state=state,target=target,now=paper['now'],release_bytes=release_bytes,trusted_release_sha256=release_sha,
        receipt_bytes=canonical(receipt),trusted_receipt_sha256=sha256(canonical(receipt)).hexdigest(),
        files=deepcopy(paper['files']),calendar_bytes=paper['calendar_bytes'])


def reseal_receipt(args, receipt):
    receipt['source_sha256']={p:sha256(raw).hexdigest() for p,raw in args['files'].items()}
    args['receipt_bytes']=canonical(receipt);args['trusted_receipt_sha256']=sha256(args['receipt_bytes']).hexdigest()


class PaperDailySignalTests(unittest.TestCase):
    def test_same_sources_real_original_shared_and_paper_daily_targets(self):
        for held in (False,True):
            for on in (False,True):
                with self.subTest(held=held,on=on),TemporaryDirectory() as folder:
                    args=setup(folder,held,on);before=deepcopy(args);real=reference(args)
                    old=verify_daily_signal_bundle(**real);shared=verify_real_daily_signal_bundle(**real)
                    paper=verify_paper_daily_signal(**args)
                    self.assertEqual(old,shared)
                    self.assertEqual(paper['status'],'DAILY_SIGNAL_READY')
                    for field in ('effective_target_quantities','valid_from','valid_until','available_at','observed_at'):
                        self.assertEqual(paper['signal'][field],old['signal'][field],field)
                    monthly=args['selection_result']['payload']['target_quantities']['B']
                    self.assertEqual(paper['signal']['effective_target_quantities']['B'],monthly if on else monthly//2)
                    if held:self.assertEqual(paper['signal']['effective_target_quantities']['A'],0)
                    self.assertFalse(paper['automatic_acceptance_allowed'])
                    self.assertEqual(args,before)

    def test_same_source_rejections_resealed_receipt(self):
        for mode in ('future','unit','quantity','missing-session','close','pending-rights'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args=setup(folder);receipt=json.loads(args['receipt_bytes']);inputs=json.loads(args['files']['normalized.json'])
                if mode=='future':inputs['histories']['B']['closes'][-1]['completed_at']='2099-01-01T16:00:00-05:00'
                elif mode=='unit':inputs['histories']['B']['units']['basis_id']='wrong'
                elif mode=='quantity':inputs['base_target']['quantities']['B']+=1
                elif mode=='missing-session':inputs['session_dates'].pop(-2)
                elif mode=='close':inputs['session_close_times']['closes'][inputs['signal_date']]='2026-11-02T20:00:00+00:00'
                else:receipt['pending_rights']=['unresolved']
                args['files']['normalized.json']=canonical(inputs);reseal_receipt(args,receipt)
                real=reference(args)
                errors=[]
                for fn,values in [(verify_daily_signal_bundle,real),(verify_real_daily_signal_bundle,real),(verify_paper_daily_signal,args)]:
                    with self.assertRaises(ValueError) as caught:fn(**values)
                    errors.append(str(caught.exception))
                self.assertEqual(errors[0],errors[1]);self.assertEqual(errors[0],errors[2])

    def test_stale_signal_wait_and_missing_receipt_wait(self):
        with TemporaryDirectory() as folder:
            args=setup(folder);args['now']='2026-11-03T21:00:00+00:00'
            self.assertEqual(verify_paper_daily_signal(**args)['status'],'WAIT_FRESH_SIGNAL')
            self.assertEqual(verify_real_daily_signal_bundle(**reference(args))['status'],'WAIT_FRESH_SIGNAL')
            args['receipt_bytes']=None;args['trusted_receipt_sha256']=None
            self.assertEqual(verify_paper_daily_signal(**args)['status'],'WAIT_SIGNAL')

    def test_paper_authority_account_target_and_source_guards(self):
        for mode in ('web-scope','release-scope','account','target','start','raw'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args=setup(folder);app=json.loads(args['application_bytes'])
                if mode=='web-scope':app['scope']='WEB_MANUAL_ADVICE_RULE_ONLY'
                elif mode=='release-scope':
                    release=json.loads(args['release_bytes']);release['scope']='WEB_MANUAL_ADVICE_RULE_ONLY'
                    args['release_bytes']=canonical(release);args['trusted_release_sha256']=sha256(args['release_bytes']).hexdigest()
                    app['release_sha256']=args['trusted_release_sha256']
                    receipt=json.loads(args['receipt_bytes']);receipt['release_sha256']=app['release_sha256'];reseal_receipt(args,receipt)
                elif mode=='account':app['account_id']='real-account'
                elif mode=='target':app['target_id']='wrong'
                elif mode=='start':app['start_session']='2026-12-01'
                else:args['files']['raw-history.json']+=b' '
                args['application_bytes']=canonical(app);args['trusted_application_sha256']=sha256(args['application_bytes']).hexdigest()
                with self.assertRaises(ValueError):verify_paper_daily_signal(**args)

    def test_real_replay_and_paper_replay_are_static_and_not_interchangeable(self):
        with TemporaryDirectory() as folder:
            args=setup(folder)
            damaged=deepcopy(args);damaged['book']['cash']='999999'
            with self.assertRaisesRegex(ValueError,'PAPER_BOOK_REPLAY_MISMATCH'):
                verify_paper_daily_signal(**damaged)
            real=reference(args);real['state']['cash']='999999'
            with self.assertRaisesRegex(ValueError,'ACCOUNT_REPLAY_MISMATCH'):
                verify_real_daily_signal_bundle(**real)
            args['book']=real['state']
            with self.assertRaises((ValueError,KeyError)):
                verify_paper_daily_signal(**args)

    def test_current_book_availability_and_receipt_after_state_are_required(self):
        for evaluated,expected in [('2026-11-03T15:00:30+00:00','PAPER_DAILY_STATE_NOT_AVAILABLE'),
                                   ('2026-11-03T14:59:00+00:00','PAPER_DAILY_RECEIPT_BEFORE_STATE')]:
            with self.subTest(evaluated=evaluated),TemporaryDirectory() as folder:
                args=setup(folder)
                changed=accept(args['book'],proposal(args['book']))
                oid=next(iter(changed['orders']))
                changed=transact(changed,dict(kind='SETTLE',operation_id='later',expected_revision=changed['revision'],
                    minutes={oid:[bar()]},observed_through='2026-02-02T10:02:00-05:00',evaluated_at=evaluated))
                args['book']=changed
                with self.assertRaisesRegex(ValueError,expected):verify_paper_daily_signal(**args)

    def test_selection_history_cannot_roll_back_or_fork_after_receipt_rebinding(self):
        for mode in ('rollback', 'different-fill', 'different-operation'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                args=setup(folder,held=True)
                changed=book()
                if mode!='rollback':
                    changed=settle(accept(changed,proposal(changed,{'A':13 if mode=='different-fill' else 14}),
                        identifier='fork' if mode=='different-operation' else 'accept'))
                args['book']=changed
                receipt=json.loads(args['receipt_bytes']);receipt['account_revision']=changed['revision']
                reseal_receipt(args,receipt)
                with self.assertRaisesRegex(ValueError,'PAPER_DAILY_SELECTION_NOT_ANCESTOR'):
                    verify_paper_daily_signal(**args)

    def test_valid_post_selection_fill_preserves_monthly_target(self):
        with TemporaryDirectory() as folder:
            args=setup(folder,held=True)
            original_target=deepcopy(args['selection_result'])
            original_history=deepcopy(args['book']['operations'])
            changed=accept(args['book'],proposal(args['book'],{'A':15},day='2026-11-02'),identifier='post-selection')
            changed=settle(changed,identifier='post-selection-fill',day='2026-11-02')
            self.assertEqual(changed['shares']['A'],15)
            self.assertEqual(changed['operations'][:len(original_history)],original_history)
            args['book']=changed
            receipt=json.loads(args['receipt_bytes']);receipt['account_revision']=changed['revision']
            reseal_receipt(args,receipt)
            result=verify_paper_daily_signal(**args)
            self.assertEqual(result['status'],'DAILY_SIGNAL_READY')
            self.assertEqual(result['paper_book_revision'],changed['revision'])
            self.assertEqual(result['signal']['effective_target_quantities'],{'A':0,'B':10})
            self.assertEqual(args['selection_result'],original_target)


if __name__=='__main__':unittest.main()
