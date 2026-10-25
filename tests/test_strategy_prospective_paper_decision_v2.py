from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_prospective_paper_cap_daily_v2 import project_paper_cap_daily
from data.strategy_prospective_paper_decision_v2 import produce_prospective_decision, ProspectiveTemporaryCaps
from data.strategy_paper_application_descriptor_v2 import SCOPE
from backtest.current_strategy_prospective_paper_book_v2 import transact, replay, SETTLEMENT_SCHEMA
from backtest.current_strategy_prospective_paper_book_v1 import replay as replay_old
from prospective_paper_v2_fixture import fixture
from test_strategy_paper_execution_preview_v1 import capture


def next_day(folder, extra_code_paths=(), monthly_price='1000', extra_sources=None):
    release = canonical(dict(schema='PAPER_CAP_EXIT_DAILY_RELEASE_V2', policy_id='MONTHLY_CAP50_EXIT20',
        approved=True, scope='PAPER_DAILY_SIGNAL_RULE_ONLY', approved_at='2026-11-03T14:58:00+00:00'))
    session = dict(date='2026-11-04', open='2026-11-04T14:30:00+00:00', close='2026-11-04T21:00:00+00:00')
    following = dict(date='2026-11-05', open='2026-11-05T14:30:00+00:00',close='2026-11-05T21:00:00+00:00')
    args = fixture(folder, monthly_price=monthly_price, extra_code_paths=extra_code_paths,
                   extra_sources={**(extra_sources or {}),'policy/cap.json':release}, extra_sessions=[session,following])
    inputs = json.loads(args['files']['normalized.json'])
    inputs.update(signal_date='2026-11-03', observed_at='2026-11-03T21:00:00+00:00')
    inputs['session_dates'].append('2026-11-03')
    inputs['session_close_times']['closes']['2026-11-03'] = inputs['observed_at']
    for history in inputs['histories'].values():
        history['closes'] = history['closes'][1:] + [dict(date='2026-11-03',completed_at=inputs['observed_at'],close='101')]
        history['units']['unit_asof']='2026-11-03'
    args['files']['normalized.json']=canonical(inputs)
    args['now']='2026-11-04T15:00:10+00:00'
    receipt=json.loads(args['receipt_bytes'])
    receipt.update(available_at='2026-11-04T15:00:02+00:00',source_received_at='2026-11-04T15:00:01+00:00',
        valid_from='2026-11-04T15:00:02+00:00',valid_until=session['close'],execution_session=session,
        market_asof=inputs['observed_at'],source_sha256={p:sha256(raw).hexdigest() for p,raw in args['files'].items()})
    args['receipt_bytes']=canonical(receipt);args['trusted_receipt_sha256']=sha256(args['receipt_bytes']).hexdigest()
    return args


class NewPolicyExecutionTests(unittest.TestCase):
    def test_cap_signal_to_limit_accept_fill_and_old_policy_rejection(self):
        self.exercise_chain()

    def test_filled_position_new_zero_cap_exits_without_cash_credit(self):
        self.exercise_chain(monthly_price='10000', zero_cap=True)

    def test_buy_data_failure_does_not_block_verified_exit(self):
        self.exercise_chain(buy_failure=True)

    def exercise_chain(self, monthly_price='1000', zero_cap=False, buy_failure=False):
        with TemporaryDirectory() as folder:
            daily=next_day(folder,monthly_price=monthly_price); book=daily['book']; authority=daily['authority']
            with self.assertRaises(ValueError):
                replay_old(book,authority=authority,admitted_decisions={})
            store=MonthlyPeakExitStore(Path(folder)/'risk.sqlite')
            day=project_paper_cap_daily(daily_arguments=daily,risk_store=store,cap_release_path='policy/cap.json')
            quantity=1 if zero_cap else 10
            self.assertEqual(day['signal']['effective_target_quantities'],{'B':quantity})
            clock=lambda:'2026-11-04T15:00:10+00:00'
            caps=ProspectiveTemporaryCaps(book=book,authority=authority,admitted_decisions={},clock=clock)
            self.addCleanup(caps.close)
            market,units=capture(book,datetime.fromisoformat(clock()))
            admission=canonical(dict(schema='PROSPECTIVE_PAPER_EXECUTION_ADMISSION_V1',scope=SCOPE,
                descriptor_sha256=book['descriptor_sha256'],account_id=book['account_id'],account_revision=book['revision'],
                target_id=day['target_id'],daily_evidence_id=day['signal']['evidence_id'],cap_namespace_id=caps.namespace_id,
                source_sha256=market['source_hashes'],unit_review_sha256=sha256(canonical(units)).hexdigest(),available_at=clock()))
            result=produce_prospective_decision(daily_arguments=daily,execution_admission_bytes=admission,
                trusted_execution_admission_sha256=sha256(admission).hexdigest(),market_capture=market,unit_review=units,
                caps=caps,clock=clock,risk_store=store,cap_release_path='policy/cap.json')
            self.assertEqual(result['decision']['policy_id'],'MONTHLY_CAP50_EXIT20')
            self.assertEqual([(o['side'],o['quantity']) for o in result['new_orders']],[('BUY',quantity)])
            admitted={result['decision_sha256']:result['decision_bytes']}
            request=dict(kind='ACCEPT',operation_id='cap-buy',expected_revision=book['revision'],decision_bytes=result['decision_bytes'].decode())
            accepted=transact(book,request,authority=authority,admitted_decisions=admitted,
                current_target_id=day['target_id'],clock=lambda:datetime.fromisoformat('2026-11-04T15:00:11+00:00'))
            pending={oid:o for oid,o in accepted['orders'].items() if o['closed'] is None}
            minutes={oid:[dict(security_id=o['security_id'],start='2026-11-04T15:01:00+00:00',end='2026-11-04T15:02:00+00:00',
                open='990',high='1010',low='900',close='990')] for oid,o in pending.items()}
            settlement=canonical(dict(schema=SETTLEMENT_SCHEMA,scope=SCOPE,status='VERIFIED_PROSPECTIVE_PAPER_SETTLEMENT_EVIDENCE',
                descriptor_sha256=book['descriptor_sha256'],registration_sha256=book['registration_sha256'],account_id=book['account_id'],
                account_revision=accepted['revision'],pending_orders_sha256=sha256(canonical(pending)).hexdigest(),
                observed_through='2026-11-04T15:02:00+00:00',available_at='2026-11-04T15:02:00+00:00',minutes=minutes,
                source_review=dict(scope='PROSPECTIVE_PAPER_MINUTE_SOURCE_REVIEW_V1',receipt_sha256='a'*64,
                    source_sha256={'fixture':sha256(canonical(minutes)).hexdigest()})))
            settlements={sha256(settlement).hexdigest():settlement}
            filled=transact(accepted,dict(kind='SETTLE',operation_id='cap-fill',expected_revision=accepted['revision'],
                minutes=minutes,observed_through='2026-11-04T15:02:00+00:00',settlement_bytes=settlement.decode()),
                authority=authority,admitted_decisions=admitted,admitted_settlements=settlements,
                clock=lambda:datetime.fromisoformat('2026-11-04T15:02:01+00:00'))
            self.assertEqual(filled['shares'],{'B':quantity})
            self.assertEqual(Fraction(filled['cash']),20000-quantity*Fraction(result['new_orders'][0]['limit_price']))
            self.assertEqual(replay(filled,authority=authority,admitted_decisions=admitted,admitted_settlements=settlements),filled)
            if zero_cap:
                from paper_zero_cap_exit_case import verify_zero_cap_exit
                verify_zero_cap_exit(self,daily,filled,admitted,settlements,store,caps,admission)
                return
            # Next completed close crosses the 20% threshold: the same chain
            # must now produce a full exit, not another monthly top-up.
            exit_daily=deepcopy(daily)
            exit_daily.update(book=filled,admitted_decisions=admitted,admitted_settlements=settlements,
                              now='2026-11-05T15:00:10+00:00')
            history=json.loads(exit_daily['files']['normalized.json'])
            history.update(signal_date='2026-11-04',observed_at='2026-11-04T21:00:00+00:00')
            history['session_dates'].append('2026-11-04')
            history['session_close_times']['closes']['2026-11-04']=history['observed_at']
            for row in history['histories'].values():
                row['closes']=row['closes'][1:]+[dict(date='2026-11-04',completed_at=history['observed_at'],close='80')]
                row['units']['unit_asof']='2026-11-04'
            exit_daily['files']['normalized.json']=canonical(history)
            receipt=json.loads(exit_daily['receipt_bytes'])
            receipt.update(account_revision=filled['revision'],available_at='2026-11-05T15:00:02+00:00',
                source_received_at='2026-11-05T15:00:01+00:00',valid_from='2026-11-05T15:00:02+00:00',
                valid_until='2026-11-05T21:00:00+00:00',market_asof=history['observed_at'],
                execution_session=dict(date='2026-11-05',open='2026-11-05T14:30:00+00:00',close='2026-11-05T21:00:00+00:00'),
                source_sha256={p:sha256(raw).hexdigest() for p,raw in exit_daily['files'].items()})
            exit_daily['receipt_bytes']=canonical(receipt)
            exit_daily['trusted_receipt_sha256']=sha256(exit_daily['receipt_bytes']).hexdigest()
            exit_signal=project_paper_cap_daily(daily_arguments=exit_daily,risk_store=store,cap_release_path='policy/cap.json')
            exit_clock=lambda:'2026-11-05T15:00:10+00:00'
            caps.clock=exit_clock
            market,units=capture(filled,datetime.fromisoformat(exit_clock()))
            exit_admission=json.loads(admission)
            exit_admission.update(account_revision=filled['revision'],daily_evidence_id=exit_signal['signal']['evidence_id'],
                source_sha256=market['source_hashes'],unit_review_sha256=sha256(canonical(units)).hexdigest(),available_at=exit_clock())
            raw_exit_admission=canonical(exit_admission)
            exit_arguments=dict(daily_arguments=exit_daily,execution_admission_bytes=raw_exit_admission,
                trusted_execution_admission_sha256=sha256(raw_exit_admission).hexdigest(),market_capture=market,unit_review=units,
                caps=caps,clock=exit_clock,risk_store=store,cap_release_path='policy/cap.json')
            if buy_failure:
                # Inject only the buy-side failure; fallback still uses the real
                # quote/unit validator and actual held-position difference.
                from unittest.mock import patch
                from data.strategy_execution_limits_common_v1 import _build_execution_limits_core
                exit_admission.update(sell_source_sha256=market['source_hashes'],
                    sell_unit_review_sha256=sha256(canonical(units)).hexdigest())
                bound=canonical(exit_admission)
                exit_arguments.update(execution_admission_bytes=bound,
                    trusted_execution_admission_sha256=sha256(bound).hexdigest(),
                    sell_market_capture=market,sell_unit_review=units)
                calls=[]
                def fail_buy_once(**arguments):
                    calls.append(arguments['target_quantities'])
                    if len(calls)==1:raise ValueError('MINUTE_GAP')
                    return _build_execution_limits_core(**arguments)
                with patch('data.strategy_prospective_paper_decision_v2._build_execution_limits_core',side_effect=fail_buy_once):
                    exited=produce_prospective_decision(**exit_arguments)
                self.assertEqual(len(calls),2)
            else:
                exited=produce_prospective_decision(**exit_arguments)
            self.assertEqual(exited['decision']['effective_target_quantities'],{'B':0})
            self.assertEqual([(o['side'],o['quantity']) for o in exited['new_orders']],[('SELL',10)])
            exit_admitted={**admitted,exited['decision_sha256']:exited['decision_bytes']}
            selling=transact(filled,dict(kind='ACCEPT',operation_id='cap-exit',expected_revision=filled['revision'],
                decision_bytes=exited['decision_bytes'].decode()),authority=authority,admitted_decisions=exit_admitted,
                admitted_settlements=settlements,current_target_id=day['target_id'],
                clock=lambda:datetime.fromisoformat('2026-11-05T15:00:11+00:00'))
            self.assertEqual(sum(o['quantity'] for o in selling['orders'].values() if o['closed'] is None and o['side']=='SELL'),10)
            bad=deepcopy(result['decision']);bad['policy_id']='SMA20_HALF_OFF_RESEARCH'
            raw=canonical(bad)
            with self.assertRaisesRegex(ValueError,'PROSPECTIVE_DECISION_BINDING'):
                transact(book,dict(request,decision_bytes=raw.decode()),authority=authority,
                    admitted_decisions={sha256(raw).hexdigest():raw},current_target_id=day['target_id'],
                    clock=lambda:datetime.fromisoformat('2026-11-04T15:00:11+00:00'))


if __name__=='__main__':unittest.main()
