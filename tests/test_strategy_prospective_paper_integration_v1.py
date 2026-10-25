from copy import deepcopy
from datetime import datetime,time,timezone
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v1 import SCOPE,plan_future_start
from backtest.current_strategy_prospective_paper_book_v1 import create_book,transact,replay,CODE_PATHS as BOOK_PINS,SETTLEMENT_SCHEMA
from data.strategy_prospective_paper_selection_v1 import select_prospective_target,verify_prospective_target
from data.strategy_prospective_paper_daily_v1 import verify_prospective_daily
from data.strategy_prospective_paper_decision_v1 import produce_prospective_decision,ProspectiveTemporaryCaps,CODE_PATHS
import test_strategy_paper_application_descriptor_v1 as descriptor_fixture
from test_strategy_paper_daily_signal_v1 import setup
from test_strategy_paper_execution_preview_v1 import capture

ROOT=Path(__file__).resolve().parents[1]


def fixture(folder,monthly_price='1000',extra_code_paths=(),extra_sources=None,extra_sessions=()):
    old=setup(folder)
    calendar=json.loads(old['calendar_bytes'])
    calendar['sessions'].extend(deepcopy(extra_sessions))
    for row in calendar['sessions']:
        day=datetime.fromisoformat(row['date']).date()
        for field,hour,minute in [('open',9,30),('close',16,0)]:
            row[field]=datetime.combine(day,time(hour,minute),ZoneInfo('America/New_York')).astimezone(timezone.utc).isoformat()
    cal=canonical(calendar);calhash=sha256(cal).hexdigest()
    release=json.loads(old['release_bytes']);release['calendar_sha256']=calhash
    f=descriptor_fixture.DescriptorTests();f.setUp();app=deepcopy(f.app)
    app['calendar_sha256']=calhash
    app['plan']=plan_future_start(calendar_bytes=cal,calendar_sha256=calhash,now='2026-11-03T14:58:00+00:00',terminal_date='2026-11-03')
    app['policy']['fee_bps']='0'
    codes={p:(ROOT/p).read_bytes() for p in CODE_PATHS|BOOK_PINS|set(extra_code_paths)}
    sources={'policy/daily.json':canonical(release)}
    sources.update(extra_sources or {})
    app['code_sha256']={p:sha256(raw).hexdigest() for p,raw in codes.items()}
    app['source_sha256']={p:sha256(raw).hexdigest() for p,raw in sources.items()}
    raw=canonical(app);desc_hash=sha256(raw).hexdigest()
    approval=canonical(dict(schema='PAPER_APPLICATION_REVIEW_V1',scope=SCOPE,descriptor_sha256=desc_hash,approved=True,
        reviewed_at='2026-11-03T14:58:30+00:00',review_role='IMPLEMENTATION_REVIEW_OF_USER_AUTHORIZED_PAPER_SCOPE',
        authorization_basis='TEMPORARY SYNTHETIC INTEGRATION TEST ONLY'))
    registration=canonical(dict(schema='PROSPECTIVE_PAPER_REGISTRATION_V1',scope=SCOPE,descriptor_sha256=desc_hash,
        account_id=app['account_id'],simulation_id=app['simulation_id'],registered_at='2026-11-03T14:59:00+00:00',
        first_session=app['plan']['first_session'],terminal_session=app['plan']['terminal_session'],integration_review_sha256='a'*64))
    authority=dict(descriptor_arguments=dict(descriptor_bytes=raw,trusted_descriptor_sha256=desc_hash,
        approval_bytes=approval,trusted_approval_sha256=sha256(approval).hexdigest(),calendar_bytes=cal,code_bytes=codes,source_bytes=sources),
        registration_bytes=registration,trusted_registration_sha256=sha256(registration).hexdigest(),trusted_integration_review_sha256='a'*64)
    book=create_book(authority=authority,clock=lambda:datetime.fromisoformat('2026-11-03T15:00:00+00:00'));admitted={}
    package=deepcopy(old['selection_arguments']['source_package']);selection_at='2026-11-03T15:00:01+00:00'
    def put(path,value):
        raw=canonical(value);package['files'][path]=raw;package['source_hashes'][path]=sha256(raw).hexdigest()
    marks=json.loads(package['files']['marks.paper.json'])
    for mark in marks.values():mark.update(observed_at=selection_at,price=monthly_price)
    put('marks.paper.json',marks)
    units=json.loads(package['files']['review.paper.json']);units.update(account_revision=book['revision'],reviewed_at=selection_at,
        marks_sha256=package['source_hashes']['marks.paper.json'])
    for sid,unit in units['securities'].items():
        unit.update(current_mark_sha256=sha256(canonical(marks[sid])).hexdigest(),covered_through=selection_at)
    put('review.paper.json',units)
    for p,raw in codes.items():package['files'][p]=raw;package['source_hashes'][p]=sha256(raw).hexdigest()
    review=canonical(dict(schema='PROSPECTIVE_PAPER_SOURCE_ADMISSION_V1',scope=SCOPE,descriptor_sha256=desc_hash,
        account_id=book['account_id'],account_revision=book['revision'],source_sha256=package['source_hashes'],
        available_at=selection_at,source_authenticated=False,coverage_complete=False))
    selection_args=dict(book=book,authority=authority,admitted_decisions=admitted,source_review_bytes=review,
        trusted_source_review_sha256=sha256(review).hexdigest(),source_package=package,manifest_path='manifest.json',
        marks_path='marks.paper.json',unit_review_path='review.paper.json',now=selection_at,maximum_mark_age_seconds=120)
    selected=select_prospective_target(clock=lambda:selection_at,**selection_args)
    inputs=json.loads(old['files']['normalized.json']);inputs['base_target']['origin_reference']=selected['decision_id']
    inputs['base_target']['quantities']=selected['payload']['target_quantities']
    rows={r['date']:r for r in calendar['sessions']}
    inputs['session_close_times']['closes']={day:rows[day]['close'] for day in inputs['session_dates']}
    for history in inputs['histories'].values():
        for row in history['closes']:row['completed_at']=rows[row['date']]['close']
    files=deepcopy(old['files']);files['normalized.json']=canonical(inputs)
    receipt=json.loads(old['receipt_bytes']);receipt.update(account_id=book['account_id'],account_revision=book['revision'],
        target_id=selected['decision_id'],release_sha256=app['source_sha256']['policy/daily.json'],available_at='2026-11-03T15:00:02+00:00',
        valid_from='2026-11-03T15:00:02+00:00',source_sha256={p:sha256(raw).hexdigest() for p,raw in files.items()})
    daily=dict(book=book,authority=authority,admitted_decisions=admitted,selection_result=selected,selection_arguments=selection_args,
        now='2026-11-03T15:00:10+00:00',release_path='policy/daily.json',receipt_bytes=canonical(receipt),
        trusted_receipt_sha256=sha256(canonical(receipt)).hexdigest(),files=files)
    return daily


def execution(daily,clock,caps=None):
    caps=caps or ProspectiveTemporaryCaps(book=daily['book'],authority=daily['authority'],admitted_decisions=daily['admitted_decisions'],clock=clock,
        admitted_settlements=daily.get('admitted_settlements'))
    market,units=capture(daily['book'],datetime.fromisoformat(clock()))
    day=verify_prospective_daily(**daily)
    admission=canonical(dict(schema='PROSPECTIVE_PAPER_EXECUTION_ADMISSION_V1',scope=SCOPE,
        descriptor_sha256=daily['book']['descriptor_sha256'],account_id=daily['book']['account_id'],
        account_revision=daily['book']['revision'],target_id=day['target_id'],daily_evidence_id=day['signal']['evidence_id'],
        cap_namespace_id=caps.namespace_id,source_sha256=market['source_hashes'],unit_review_sha256=sha256(canonical(units)).hexdigest(),
        available_at=clock()))
    return dict(daily_arguments=daily,execution_admission_bytes=admission,trusted_execution_admission_sha256=sha256(admission).hexdigest(),
        market_capture=market,unit_review=units,caps=caps,clock=clock)


class ProspectiveIntegrationTests(unittest.TestCase):
    def test_all_cash_zero_daily_target_has_empty_limits_and_holds(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder,monthly_price='20000')
            self.assertEqual(daily['selection_result']['payload']['target_quantities'],{'B':1})
            self.assertEqual(verify_prospective_daily(**daily)['signal']['effective_target_quantities'],{'B':0})
            args=execution(daily,lambda:'2026-11-03T15:00:10+00:00');self.addCleanup(args['caps'].close)
            result=produce_prospective_decision(**args)
            self.assertEqual(result['status'],'HOLD');self.assertIsNone(result['decision_bytes'])
            self.assertEqual(result['new_orders'],[])
            self.assertEqual(result['difference']['binding']['limits'],{})
            self.assertEqual(result['difference']['spendable_cash'],'20000')

    def test_actual_selector_daily_limits_admitted_acceptance_and_fill(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder);book=daily['book'];before=deepcopy(book)
            self.assertEqual(daily['selection_result']['payload']['target_quantities'],{'B':20})
            self.assertEqual(verify_prospective_daily(**daily)['signal']['effective_target_quantities'],{'B':10})
            args=execution(daily,lambda:'2026-11-03T15:00:10+00:00');self.addCleanup(args['caps'].close)
            result=produce_prospective_decision(**args)
            self.assertEqual(result['status'],'VERIFIED_PROSPECTIVE_PAPER_EXECUTION_DECISION')
            self.assertEqual(book,before)
            admitted={result['decision_sha256']:result['decision_bytes']}
            accepted=transact(book,dict(kind='ACCEPT',operation_id='real-pipeline',expected_revision=book['revision'],
                decision_bytes=result['decision_bytes'].decode()),authority=daily['authority'],admitted_decisions=admitted,
                current_target_id=daily['selection_result']['decision_id'],clock=lambda:datetime.fromisoformat('2026-11-03T15:00:11+00:00'))
            minutes={oid:[dict(security_id=o['security_id'],start='2026-11-03T15:01:00+00:00',end='2026-11-03T15:02:00+00:00',
                open='990',high='1010',low='900',close='990')] for oid,o in accepted['orders'].items()}
            pending={oid:o for oid,o in accepted['orders'].items() if o['closed'] is None}
            settlement=canonical(dict(schema=SETTLEMENT_SCHEMA,scope=SCOPE,status='VERIFIED_PROSPECTIVE_PAPER_SETTLEMENT_EVIDENCE',
                descriptor_sha256=accepted['descriptor_sha256'],registration_sha256=accepted['registration_sha256'],
                account_id=accepted['account_id'],account_revision=accepted['revision'],pending_orders_sha256=sha256(canonical(pending)).hexdigest(),
                observed_through='2026-11-03T15:02:00+00:00',available_at='2026-11-03T15:02:00+00:00',minutes=minutes,
                source_review=dict(scope='PROSPECTIVE_PAPER_MINUTE_SOURCE_REVIEW_V1',receipt_sha256='a'*64,
                    source_sha256={'synthetic-bars.json':sha256(canonical(minutes)).hexdigest()})))
            settlements={sha256(settlement).hexdigest():settlement}
            filled=transact(accepted,dict(kind='SETTLE',operation_id='fill',expected_revision=accepted['revision'],minutes=minutes,
                observed_through='2026-11-03T15:02:00+00:00',settlement_bytes=settlement.decode()),authority=daily['authority'],admitted_decisions=admitted,
                admitted_settlements=settlements,
                clock=lambda:datetime.fromisoformat('2026-11-03T15:02:01+00:00'))
            self.assertEqual(filled['shares'],{'B':10})
            price=Fraction(result['new_orders'][0]['limit_price'])
            self.assertEqual(Fraction(filled['cash']),20000-10*price)
            self.assertEqual(replay(filled,authority=daily['authority'],admitted_decisions=admitted,admitted_settlements=settlements),filled)
            # The same monthly target still yields ten daily shares; filled ten
            # shares must not cause another ten-share buy on the next preview.
            daily.update(book=filled,admitted_decisions=admitted,admitted_settlements=settlements,now='2026-11-03T15:02:10+00:00')
            receipt=json.loads(daily['receipt_bytes']);receipt.update(account_revision=filled['revision'],
                available_at='2026-11-03T15:02:02+00:00',valid_from='2026-11-03T15:02:02+00:00')
            daily['receipt_bytes']=canonical(receipt);daily['trusted_receipt_sha256']=sha256(canonical(receipt)).hexdigest()
            refreshed=verify_prospective_daily(**daily)
            self.assertEqual(refreshed['signal']['effective_target_quantities'],{'B':10})
            again=execution(daily,lambda:'2026-11-03T15:02:10+00:00',caps=args['caps'])
            second=produce_prospective_decision(**again)
            self.assertEqual(second['status'],'HOLD');self.assertEqual(second['new_orders'],[])
            self.assertEqual(Fraction(second['difference']['total_uninvested_cash']),Fraction(filled['cash']))

    def test_foreign_source_review_and_stale_execution_admission_rejected(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder);bad=deepcopy(daily['selection_arguments'])
            review=json.loads(bad['source_review_bytes']);review['account_revision']='foreign'
            bad['source_review_bytes']=canonical(review);bad['trusted_source_review_sha256']=sha256(canonical(review)).hexdigest()
            with self.assertRaisesRegex(ValueError,'SOURCE_BINDING'):verify_prospective_target(daily['selection_result'],**bad)
            args=execution(daily,lambda:'2026-11-03T15:00:10+00:00');self.addCleanup(args['caps'].close)
            args['market_capture']['files']['B.raw']+=b' '
            with self.assertRaisesRegex(ValueError,'MARK_SOURCE_CHANGED'):produce_prospective_decision(**args)

    def test_last_return_clock_and_external_market_mutation_rejected(self):
        for mode in ('late','mutation'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                daily=fixture(folder);args=execution(daily,lambda:'2026-11-03T15:00:10+00:00')
                self.addCleanup(args['caps'].close);calls=[0]
                def clock():
                    calls[0]+=1
                    if calls[0]==4 and mode=='mutation':args['market_capture']['files']['B.raw']+=b' '
                    return '2026-11-03T15:01:00+00:00' if calls[0]>=5 and mode=='late' else '2026-11-03T15:00:10+00:00'
                args['clock']=clock
                with self.assertRaisesRegex(ValueError,'PROSPECTIVE_DECISION_EXPIRED|PROSPECTIVE_INPUT_CHANGED'):
                    produce_prospective_decision(**args)

    def test_search_finishing_after_quote_lifetime_cannot_publish_target(self):
        with TemporaryDirectory() as folder:
            daily=fixture(folder);args=daily['selection_arguments']
            ticks=iter([args['now'],'2026-11-03T15:02:02+00:00','2026-11-03T15:02:02+00:00'])
            with self.assertRaisesRegex(ValueError,'PROSPECTIVE_SELECTION_EXPIRED'):
                select_prospective_target(clock=lambda:next(ticks),**args)


if __name__=='__main__':unittest.main()
