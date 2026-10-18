"""Revision-independent explicit market configuration; no production inputs."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from data.current_quantity_v2_monthly_composition import create_services,MonthlyFileConfiguration
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_paper_ledger import digest
from test_current_quantity_v2_monthly_composition import config_fixture
from test_current_quantity_v2_bounded_unit_review import feed


def market_fixture(folder):
    root,h,paper,state,clock,source=config_fixture(folder)
    old=json.loads((root/'config.json').read_bytes());entry=old['training_entries'][0]
    market={k:deepcopy(entry[k]) for k in ('target_month','source_hashes','manifest_path','calendar_path','identities_path','held_bar_sources')}
    market['decision_date']=json.loads((root/entry['calendar_path']).read_bytes())['decision_date']
    raw=canonical(dict(schema='QUANTITY_V2_MONTHLY_SERVER_INPUTS_V2',market_entries=[market],account_reviews=[]));(root/'market.json').write_bytes(raw)
    return root,sha256(raw).hexdigest(),paper,state,clock,source


class MarketCompositionTests(unittest.TestCase):
    def test_market_binding_no_revision_and_old_month_refused(self):
        with TemporaryDirectory() as folder:
            root,h,paper,state,clock,_=market_fixture(folder)
            config=MonthlyFileConfiguration(root=root,path='market.json',sha256_value=h,clock=lambda:clock[0])
            first=config.market_reader(state);changed=deepcopy(state);changed['ledger']['revision']='new'
            self.assertEqual(first,config.market_reader(changed));self.assertNotIn('account_review_path',first)
            clock[0]=clock[0].replace(month=12)
            with self.assertRaisesRegex(ValueError,'MONTHLY_SOURCE_UNAVAILABLE'):config.market_reader(state)
            clock[0]=clock[0].replace(month=11)
            raw=json.loads((root/'market.json').read_bytes());raw['market_entries'][0]['decision_date']='2026-10-13';body=canonical(raw);(root/'market.json').write_bytes(body)
            config.sha256_value=sha256(body).hexdigest()
            with self.assertRaisesRegex(ValueError,'MONTHLY_SOURCE_UNAVAILABLE'):config.market_reader(state)

    def test_real_generate_derived_review_and_get_no_callbacks(self):
        with TemporaryDirectory() as folder:
            root,h,paper,state,clock,source=market_fixture(folder);calls=[]
            baselinefiles={'baseline/chain':canonical(state),'baseline/note':b'explicit synthetic baseline'}
            baselinefiles['baseline/review']=canonical(dict(schema='EXPLICIT_PAPER_RIGHTS_BASELINE_V1',account_id=state['ledger']['account_id'],state_revision=state['ledger']['revision'],chain_sha256=digest(state),pending_rights=[],reviewed_at=clock[0].isoformat(),source_references=['baseline/note']))
            baseline=dict(files=baselinefiles,source_hashes={p:sha256(v).hexdigest() for p,v in baselinefiles.items()},documents=dict(chain='baseline/chain',review='baseline/review'))
            def daily(ticker,start,end):
                calls.append(ticker);chart=dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),timestamp=[int(start.timestamp()),int(end.timestamp())],indicators={'quote':[dict(open=[1,1],high=[1,1],low=[1,1],close=[1,1],volume=[1,1])]},events={})
                return dict(status=200,body=canonical({'chart':{'result':[chart],'error':None}}))
            def rss():calls.append('RSS');return dict(status=200,body=feed())
            actions=PaperActionEvidenceSources(fetch=daily,rss_fetch=rss,clock=lambda:clock[0])
            services=create_services(root=root,paper_service=paper,storage_root=Path(folder)/'registered',config_path='market.json',config_sha256=h,execution_review_mode='DERIVED_PAPER_BOUNDED',action_evidence_reader=actions,baseline_reader=lambda _:deepcopy(baseline))
            self.assertEqual(calls,[]);self.assertFalse((Path(folder)/'registered').exists())
            aid=state['ledger']['account_id'];result=services['research'].generate(account_id=aid,expected_revision=state['ledger']['revision'])
            self.assertEqual(result['status'],'READY');self.assertEqual(calls.count('RSS'),1);self.assertEqual(paper.store.read(aid),state)
            def forbidden(*a,**k):raise AssertionError('GET must not compute/fetch')
            services['research'].training_reader=forbidden;actions.fetch=forbidden;actions.rss_fetch=forbidden
            with patch('subprocess.run',side_effect=forbidden):
                self.assertEqual(services['research'].current(account_id=aid)['decision_id'],result['decision_id'])
                self.assertEqual(services['research'].read(account_id=aid,registration_id=result['registration_id'])['decision_id'],result['decision_id'])

if __name__=='__main__':unittest.main()
