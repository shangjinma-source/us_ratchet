import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from data.roa_monthly_loader import RoaMonthlySelectionLoader
from scripts.research.prepare_roa_monthly_registration import prepare

class RegistrationTests(unittest.TestCase):
    def fixture(self, root):
        def save(name, value):
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
            raw=json.dumps(value).encode();p.write_bytes(raw)
            return {'path':name,'sha256':sha256(raw).hexdigest()}
        code=save('code.json',{})
        base=save('base.json',{'schema':'BASE'})
        original={'selection_id':'original','selection':[],'weights':{'sid':'1/10'},'securities':[], 'decision_date':'2026-11-30','effective_month':'2026-12'}
        source=save('bundle/selection.source.json',original)
        artifact={**original,'schema':'ROA_MONTH_SELECTION_V1','first_execution_session':'2026-12-01','source_hashes':{source['path']:source['sha256']}}
        artifact.pop('selection_id');artifact['selection_id']=sha256(json.dumps(artifact,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        runtime=save('package/runtime.json',artifact)
        save('package/registry.json',{'2026-12':runtime})
        receipt=save('package/receipt.json',{'status':'PREPARED_VERIFIED_NOT_REGISTERED','month':'2026-12','decision_date':'2026-11-30','selection_id':'original','registry_proposal':'package/registry.json','runtime_path':runtime['path'],'runtime_sha256':runtime['sha256']})
        config={'schema':'ROA_UNIFIED_PREPARATION_V34','base_v33':base,'source_pins':{code['path']:code['sha256']},'roa':{'monthly_selections':{},'base_input_root':'immutable','contract_hashes':{'contract':'keep'},'account_id':'never-write'}}
        configref=save('config.json',config)
        active=save('active.json',{'schema':'STRATEGY_SERVER_ACTIVE_V6','configuration_path':configref['path'],'configuration_sha256':configref['sha256']})
        args=dict(root=root,active_path=active['path'],active_sha256=active['sha256'],receipt_path=receipt['path'],receipt_sha256=receipt['sha256'],output_directory='release')
        return args,save,config,artifact
    def test_merge_and_rollback(self):
        with TemporaryDirectory() as d:
            root=Path(d);args,save,config,_=self.fixture(root);before=(root/'active.json').read_bytes()
            prepare(**args)
            actual=json.loads((root/'release/deploy-v34.json').read_bytes())
            self.assertEqual(actual['roa'].pop('monthly_selections')['2026-12']['path'],'package/runtime.json')
            config['roa'].pop('monthly_selections');self.assertEqual(actual,config)
            self.assertEqual((root/'active.json').read_bytes(),before)
            self.assertEqual((root/'release/rollback_active.json').read_bytes(),before)
            with self.assertRaisesRegex(ValueError,'OUTPUT_ALREADY_EXISTS'):prepare(**args)
    def test_source_changes_after_loader_rejected(self):
        with TemporaryDirectory() as d:
            root=Path(d);args,_,_,_=self.fixture(root)
            original=RoaMonthlySelectionLoader.__call__
            def changed(loader, session):
                result=original(loader,session)
                (root/'package/registry.json').write_text('{}')
                return result
            with patch.object(RoaMonthlySelectionLoader,'__call__',changed):
                with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED_DURING_PREPARATION'):prepare(**args)
            self.assertFalse((root/'release').exists())

    def test_active_race_keeps_exact_rollback(self):
        with TemporaryDirectory() as d:
            root=Path(d);args,_,_,_=self.fixture(root);before=(root/'active.json').read_bytes()
            original=Path.open
            def changed(path, *a, **kw):
                if path.name=='rollback_active.json':
                    (root/'active.json').write_bytes(b'other release')
                return original(path,*a,**kw)
            with patch.object(Path,'open',changed):
                with self.assertRaisesRegex(ValueError,'ACTIVE_CHANGED_DURING_PREPARATION'):prepare(**args)
            self.assertEqual((root/'release/rollback_active.json').read_bytes(),before)
            self.assertFalse((root/'release/preparation.json').exists())

    def test_fail_closed(self):
        for case in ('hash','source','conflict','schema','path'):
            with self.subTest(case=case),TemporaryDirectory() as d:
                root=Path(d);args,save,config,_=self.fixture(root)
                if case=='hash':args['active_sha256']='0'*64
                elif case=='source':(root/'code.json').write_text('changed')
                elif case=='path':args['receipt_path']='../outside.json'
                else:
                    if case=='conflict':config['roa']['monthly_selections']['2026-12']={}
                    else:config['schema']='OLD'
                    ref=save('config.json',config)
                    act=save('active.json',{'schema':'STRATEGY_SERVER_ACTIVE_V6','configuration_path':ref['path'],'configuration_sha256':ref['sha256']})
                    args['active_sha256']=act['sha256']
                with self.assertRaises(ValueError):prepare(**args)
                self.assertFalse((root/'release').exists())

if __name__=='__main__':unittest.main()
