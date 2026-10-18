"""Explicit initial execution month, including legitimate month-end next-month use."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import test_current_quantity_v2_current_cash_plan as fixtures
from test_current_quantity_v2_current_cash_sources import snapshot_fixture,month_config
from test_current_quantity_v2_intraday_reference import NOW,raw
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_current_cash_plan import build_current_cash_plan,canonical
from data.current_quantity_v2_execution_month import validate_execution_month
from data.current_quantity_v2_current_cash_ledger_adapter import freeze_current_cash_proposal,build_recorded_cash_proposal
from data.current_quantity_v2_paper_ledger import initial,review_ledger,accept_proposal


class ExecutionMonthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.CurrentCashTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixtures.CurrentCashTests.tearDownClass()

    def test_public_requires_document_and_blocks_next_month_before_quote_checks(self):
        args=deepcopy(fixtures.CurrentCashTests.args)
        args['execution_package']['documents'].pop('execution_month_mandate')
        self.assertEqual(build_current_cash_plan(**args)['reason'],'MONTH_MANDATE_REQUIRED')
        args=deepcopy(fixtures.CurrentCashTests.args)
        args['now']='2026-11-02T15:00:00+00:00'
        args['genesis_declaration'].update(target_month='2026-11',active_date='2026-11-02')
        self.assertEqual(build_current_cash_plan(**args)['reason'],'RESELECT_REQUIRED')
        path=args['execution_package']['documents']['execution_month_mandate']
        args['execution_package']['files'][path]+=b' '
        self.assertEqual(build_current_cash_plan(**args)['reason'],'SOURCE_HASH_MISMATCH')

    def test_explicit_next_month_calendar_and_missing_boundary(self):
        files={'input':b'fixed input','calendar-source':b'explicit synthetic schedule'}
        pins={p:sha256(v).hexdigest() for p,v in files.items()};original={'input':pins['input']}
        calendar=dict(schema='SCHEDULED_REGULAR_SESSIONS_V1',calendar=['2026-10-30','2026-11-02','2026-11-03'],
            source_hashes={'calendar-source':pins['calendar-source']})
        files['calendar']=canonical(calendar);pins['calendar']=sha256(files['calendar']).hexdigest()
        d=dict(schema='V2_INITIAL_EXECUTION_MONTH_V1',mode='MONTH_END_NEXT_MONTH',decision_date='2026-10-30',
            target_month='2026-11',first_active_session='2026-11-02',original_source_hashes=original,source_hashes=pins,calendar_path='calendar')
        def check(declaration=d,session='2026-11-02'):
            return validate_execution_month(declaration,decision_date='2026-10-30',original_pins=original,session=session,files=files,pins=pins)
        self.assertEqual(check(),'2026-11')
        wrong=deepcopy(d);wrong['original_source_hashes']={'input':original['input'],'other-input':'0'*64}
        with self.assertRaisesRegex(ValueError,'INPUT_BINDING'):check(wrong)
        with self.assertRaisesRegex(ValueError,'RESELECT_REQUIRED'):check(session='2026-12-01')
        with self.assertRaisesRegex(ValueError,'NOT_ACTIVE'):check(session='2026-10-30')
        wrong=deepcopy(d);wrong['first_active_session']='2026-11-03'
        with self.assertRaisesRegex(ValueError,'ADJACENT'):check(wrong)
        wrong=deepcopy(d);wrong['mode']='INITIAL_CURRENT_MONTH_BOOTSTRAP'
        with self.assertRaisesRegex(ValueError,'BOOTSTRAP'):check(wrong)

    def test_provider_missing_stale_mandate_zero_fetch_and_source_drift(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);snapshots,view=snapshot_fixture(root);calls=[];clock=[NOW]
            service=CurrentQuantityV2CurrentCashSources(root=root,snapshot_service=snapshots,
                server_account_id='pool',fetch=lambda t:(calls.append(t),raw(t,10))[1],clock=lambda:clock[0])
            with self.assertRaisesRegex(ValueError,'MONTH_MANDATE_REQUIRED'):service.capture(view['decision_id'])
            self.assertEqual(calls,[])
            service.month_mandate=month_config(root);clock[0]=NOW.replace(month=11,day=2)
            with self.assertRaisesRegex(ValueError,'RESELECT_REQUIRED'):service.capture(view['decision_id'])
            self.assertEqual(calls,[])
            clock[0]=NOW;service.capture(view['decision_id']);self.assertEqual(len(calls),2)
            (root/'month.json').write_bytes((root/'month.json').read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'MONTH_MANDATE_HASH_MISMATCH'):service.resolve(view['decision_id'])
            self.assertEqual(len(calls),2)

    def test_legacy_accepted_json_replays_but_cannot_be_newly_accepted(self):
        args=deepcopy(fixtures.CurrentCashTests.args);plan=build_current_cash_plan(**args)
        proposal=freeze_current_cash_proposal(plan,args['execution_package'])
        causal=deepcopy(proposal['causal_inputs']);f=causal['frozen_execution_package']
        path=f['documents'].pop('execution_month_mandate');f['source_hashes'].pop(path);f['files_base64'].pop(path)
        legacy=build_recorded_cash_proposal(**causal)
        saved=initial(dict(proposal=legacy,account_state=causal['account_state'],accepted_at=causal['now']))
        self.assertEqual(review_ledger(json.loads(json.dumps(saved))),saved)
        with self.assertRaisesRegex(ValueError,'MONTH_MANDATE_REQUIRED'):
            accept_proposal(legacy,account_state=causal['account_state'],now=causal['now'])
        # Accepted DAY replay uses frozen acceptance, not the present calendar month.
        self.assertEqual(review_ledger(saved)['orders'],saved['orders'])


if __name__=='__main__':unittest.main()
