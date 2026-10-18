from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_first_period_same_flow_nav_comparison_20261003 as m


def fixture():
    refs={role:dict(path='synthetic/'+role,sha256=(str(i%10)*64)) for i,role in enumerate(m.PINS)}
    flags=dict.fromkeys(('orders_executed','point_in_time_verified','promotion_allowed'),False)
    d={}
    for role,schema in [('candidate','FIRST_PERIOD_CASH_BUY_HOLD_PUBLICATION_V1'),('incumbent','FIRST_PERIOD_INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V2')]:
        d[role+'_accounts']=dict(source_hashes={},**flags)
        d[role+'_publication']=dict(schema=schema,status='PUBLISHED_CONDITIONAL_PRICE_ONLY_PATHS' if role=='candidate' else 'PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS',account_reference=refs[role+'_accounts'],source_hashes={},**flags)
    d['incumbent_audit']=dict(schema='FIRST_PERIOD_INCUMBENT_CASH_FLOW_INDEPENDENT_READBACK_V1',status='PASS',accounts_reference=refs['incumbent_accounts'],publication_reference=refs['incumbent_publication'],reader_sha256=refs['incumbent_reader']['sha256'],source_hashes={refs[r]['path']:refs[r]['sha256'] for r in ('incumbent_reader','incumbent_accounts','incumbent_publication')},counts=dict(paths=2,daily=212,decisions=12,mappings=8),**dict.fromkeys(('formal_admission','point_in_time_verified','promotion_allowed','production_functions_called','old_experiments_reexecuted'),False))
    d['candidate_review_report']=' '.join(refs[r]['sha256'] for r in ('candidate_accounts','candidate_publication','candidate_reader')).encode()
    d['candidate_reader']=' '.join(refs[r]['sha256'] for r in ('candidate_accounts','candidate_publication')).encode()
    d['currency_manifest']=dict(schema='FUND_CURRENCY_ISSUER_LISTING_CAPTURE_V1',fund_code='012922',currency='CNY',source_reference=refs['currency_html'],**dict.fromkeys(('nav_dataset_currency_binding_certified','historical_2023_class_continuity_verified','fx_rates_supplied','point_in_time_verified','promotion_allowed','subscription_terms_verified'),False))
    return d,refs


class Tests(unittest.TestCase):
    def test_metadata_crosslinks_exact_scope_and_authority(self):
        d,r=fixture();m.validate_documents(d,r)
        for mode in ('audit','reader','count','permission','review'):
            bad=deepcopy(d)
            if mode=='audit':bad['incumbent_audit']['accounts_reference']['sha256']='f'*64
            elif mode=='reader':bad['incumbent_audit']['reader_sha256']='f'*64
            elif mode=='count':bad['incumbent_audit']['counts']['paths']=True
            elif mode=='permission':bad['currency_manifest']['fx_rates_supplied']=True
            else:bad['candidate_review_report']=b'no attestation'
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.validate_documents(bad,r)

    def test_private_compilation_exact_bytes_no_shared_callable(self):
        metric=b'x=7'
        core=("from backtest import ndx_cash_fork_reference_window_research as window\nREFERENCE_METRICS_SOURCE_SHA256='"+m.sha(metric)+"'\ndef compare_first_period_paths(): return window.x\n").encode()
        blobs=dict(core=core,metrics=metric);refs={k:dict(path=k+'.py',sha256=m.sha(v)) for k,v in blobs.items()}
        names=('backtest.ndx_first_period_same_flow_comparison_research','backtest.ndx_cash_fork_reference_window_research')
        with patch.dict(sys.modules):
            for n in names:sys.modules.pop(n,None)
            compare=m.private_compare(blobs,refs);self.assertEqual(compare(),7)
            with self.assertRaises(ValueError):m.private_compare(dict(core=core+b' ',metrics=metric),refs)
            sys.modules[names[1]]=object()
            with self.assertRaisesRegex(ValueError,'Cached'):m.private_compare(blobs,refs)

    def test_execute_and_existing_namespace_fail_before_io(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No IO')):
            with self.assertRaises(ValueError):m.run()
        with tempfile.TemporaryDirectory() as td,patch.object(m,'OUTPUT',Path(td)):
            with self.assertRaisesRegex(ValueError,'no retry'):m.run(execute=True)

    def test_failure_persists_without_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);out=root/'out';pins={}
            for role in ('candidate_accounts','candidate_publication','incumbent_accounts','incumbent_publication'):
                folder=root/role.split('_')[0];folder.mkdir(exist_ok=True)
                name='accounts.json' if role.endswith('accounts') else 'publication.json'
                path=folder/name;path.write_bytes(b'{}');(folder/'started.json').write_bytes(b'{}')
                pins[role]=(str(path),m.sha(b'{}'))
            path=root/'benchmark.json';path.write_bytes(b'{}');pins['benchmark']=(str(path),m.sha(b'{}'))
            with patch.object(m,'PINS',pins),patch.object(m,'OUTPUT',out),patch.object(m,'guard'),patch.object(m,'validate_documents'),patch.object(m,'private_compare',return_value=lambda **k: (_ for _ in ()).throw(ValueError('synthetic failure'))):
                with self.assertRaisesRegex(ValueError,'synthetic failure'):m.run(execute=True)
                self.assertTrue((out/'started.json').exists());self.assertTrue((out/'failure.json').exists())
                with self.assertRaisesRegex(ValueError,'no retry'):m.run(execute=True)

if __name__=='__main__':unittest.main()
