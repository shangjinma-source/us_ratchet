import base64
from copy import deepcopy
from datetime import datetime,timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import test_current_quantity_v2_current_cash_plan as base
from data.current_quantity_v2_current_cash_plan import build_current_cash_plan
from data.current_quantity_v2_current_cash_ledger_adapter import freeze_current_cash_proposal,build_recorded_cash_proposal
from data.current_quantity_v2_paper_ledger import accept_proposal,review_ledger
from data.current_quantity_v2_paper_store import QuantityV2PaperStore
from data.current_quantity_v2_paper_service import compact


def frozen_fixture(args):
    args=deepcopy(args);plan=build_current_cash_plan(**args)
    return freeze_current_cash_proposal(plan,args['execution_package']),args


class CurrentCashLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base.CurrentCashTests.setUpClass();cls.args=deepcopy(base.CurrentCashTests.args)
    @classmethod
    def tearDownClass(cls):base.CurrentCashTests.tearDownClass()

    def test_temporary_store_delayed_accept_fill_fee_retry_restore(self):
        p,args=frozen_fixture(self.args);p=json.loads(json.dumps(p));before=deepcopy(args['capital_decision'])
        now=datetime.fromisoformat(args['now'])+timedelta(seconds=1);calls=[]
        def factory(at):calls.append(at);return dict(proposal=deepcopy(p),account_state=deepcopy(args['account_state']))
        with TemporaryDirectory() as folder:
            path=Path(folder)/'paper.sqlite3';store=QuantityV2PaperStore(path)
            request=dict(account_id=p['account_id'],proposal_id=p['proposal_id'],operation_id='new-cash',factory=factory,clock=lambda:now)
            accepted=store.accept(**request);ledger=accepted['ledger']
            self.assertEqual(ledger['target_quantities'],{'A':6,'B':4});self.assertEqual(ledger['historical_target_quantities'],{'A':1,'B':1})
            self.assertEqual(ledger['cash'],'110');self.assertEqual(ledger['reserved_cash'],'90')
            oid=next(k for k,o in ledger['orders'].items() if o['security_id']=='A')
            now+=timedelta(seconds=1)
            filled=store.record_event(account_id=p['account_id'],event=dict(event_id='fill',type='FILL',order_id=oid,
                expected_revision=ledger['revision'],quantity=1,price='9',fees='1/5',executed_at=now.isoformat()),clock=lambda:now)
            self.assertEqual(filled['ledger']['cash'],'504/5');self.assertEqual(filled['ledger']['shares'],{'A':1})
            request['factory']=lambda at:(_ for _ in ()).throw(AssertionError('retry factory'))
            request['clock']=lambda:(_ for _ in ()).throw(AssertionError('retry clock'))
            self.assertEqual(store.accept(**request),filled);self.assertEqual(len(calls),1)
            args['execution_package']['files'].clear() # Replay uses accepted JSON only, no live package or clock.
            restored=QuantityV2PaperStore(path).read(p['account_id']);self.assertEqual(restored,filled)
            view=compact(restored);self.assertEqual(view['target_scope'],'NEW_CASH_CURRENT_QUOTE_ALLOCATION')
            self.assertEqual(view['execution_target_id'],p['execution_target_id'])
            self.assertEqual(view['historical_target_quantities'],{'A':1,'B':1});self.assertNotIn('causal_inputs',view)
            self.assertEqual(review_ledger(json.loads(json.dumps(restored['ledger']))),restored['ledger'])
        self.assertEqual(args['capital_decision'],before)

    def test_normalized_replay_omits_only_historical_not_current_evidence(self):
        p,args=frozen_fixture(self.args);f=p['causal_inputs']['frozen_execution_package']
        files={k:base64.b64decode(v) for k,v in f['files_base64'].items()}
        self.assertLess(sum(map(len,files.values())),16*1024*1024)
        self.assertLess(len(files),len(f['source_hashes']))
        self.assertFalse(p['source_bytes_verified']);self.assertFalse(p['historical_source_bytes_reverified'])
        self.assertTrue(p['current_execution_bytes_verified'])
        a=deepcopy(args);a['execution_package']=dict(files=files,source_hashes=f['source_hashes'],documents=f['documents'])
        self.assertEqual(build_current_cash_plan(**a)['status'],'BLOCKED') # Public builder remains full closure.
        self.assertEqual(build_recorded_cash_proposal(**p['causal_inputs']),p)
        for kind in ('raw','identity','target','cash','pin','base64'):
            bad=deepcopy(p)
            if kind=='raw':bad['causal_inputs']['frozen_execution_package']['files_base64']['current/A.raw']=base64.b64encode(b'{}').decode()
            elif kind=='identity':bad['causal_inputs']['frozen_execution_package']['files_base64'].pop('current/review-evidence.json')
            elif kind=='target':bad['target_quantities']['A']=7
            elif kind=='cash':bad['causal_inputs']['account_state']['cash']='111'
            elif kind=='pin':bad['causal_inputs']['frozen_execution_package']['source_hashes']['input.json']='0'*64
            else:bad['causal_inputs']['frozen_execution_package']['files_base64']['current/A.raw']+='\n'
            with self.subTest(kind=kind),self.assertRaises((ValueError,KeyError)):
                accept_proposal(bad,account_state=args['account_state'],now=datetime.fromisoformat(args['now'])+timedelta(seconds=1))

    def test_historical_current_reference_must_remain_frozen(self):
        args=deepcopy(self.args);package=args['execution_package'];path=package['documents']['identities']
        identities=json.loads(package['files'][path]);identities['A']['source_references'].append('A.json')
        package['files'][path]=json.dumps(identities).encode()
        from hashlib import sha256
        package['source_hashes'][path]=sha256(package['files'][path]).hexdigest()
        args['genesis_declaration']['source_references'].append('A.json')
        p,args=frozen_fixture(args)
        self.assertIn('A.json',p['causal_inputs']['frozen_execution_package']['files_base64'])
        bad=deepcopy(p['causal_inputs']);bad['frozen_execution_package']['files_base64'].pop('A.json')
        with self.assertRaises(ValueError):build_recorded_cash_proposal(**bad)
        from data.current_quantity_v2_current_cash_plan import closure
        with self.assertRaisesRegex(ValueError,'SAFE_RELATIVE_PATH'):
            closure(dict(files={'ok':b'x'},source_hashes={'ok':sha256(b'x').hexdigest(),'../old':'0'*64},documents={}),historical_pins={'../old':'0'*64})

    def test_accept_deadline_and_account_change_reject(self):
        p,args=frozen_fixture(self.args)
        with self.assertRaises(ValueError):accept_proposal(p,account_state=args['account_state'],now=p['reference_valid_until'])
        account=deepcopy(args['account_state']);account['cash']='111'
        with self.assertRaises(ValueError):accept_proposal(p,account_state=account,now=args['now'])

if __name__=='__main__':unittest.main()
