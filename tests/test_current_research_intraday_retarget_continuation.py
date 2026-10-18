import base64
import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
import test_current_research_intraday_retarget_evidence as fixtures
from data.current_research_intraday_retarget_evidence import accept_retarget_with_execution_evidence,replay_execution_evidence
from data.current_research_intraday_execution_reference import read_intraday_execution_reference
from data.current_research_intraday_retarget_ledger import apply_retarget_event
from data.current_research_intraday_retarget_continuation import build_retarget_continuation_proposal
from data.current_research_intraday_retarget_sizing import build_intraday_retarget_sizing

class ContinuationTests(unittest.TestCase):
    def fixture(self,root):
        old,p,args=fixtures.FrozenRetargetTests().fixture(root)
        env=accept_retarget_with_execution_evidence(old,p,**args);now=args['now']
        def record(side,kind,**extra):
            s=env['ledger'];o=next(o for o in s['orders'].values() if o['side']==side)
            event=dict(event_id=str(len(s['retarget_events'])),kind=kind,expected_revision=s['revision'],order_id=o['order_id'],recorded_at=now.isoformat(),**extra)
            env['ledger']=apply_retarget_event(s,event,now=now)
        record('SELL','FILL',quantity=2,price='1500',fees='0',executed_at=now.isoformat())
        record('BUY','FILL',quantity=100,price='39',fees='0',executed_at=now.isoformat())
        record('BUY','CANCEL',cancelled_at=now.isoformat())
        evidence=deepcopy(env['execution_evidence'])
        for key in ('execution_inputs','units','references'):evidence[key].pop('sndk')
        paths=set(evidence['execution_inputs']['new']['source_hashes'])|set(evidence['units']['new']['source_references'])
        for key in ('files','source_hashes'):evidence[key]={p:v for p,v in evidence[key].items() if p in paths}
        u=evidence['units']['new'];u['retarget_acceptance_id']=env['ledger']['retarget_acceptance_id'];u['original_reference_source_hashes']=evidence['references']['new']['source_hashes']
        return env,dict(expected_revision=env['ledger']['revision'],execution_evidence=evidence,now=now)
    def test_partial_cancel_remaining_target_no_cash_reset(self):
        with tempfile.TemporaryDirectory() as root:env,args=self.fixture(root)
        before=deepcopy(env);r=build_retarget_continuation_proposal(env,**args)
        self.assertEqual(r['status'],'READY',r);self.assertEqual(r['target_quantities'],{'new':505})
        self.assertEqual(r['orders'][0]['quantity'],405);self.assertEqual(r['orders'][0]['side'],'BUY')
        self.assertEqual(r['actual_cash'],'16300');self.assertEqual(r['reserved_buy_cash'],str(405*Fraction('39.99')))
        self.assertEqual(env,before);self.assertFalse(r['ledger_acceptance_supported'])
    def test_stale_month_unit_and_bytes_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:env,args=self.fixture(root)
        for mode in ('revision','month','expired','unit','raw'):
            a=deepcopy(args)
            if mode=='revision':a['expected_revision']='old'
            if mode=='month':a['now']=a['now'].replace(month=12)
            if mode=='expired':a['now']+=timedelta(seconds=120)
            if mode=='unit':a['execution_evidence']['units']['new']['retarget_acceptance_id']='other'
            if mode=='raw':a['execution_evidence']['files'][next(iter(a['execution_evidence']['files']))]='YQ=='
            r=build_retarget_continuation_proposal(env,**a)
            self.assertEqual(r['status'],'BLOCKED',(mode,r));self.assertNotIn('orders',r)
    def test_valid_high_price_chain_cannot_reset_or_rewrite_same_session(self):
        with tempfile.TemporaryDirectory() as root:env,args=self.fixture(root)
        for rename in (False,True):
            a=deepcopy(args);ev=a['execution_evidence'];inputs=ev['execution_inputs']['new']
            rawpath='new.raw.json';oldreceipt=inputs['receipt_paths'][0]
            raw=json.loads(base64.b64decode(ev['files'][rawpath]));row=raw['chart']['result'][0]
            row['meta']['regularMarketPrice']=100
            for key,value in [('open',100),('high',101),('low',99),('close',100)]:row['indicators']['quote'][0][key][0]=value
            rawbytes=json.dumps(raw).encode();rawhash=sha256(rawbytes).hexdigest()
            receipt=json.loads(base64.b64decode(ev['files'][oldreceipt]));receipt['raw_sha256']=rawhash
            receiptbytes=json.dumps(receipt).encode();receipthash=sha256(receiptbytes).hexdigest()
            receiptpath='replacement.receipt.json' if rename else oldreceipt
            if rename:del ev['files'][oldreceipt];del ev['source_hashes'][oldreceipt]
            ev['files'][rawpath]=base64.b64encode(rawbytes).decode();ev['files'][receiptpath]=base64.b64encode(receiptbytes).decode()
            pins={rawpath:rawhash,receiptpath:receipthash};inputs.update(receipt_paths=[receiptpath],source_hashes=pins,expected_tip_sha256=receipthash)
            ev['source_hashes'].update(pins)
            files={p:base64.b64decode(v) for p,v in ev['files'].items()}
            ref=read_intraday_execution_reference(root='.',frozen_files=files,now=a['now'],**inputs)
            ev['references']['new']=ref;ev['units']['new']['reference_source_hashes']=ref['source_hashes']
            self.assertEqual(replay_execution_evidence(ev)['new']['buy_limit'],'99')
            result=build_retarget_continuation_proposal(env,**a)
            self.assertEqual(result['status'],'BLOCKED',result)
            self.assertEqual(result['reason'],'SAME_SESSION_RECEIPT_CHAIN_RESET' if rename else 'SAME_SESSION_SOURCE_HISTORY_CHANGED')

    def test_empty_domain_after_actual_zero_target_sell_replay(self):
        with tempfile.TemporaryDirectory() as root:
            old,proposal,args=fixtures.FrozenRetargetTests().fixture(root)
            base=Path(root);si=args['sizing_inputs'];inputs=args['execution_inputs']['new']
            rawpath='new.raw.json';receiptpath=inputs['receipt_paths'][0]
            raw=json.loads((base/rawpath).read_bytes());row=raw['chart']['result'][0]
            row['meta']['regularMarketPrice']=100000
            for key,value in [('open',100000),('high',100001),('low',99999),('close',100000)]:row['indicators']['quote'][0][key][0]=value
            (base/rawpath).write_text(json.dumps(raw),encoding='utf-8')
            rawhash=sha256((base/rawpath).read_bytes()).hexdigest()
            receipt=json.loads((base/receiptpath).read_bytes());receipt['raw_sha256']=rawhash
            (base/receiptpath).write_text(json.dumps(receipt),encoding='utf-8')
            receipthash=sha256((base/receiptpath).read_bytes()).hexdigest()
            pins={rawpath:rawhash,receiptpath:receipthash}
            inputs.update(source_hashes=pins,expected_tip_sha256=receipthash)
            si['source_hashes'].update(pins)
            ref=read_intraday_execution_reference(root=root,now=args['now'],**inputs)
            si['execution_references']['new']=ref
            si['execution_unit_continuity']['new']['reference_source_hashes']=ref['source_hashes']
            proposal=build_intraday_retarget_sizing(old,now=args['now'],**si)
            self.assertEqual(proposal['status'],'READY',proposal)
            self.assertEqual(proposal['target_quantities'],{'new':0})
            self.assertEqual([o['side'] for o in proposal['orders']],['SELL'])
            env=accept_retarget_with_execution_evidence(old,proposal,**args)
            state=env['ledger'];order=next(iter(state['orders'].values()));now=args['now']
            event=dict(event_id='liquidate',kind='FILL',expected_revision=state['revision'],order_id=order['order_id'],recorded_at=now.isoformat(),executed_at=now.isoformat(),quantity=2,price='1500',fees='0')
            env['ledger']=apply_retarget_event(state,event,now=now)
        empty=dict(execution_inputs={},units={},source_hashes={},files={},references={})
        kwargs=dict(expected_revision=env['ledger']['revision'],execution_evidence=empty,now=now)
        result=build_retarget_continuation_proposal(env,**kwargs)
        self.assertEqual(result['status'],'READY',result);self.assertEqual(result['action'],'NO_ACTION')
        self.assertEqual(result['actual_cash'],'20200');self.assertEqual(result['orders'],[])
        self.assertIsNone(result['reference_valid_until']);self.assertFalse(result['execution_source_bytes_verified'])
        kwargs['now']-=timedelta(seconds=1)
        self.assertEqual(build_retarget_continuation_proposal(env,**kwargs)['reason'],'LEDGER_OBSERVATION_AFTER_NOW')

    def test_open_orders_reject(self):
        with tempfile.TemporaryDirectory() as root:
            old,p,args=fixtures.FrozenRetargetTests().fixture(root);env=accept_retarget_with_execution_evidence(old,p,**args)
            r=build_retarget_continuation_proposal(env,expected_revision=env['ledger']['revision'],execution_evidence=env['execution_evidence'],now=args['now'])
            self.assertEqual(r['reason'],'OPEN_ORDERS_OR_RESERVES')

if __name__=='__main__':unittest.main()
