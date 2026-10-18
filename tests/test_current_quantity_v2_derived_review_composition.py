"""Explicit derived execution review, shared RSS, and source-free acceptance."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_paper_ledger import digest
from data.current_quantity_v2_monthly_composition import create_services
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from test_current_quantity_v2_monthly_composition import config_fixture
from test_current_quantity_v2_bounded_unit_review import feed


class DerivedCompositionTests(unittest.TestCase):
    def test_actual_derived_capture_shared_feed_accept_and_retry(self):
        with TemporaryDirectory() as folder:
            root,h,paper,state,clock,source=config_fixture(folder);calls=[]
            chainpath='baseline/chain.json';reviewpath='baseline/review.json'
            review=dict(schema='EXPLICIT_PAPER_RIGHTS_BASELINE_V1',account_id=state['ledger']['account_id'],state_revision=state['ledger']['revision'],
                chain_sha256=digest(state),pending_rights=[],reviewed_at=clock[0].isoformat(),source_references=['baseline/explicit.txt'])
            files={chainpath:canonical(state),reviewpath:canonical(review),'baseline/explicit.txt':b'explicit synthetic baseline'}
            baseline=dict(files=files,source_hashes={p:sha256(v).hexdigest() for p,v in files.items()},documents=dict(chain=chainpath,review=reviewpath))
            def daily(ticker,start,end):
                calls.append(ticker)
                chart=dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),
                    timestamp=[int(start.timestamp()),int(end.timestamp())],indicators={'quote':[dict(open=[1,1],high=[1,1],low=[1,1],close=[1,1],volume=[1,1])]},events={})
                return dict(status=200,body=canonical({'chart':{'result':[chart],'error':None}}))
            def rss():calls.append('RSS');return dict(status=200,body=feed())
            actions=PaperActionEvidenceSources(fetch=daily,rss_fetch=rss,clock=lambda:clock[0])
            def quote(ticker):
                value=json.loads(source.fetch(ticker));value['chart']['result'][0]['meta']['regularMarketTime']=int(clock[0].timestamp());return canonical(value)
            services=create_services(root=root,paper_service=paper,storage_root=Path(folder)/'monthly',config_path='config.json',config_sha256=h,
                fetch=quote,rss_fetch=lambda:self.fail('second RSS forbidden'),execution_review_mode='DERIVED_PAPER_BOUNDED',
                action_evidence_reader=actions,baseline_reader=lambda _:deepcopy(baseline))
            self.assertEqual(calls,[])
            aid=state['ledger']['account_id'];rev=state['ledger']['revision']
            selected=services['research'].generate(account_id=aid,expected_revision=rev)
            blobs=Path(folder)/'monthly'/'captures'/'blobs';blobs.mkdir(parents=True)
            for name,h in state['ledger']['acceptance']['proposal']['causal_inputs']['execution_references']['A']['source_hashes'].items():(blobs/h).write_bytes((root/name).read_bytes())
            p=services['paper'].monthly_preview(account_id=aid,decision_id=selected['decision_id'],expected_revision=rev)
            self.assertEqual(calls.count('RSS'),1);captured=deepcopy(calls)
            # Frozen account proof must not depend on the action collector's current mutable cache.
            actions._saved=None;clock[0]+=timedelta(seconds=1)
            accepted=services['paper'].accept_monthly_retarget(account_id=aid,proposal_id=p['proposal_id'],operation_id='derived-month',expected_revision=rev)
            self.assertEqual(calls,captured);self.assertEqual(accepted['account_id'],aid)
            current=paper.store.read(aid);buy=next(o for o in current['ledger']['orders'].values() if o['side']=='BUY')
            paper.store.record_event(account_id=aid,event=dict(type='FILL',event_id='partial',order_id=buy['order_id'],expected_revision=current['ledger']['revision'],quantity=1,price=buy['limit_price'],fees='1/10',executed_at=clock[0].isoformat()),clock=lambda:clock[0])
            current=paper.store.read(aid)
            for oid,o in list(current['ledger']['orders'].items()):
                if not o['closed']:current=paper.store.record_event(account_id=aid,event=dict(type='CANCEL',event_id='cancel-'+oid,order_id=oid,expected_revision=current['ledger']['revision'],cancelled_at=clock[0].isoformat()),clock=lambda:clock[0])
            clock[0]+=timedelta(seconds=1)
            daily=services['paper'].continuation_preview(account_id=aid,expected_revision=current['ledger']['revision'])
            self.assertEqual(calls.count('RSS'),2);self.assertEqual(daily['recorded_fees'],current['ledger']['recorded_fees'])
            request=dict(account_id=aid,proposal_id=daily['proposal_id'],operation_id='derived-daily',expected_revision=current['ledger']['revision'])
            result=services['paper'].accept_continuation(**request);captured=deepcopy(calls)
            services['continuation']['bridge']._proposals.clear();services['monthly']['bridge']._proposals.clear();clock[0]+=timedelta(days=90)
            self.assertEqual(services['paper'].accept_continuation(**request),result)
            accepted=services['paper'].account(account_id=aid)
            self.assertEqual(services['paper'].accept_monthly_retarget(account_id=aid,proposal_id=p['proposal_id'],operation_id='derived-month',expected_revision=rev),accepted)
            self.assertEqual(calls,captured)

    def test_invalid_mode_only_disables_optional_monthly(self):
        with TemporaryDirectory() as folder:
            root,h,paper,_,_,_=config_fixture(folder)
            result=create_services(root=root,paper_service=paper,storage_root=Path(folder)/'never',config_path='config.json',config_sha256=h,execution_review_mode='INVALID')
            self.assertIs(result['paper'],paper);self.assertFalse(result['configured']);self.assertFalse((Path(folder)/'never').exists())
            self.assertEqual(result['research'].current(account_id='a')['reason'],'INVALID_MONTHLY_CONFIGURATION')

if __name__=='__main__':unittest.main()
