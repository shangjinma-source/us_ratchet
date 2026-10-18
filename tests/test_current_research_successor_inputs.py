from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.current_research_successor_inputs import SuccessorInputLoader, REGISTRY_SCHEMA
from data.current_research_successor_service import CurrentResearchSuccessorService
from data.current_research_paper_service import CurrentResearchPaperService
from data.current_research_paper_store import ResearchPaperStore
from data.current_research_limit_plan import build_current_research_limit_plan
import test_current_research_monthly_plan as fixtures


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'q').write_bytes(b'explicit synthetic evidence')
        pins={'q':hashlib.sha256((self.root/'q').read_bytes()).hexdigest()}
        self.bundle=dict(account_id='a',revision='r',parent_plan_id='p',decision_date='2026-10-14',active_date='2026-10-15',
            calendar=['2026-10-14','2026-10-15'],source_hashes=pins,
            valuation_quotes=[dict(security_id='X',price='50',as_of='2026-10-14',price_basis='UNIT',source_references=['q'])],
            held_unit_continuity={'X':dict(from_date='2026-10-13',to_date='2026-10-14',price_basis='UNIT',status='NO_UNPROCESSED_ACTIONS',source_references=['q'])},
            market_session=fixtures.session('2026-10-15'),decision_session=fixtures.session('2026-10-14'),
            admission=dict(status='ACCEPTED_CONDITIONAL_RESEARCH_INPUT',reviewer='synthetic agent',reviewed_at='2026-10-14T17:00:00-04:00',evidence_references=['q'],limitations=['Synthetic; hashes do not establish market truth.']))
        self.loader=SuccessorInputLoader(root=self.root,registry_path='registry.json')

    def save(self,bundle=None,entries=None):
        bundle=deepcopy(self.bundle if bundle is None else bundle)
        raw=json.dumps(bundle,sort_keys=True).encode();key=hashlib.sha256(raw).hexdigest()
        path=key+'.json';(self.root/path).write_bytes(raw)
        entry=dict(bundle_path=path,sha256=key,**{k:bundle[k] for k in ('account_id','revision','parent_plan_id')})
        records={} if entries is None else entries
        records[key]=entry
        (self.root/'registry.json').write_text(json.dumps(dict(schema=REGISTRY_SCHEMA,entries=records)))
        return key,records

    def test_valid_and_tampered_source_or_bundle(self):
        key,_=self.save();self.assertEqual(self.loader(key),self.bundle)
        (self.root/'q').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.loader(key)
        (self.root/(key+'.json')).write_bytes(b'{}')
        with self.assertRaises(ValueError):self.loader(key)

    def test_path_escape_binding_and_unreviewed_refs(self):
        for path in ('../outside',str(self.root/'q')):
            key,entries=self.save();entries[key]['bundle_path']=path
            (self.root/'registry.json').write_text(json.dumps(dict(schema=REGISTRY_SCHEMA,entries=entries)))
            with self.assertRaises(ValueError):self.loader(key)
        key,entries=self.save();entries[key]['revision']='other'
        (self.root/'registry.json').write_text(json.dumps(dict(schema=REGISTRY_SCHEMA,entries=entries)))
        with self.assertRaises(ValueError):self.loader(key)
        for field in ('admission','quote_ref','continuity_ref'):
            b=deepcopy(self.bundle)
            if field=='admission':b.pop(field)
            elif field=='quote_ref':b['valuation_quotes'][0]['source_references']=['missing']
            else:b['held_unit_continuity']['X']['source_references']=[]
            key,_=self.save(b)
            with self.assertRaises(ValueError):self.loader(key)

    def test_symlink_escape(self):
        with TemporaryDirectory() as outside:
            target=Path(outside)/'q';target.write_bytes(b'evidence')
            try:(self.root/'link').symlink_to(target)
            except OSError:self.skipTest('Symlink privilege unavailable')
            b=deepcopy(self.bundle);b['source_hashes']['link']=hashlib.sha256(target.read_bytes()).hexdigest()
            key,_=self.save(b)
            with self.assertRaises(ValueError):self.loader(key)

    def test_discovery_absent_ambiguous_and_latest(self):
        with self.assertRaisesRegex(ValueError,'UNAVAILABLE'):self.loader.find_for_account('a','r','p')
        key,entries=self.save()
        self.assertEqual(self.loader.find_for_account('a','r','p')['input_id'],key)
        b=deepcopy(self.bundle);b['admission']['reviewer']='another'
        self.save(b,entries)
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):self.loader.find_for_account('a','r','p')
        b['decision_date']='2026-10-15';b['active_date']='2026-10-16';b['calendar']=['2026-10-15','2026-10-16']
        key,_=self.save(b,entries)
        self.assertEqual(self.loader.find_for_account('a','r','p')['input_id'],key)

    def test_full_loader_and_service_preview_no_search_or_writes(self):
        pins=self.bundle['source_hashes']
        plan=build_current_research_limit_plan(research_snapshot=dict(research_id='a'*24,as_of='2026-10-13',stocks=[dict(security_id='X',ticker='XXX')],source_hashes=pins,target_month='2026-10',market_session=fixtures.session('2026-10-14')),
            quotes=[dict(self.bundle['valuation_quotes'][0],as_of='2026-10-13',price_kind='DECLARED_DECIMAL_REFERENCE')],available_cash='100',shares={},account_revision='initial',decision_date='2026-10-13',active_date='2026-10-14',calendar=['2026-10-13','2026-10-14'],strategy_version='old',target_quantities={})
        base=CurrentResearchPaperService(root=self.root,directory=self.root/'paper',clock=lambda:datetime.fromisoformat('2026-10-14T17:00:00-04:00'))
        account='paper-'+plan['plan_id'][:24];store=ResearchPaperStore(base.directory);state=store.create(account,plan)
        self.bundle.update(account_id=account,revision=state['revision'],parent_plan_id=plan['plan_id'])
        key,_=self.save()
        service=CurrentResearchSuccessorService(base_service=base,input_provider=self.loader,search=lambda **_:self.fail('ROLL must not search'))
        discovered=service.available_input(account,state['revision']);self.assertEqual(discovered['input_id'],key)
        result=service.preview(account,key,state['revision']);self.assertEqual(result['route']['action'],'ROLL')
        self.assertTrue(service.preview(account,key,state['revision'])['cache_hit'])
        self.assertEqual(store.read(account),state)
        (self.root/'q').write_bytes(b'changed after cached preview')
        with self.assertRaises(ValueError):service.preview(account,key,state['revision'])
        with self.assertRaises(ValueError):service.activate(account,result['preview_id'],'activate',state['revision'])
        self.assertEqual(store.read(account),state)

if __name__=='__main__':unittest.main()
