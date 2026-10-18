import base64
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import unittest

import test_current_quantity_v2_current_cash_plan as base
from data.current_quantity_v2_current_cash_plan import build_current_cash_plan, rebuild_current_cash_plan
from data.current_quantity_v2_current_cash_ledger_adapter import (
    freeze_current_cash_proposal, build_recorded_cash_proposal)
from data.current_quantity_v2_pullback_cap_store import PullbackCapStore


def pullback_package(args, store_path):
    args = deepcopy(args)
    package = args['execution_package']
    files, pins, docs = (package[key] for key in ('files', 'source_hashes', 'documents'))
    def put(path, value):
        files[path] = json.dumps(value, sort_keys=True).encode()
        pins[path] = sha256(files[path]).hexdigest()
        return path
    now = args['now']
    store = PullbackCapStore(store_path, clock=lambda: now,
                            max_history_rows=100, max_history_bytes=1000000)
    reviews = json.loads(files[docs['current_unit_reviews']])
    proofs = {}
    for sid, receipt_path in docs['quote_receipts'].items():
        receipt = json.loads(files[receipt_path])
        raw_path = receipt['raw_path']
        document = json.loads(files[raw_path])
        result = document['chart']['result'][0]
        opening = base.NOW.replace(hour=9, minute=30, second=0)
        closing = base.NOW.replace(hour=16, minute=0, second=0)
        result['timestamp'] = [int((opening + timedelta(minutes=i)).timestamp()) for i in range(150)]
        result['indicators']['quote'] = [dict(open=[10]*150, high=[11]*150,
            low=[6]+[9]*149, close=[10]*150, volume=[100]*150)]
        put(raw_path, document)
        receipt['raw_sha256'] = pins[raw_path]
        put(receipt_path, receipt)
        reviews[sid]['reference_source_hashes'] = {raw_path:pins[raw_path], receipt_path:pins[receipt_path]}
        candidate = store.candidate(raw=files[raw_path], expected_sha256=pins[raw_path],
            security_id=sid, ticker=receipt['ticker'], session='2026-10-15',
            session_open=opening.isoformat(), session_close=closing.isoformat(),
            captured_at=receipt['captured_at'], checked_at=now, now=now,
            rebound_fraction='1/2', minimum_discount='1/200', maximum_age_seconds=120)
        proofs[sid] = put('current/'+sid+'.pullback-proof.json', candidate['frozen_proof'])
    put(docs['current_unit_reviews'], reviews)
    docs['pullback_policy'] = put('current/pullback-policy.json', dict(
        schema='V2_PULLBACK_EXECUTION_POLICY_V1', status='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED',
        rebound_fraction='1/2', minimum_discount='1/200', maximum_age_seconds=120))
    docs['pullback_proofs'] = proofs
    return args


class PullbackCashPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.CurrentCashTests.setUpClass()
        cls.args = pullback_package(base.CurrentCashTests.args,
            Path(base.CurrentCashTests.temp.name)/'pullback-research.sqlite3')

    @classmethod
    def tearDownClass(cls):
        base.CurrentCashTests.tearDownClass()

    def test_cash_envelopes_rebuild_and_frozen_recorded_replay(self):
        args = deepcopy(self.args)
        before = deepcopy(args)
        plan = build_current_cash_plan(**args)
        self.assertEqual(plan['status'], 'READY', plan)
        self.assertEqual(plan['execution_target_quantities'], {'A':7,'B':5})
        self.assertEqual(Fraction(plan['indicative_notional']), 96)
        self.assertEqual(Fraction(plan['remaining_cash']), 14)
        self.assertTrue(all(Fraction(row['limit_price']) == 8 for row in plan['rows']))
        self.assertTrue(all(Fraction(row['notional']) <= Fraction(row['frozen_dollar_allocation'])
                            for row in plan['rows']))
        self.assertEqual(rebuild_current_cash_plan(plan,args['execution_package']), plan)
        frozen = freeze_current_cash_proposal(plan,args['execution_package'])
        self.assertEqual(build_recorded_cash_proposal(**frozen['causal_inputs']), frozen)
        self.assertEqual(frozen['orders'], plan['orders'])
        self.assertEqual(frozen['target_quantities'], plan['execution_target_quantities'])
        self.assertEqual(frozen['reference_valid_until'], plan['reference_valid_until'])
        documents = args['execution_package']['documents']
        packed = frozen['causal_inputs']['frozen_execution_package']['files_base64']
        for path in [documents['pullback_policy'],*documents['pullback_proofs'].values()]:
            self.assertEqual(base64.b64decode(packed[path]),args['execution_package']['files'][path])
        self.assertEqual(args,before)

    def test_proof_policy_raw_identity_and_expiry_tampering_blocked(self):
        self.assertEqual(build_current_cash_plan(**deepcopy(self.args))['status'],'READY')
        for mode in ('proof','policy','raw','identity','expiry','missing-proof'):
            args = deepcopy(self.args)
            package = args['execution_package']; docs = package['documents']
            if mode == 'expiry':
                args['now'] = (base.NOW.replace(second=0)+timedelta(seconds=120)).isoformat()
            elif mode == 'missing-proof':
                docs['pullback_proofs'].pop('A')
            else:
                path = docs['pullback_policy'] if mode == 'policy' else docs['pullback_proofs']['A']
                if mode == 'raw': path = 'current/A.raw'
                value = json.loads(package['files'][path])
                if mode == 'proof': value['result']['candidate']['limit_price'] = '1'
                elif mode == 'policy': value['rebound_fraction'] = '1/4'
                elif mode == 'identity': value['parameters']['security_id'] = 'B'
                else: value['chart']['result'][0]['meta']['regularMarketPrice'] = 11
                package['files'][path] = json.dumps(value).encode()
                package['source_hashes'][path] = sha256(package['files'][path]).hexdigest()
            with self.subTest(mode=mode):
                self.assertEqual(build_current_cash_plan(**args)['status'],'BLOCKED')

    def test_frozen_proof_replayed_not_just_included(self):
        plan = build_current_cash_plan(**deepcopy(self.args))
        self.assertEqual(plan['status'],'READY',plan)
        frozen = freeze_current_cash_proposal(plan,self.args['execution_package'])
        for kind in ('proof','policy','missing'):
            causal = deepcopy(frozen['causal_inputs'])
            package = causal['frozen_execution_package']
            docs = package['documents']
            path = docs['pullback_policy'] if kind == 'policy' else docs['pullback_proofs']['A']
            if kind == 'missing':
                package['files_base64'].pop(path)
            else:
                value = json.loads(base64.b64decode(package['files_base64'][path]))
                if kind == 'policy': value['minimum_discount']='1/100'
                else: value['record_hash']='0'*64
                raw = json.dumps(value).encode()
                package['files_base64'][path]=base64.b64encode(raw).decode()
                package['source_hashes'][path]=sha256(raw).hexdigest()
            with self.subTest(kind=kind),self.assertRaises((ValueError,KeyError)):
                build_recorded_cash_proposal(**causal)


if __name__ == '__main__':
    unittest.main()
