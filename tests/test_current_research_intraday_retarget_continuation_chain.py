import base64
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import tempfile
import unittest
import test_current_research_intraday_retarget_continuation as fixtures
from data.current_research_intraday_execution_reference import read_intraday_execution_reference
from data.current_research_intraday_retarget_continuation_chain import (
    build_retarget_chain_proposal,accept_retarget_chain_proposal,
    apply_retarget_chain_event,review_retarget_continuation_chain)

class ChainTests(unittest.TestCase):
    def append_quote(self,evidence,now,price,low):
        ev=deepcopy(evidence);inp=ev['execution_inputs']['new'];seq=len(inp['receipt_paths'])+1
        previous=inp['expected_tip_sha256'];first=json.loads(base64.b64decode(ev['files'][inp['receipt_paths'][0]]))
        raw=json.loads(base64.b64decode(ev['files'][first['raw_path']]));row=raw['chart']['result'][0];stamp=int(now.timestamp())
        row['meta'].update(regularMarketPrice=price,regularMarketTime=stamp)
        row['timestamp']=[stamp-60,stamp,stamp+1]
        for key,value in [('open',price),('high',price+1),('low',low),('close',price)]:row['indicators']['quote'][0][key][0]=value
        rp=f'new-{seq}.raw.json';cp=f'new-{seq}.receipt.json';rawbytes=json.dumps(raw).encode();rh=sha256(rawbytes).hexdigest()
        receipt=dict(first,sequence=seq,previous_receipt_sha256=previous,raw_path=rp,raw_sha256=rh,captured_at=now.isoformat())
        cb=json.dumps(receipt).encode();ch=sha256(cb).hexdigest()
        for path,body,digest in [(rp,rawbytes,rh),(cp,cb,ch)]:
            ev['files'][path]=base64.b64encode(body).decode();ev['source_hashes'][path]=digest;inp['source_hashes'][path]=digest
        inp['receipt_paths'].append(cp);inp['expected_tip_sha256']=ch
        files={p:base64.b64decode(v) for p,v in ev['files'].items()}
        ref=read_intraday_execution_reference(root='.',frozen_files=files,now=now,**inp)
        ev['references']['new']=ref;unit=ev['units']['new'];unit['reference_source_hashes']=ref['source_hashes'];unit['covered_through']=now.isoformat();unit['reviewed_asof']=now.isoformat()
        return ev
    def fixture(self):
        with tempfile.TemporaryDirectory() as root:env,args=fixtures.ContinuationTests().fixture(root)
        return env,args['execution_evidence'],args['now']
    def accept(self,state,evidence,now,oid):
        ledger=state['ledger'];p=build_retarget_chain_proposal(state,expected_revision=ledger['revision'],execution_evidence=evidence,now=now)
        self.assertEqual(p['status'],'READY',p)
        args=dict(operation_id=oid,expected_revision=ledger['revision'],execution_evidence=evidence,now=now)
        return accept_retarget_chain_proposal(state,p,**args),p,args
    def event(self,state,kind,now,**fields):
        s=state['ledger'];o=next(iter(s['orders'].values()))
        event=dict(event_id='chain-event-'+str(len(s['events'])),kind=kind,expected_revision=s['revision'],order_id=o['order_id'],recorded_at=now.isoformat(),**fields)
        return apply_retarget_chain_event(state,event,now=now),event
    def test_two_cycles_keep_money_target_and_latest_cap_chain(self):
        env,initial,now=self.fixture();e1=self.append_quote(initial,now+timedelta(minutes=1),39,38)
        chain,p,a=self.accept(env,e1,now+timedelta(minutes=1),'accept-1')
        self.assertEqual(next(iter(chain['ledger']['orders'].values()))['quantity'],405)
        t=now+timedelta(minutes=1,seconds=1)
        chain,fill=self.event(chain,'FILL',t,quantity=100,price='37',fees='1',executed_at=t.isoformat())
        t+=timedelta(seconds=1);chain,_=self.event(chain,'CANCEL',t,cancelled_at=t.isoformat())
        self.assertEqual(chain['ledger']['cash'],'12599');self.assertEqual(chain['ledger']['shares']['new'],200)
        branch=self.append_quote(initial,now+timedelta(minutes=2),50,49)
        rejected=build_retarget_chain_proposal(chain,expected_revision=chain['ledger']['revision'],execution_evidence=branch,now=now+timedelta(minutes=2))
        self.assertEqual(rejected['status'],'BLOCKED');self.assertIn('SAME_SESSION',rejected['reason'])
        e2=self.append_quote(e1,now+timedelta(minutes=2),50,49)
        chain,p2,a2=self.accept(chain,e2,now+timedelta(minutes=2),'accept-2')
        order=next(iter(chain['ledger']['orders'].values()));self.assertEqual(order['quantity'],305);self.assertEqual(order['limit_price'],'38')
        # Manual fill after quote acceptance deadline remains within the frozen DAY session.
        t=now+timedelta(minutes=5)
        chain,last=self.event(chain,'FILL',t,quantity=305,price='38',fees='0',executed_at=t.isoformat())
        self.assertEqual(chain['ledger']['cash'],'1009');self.assertEqual(chain['ledger']['fees'],'1')
        self.assertEqual(chain['ledger']['shares']['new'],505);self.assertEqual(chain['ledger']['target_quantities'],{'new':505})
        self.assertEqual(review_retarget_continuation_chain(chain),chain)
        self.assertEqual(apply_retarget_chain_event(chain,last,now=t+timedelta(days=1)),chain)
        self.assertEqual(accept_retarget_chain_proposal(chain,p,**dict(a,now=t+timedelta(days=1))),chain)
        e3=self.append_quote(e2,now+timedelta(minutes=6),30,29)
        done=build_retarget_chain_proposal(chain,expected_revision=chain['ledger']['revision'],execution_evidence=e3,now=now+timedelta(minutes=6))
        self.assertEqual(done['action'],'NO_ACTION');self.assertEqual(done['target_quantities'],{'new':505})
        with self.assertRaisesRegex(ValueError,'CURRENT_CONTINUATION_NOT_ACCEPTABLE'):
            accept_retarget_chain_proposal(chain,done,operation_id='no-action',expected_revision=chain['ledger']['revision'],execution_evidence=e3,now=now+timedelta(minutes=6))
    def test_expired_stale_and_tamper_rejected(self):
        env,e,now=self.fixture();e=self.append_quote(e,now+timedelta(minutes=1),39,38)
        chain,p,args=self.accept(env,e,now+timedelta(minutes=1),'a')
        self.assertTrue(p['ledger_acceptance_supported'])
        with self.assertRaisesRegex(ValueError,'DUPLICATE_OPERATION_ID'):
            accept_retarget_chain_proposal(env,p,**dict(args,operation_id=env['ledger']['retarget_acceptance']['operation_id']))
        for altered in (dict(args,expected_revision='old'),dict(args,now=now+timedelta(minutes=3))):
            with self.assertRaises(ValueError):accept_retarget_chain_proposal(env,p,**altered)
        bad=deepcopy(chain);bad['ledger']['cash']='999999'
        with self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):review_retarget_continuation_chain(bad)
        bad=deepcopy(chain);bad['operations'][0]['execution_evidence']['files'][next(iter(e['files']))]='YQ=='
        with self.assertRaises(ValueError):review_retarget_continuation_chain(bad)
        conflict=deepcopy(p);conflict['actual_cash']='1'
        with self.assertRaisesRegex(ValueError,'CONFLICTING_ACCEPT'):accept_retarget_chain_proposal(chain,conflict,**args)
    def test_cancelled_old_order_cannot_be_filled_after_reaccept(self):
        env,e,now=self.fixture();e1=self.append_quote(e,now+timedelta(minutes=1),39,38)
        chain,_,_=self.accept(env,e1,now+timedelta(minutes=1),'a1');oldorder=next(iter(chain['ledger']['orders']))
        t=now+timedelta(minutes=1,seconds=1);chain,_=self.event(chain,'CANCEL',t,cancelled_at=t.isoformat())
        e2=self.append_quote(e1,now+timedelta(minutes=2),39,38);chain,_,_=self.accept(chain,e2,now+timedelta(minutes=2),'a2')
        event=dict(event_id='late',kind='FILL',expected_revision=chain['ledger']['revision'],order_id=oldorder,recorded_at=(now+timedelta(minutes=2)).isoformat(),executed_at=t.isoformat(),quantity=1,price='37',fees='0')
        with self.assertRaisesRegex(ValueError,'UNKNOWN_ORDER'):apply_retarget_chain_event(chain,event,now=now+timedelta(minutes=2))

if __name__=='__main__':unittest.main()
