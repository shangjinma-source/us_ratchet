"""Real profiled selection -> V4 risk/current daily HTTP; isolated admitted source."""
from datetime import timedelta
from hashlib import sha256
from fractions import Fraction
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.strategy_account_ledger import canonical
from data.monthly_cap_exit_reader_v4 import MonthlyCapExitReaderV4
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_daily_rebound_archive import archive_rebound_evidence
from data.strategy_daily_composition_v7 import DailyCompositionV7
from api.strategy_daily_preview_v4 import create_router
import test_profiled_monthly_current_cash_selection as fixture


class MonthlyFirstDayTests(fixture.ProfiledMonthlySelectionTests):
    def verify_daily_handoff(self, f, monthly, target, state):
        now = f.f.now
        day = '2026-11-30'
        domain = set(state['shares']) | set(target['payload']['target_quantities'])
        closes = {day: day+'T21:00:00+00:00', '2026-12-01': '2026-12-01T21:00:00+00:00'}
        inputs = dict(base_target=dict(origin_reference=target['target_id'],
            monthly_target_created_at=target['payload']['created_at'],
            monthly_decision_date=day, quantities=target['payload']['target_quantities'],
            price_units={sid:'nominal' for sid in domain}), signal_date=day,
            observed_at=now.isoformat(), session_dates=list(closes),
            session_close_times=dict(closes=closes, review_reference='isolated-calendar'),
            histories={sid:dict(units=dict(schema='REVIEWED_CONSTANT_DECISION_SHARE_UNITS_V1',
                unit_asof=day,currency='USD',basis_id='nominal',review_reference='fixture'),
                source_reference='fixture', closes=[dict(date=day,completed_at=closes[day],close='10')])
                for sid in domain})
        files = {'inputs.json':canonical(inputs)}
        receipt = dict(schema='SERVER_REVIEWED_DAILY_EVIDENCE_V1',
            account_revision=state['revision'],target_id=target['target_id'],
            normalized_inputs_path='inputs.json',
            source_sha256={k:sha256(v).hexdigest() for k,v in files.items()})
        archive = archive_rebound_evidence(root=f.root/'handoff-source',
            receipt_bytes=canonical(receipt),files=files)
        # Source approval is a fixture. The runtime selector, risk projection,
        # execution provider and cash difference calculation are real code.
        signal = dict(account_id=state['account_id'],account_revision=state['revision'],
            target_id=target['target_id'],policy_id='MONTHLY_CAP50_EXIT20',
            evidence_id=archive['receipt_sha256'],evidence_archive=archive,
            observed_at=now.isoformat(),available_at=now.isoformat(),valid_from=now.isoformat(),
            valid_until=(now+timedelta(minutes=2)).isoformat())
        risk = MonthlyPeakExitStore(f.root/'handoff-risk.sqlite')
        reader = MonthlyCapExitReaderV4(source_reader=lambda *args:dict(
            status='DAILY_SIGNAL_READY',signal=signal,evidence_archive=archive),
            risk_store=risk,source_archive_root=f.root/'handoff-source',
            output_archive_root=f.root/'handoff-projected',release_bytes=b'fixture',
            validate_release=monthly.validate_current_target_pins,risk_history=None)
        runtime, configuration = monthly._for_target(target)
        fees = target['payload']['decision']['payload']['input_binding']['search_arguments']['fee_bps']
        daily = DailyCompositionV7(monthly_service=monthly,evidence_reader=reader,
            execution_provider=runtime.execution_provider,clock=lambda:f.f.now,
            policy_execution_enabled=True,policy_id='MONTHLY_CAP50_EXIT20',fee_bps=fees)
        app=FastAPI();app.include_router(create_router(service=daily))
        with TestClient(app) as client:
            response=client.post('/api/strategy-daily-v3/preview',json=dict(
                expected_revision=state['revision'],target_id=target['target_id']))
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertEqual(result['status'],'READY',response.text)
        self.assertEqual(risk.read(state['account_id'])['decision_date'],day)
        self.assertTrue(any(row['security_id']=='departed-id' and row['side']=='SELL'
            and row['quantity']==2 for row in result['new_orders']),response.text)
        buy_cost=sum((Fraction(str(row['limit_price']))*row['quantity']
            for row in result['new_orders'] if row['side']=='BUY'),Fraction(0))
        self.assertLessEqual(buy_cost,Fraction(state['available_cash']))
        self.assertEqual(monthly.accounts.read(),state)
        self.assertEqual(monthly.current(),target)
