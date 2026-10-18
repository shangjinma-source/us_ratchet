from math import comb
from datetime import date,timedelta
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import bulk_all_k_plan_20261003 as module


def args(count=76):
    return dict(groups=[(f'I{i:03d}',[f'S{i:03d}']+(['CLASS2'] if i==0 else [])) for i in range(count)],
        panel_reference={'path':str(module.ROOT/'synthetic_panel.json'),'sha256':'a'*64},
        panel_audit_reference={'path':str(module.ROOT/'synthetic_audit.md'),'sha256':'b'*64},
        decision_cutoff='2026-09-21',parameters=module.PARAMETERS.copy(),
        fitter_source_hashes={str(module.ROOT/'synthetic_source.py'):'c'*64},previous_target_weights=None,shard_size=1000)


class LazyTests(unittest.TestCase):
    def test_wrapper_ticker_columns_are_not_sid_columns(self):
        settings=args();records=[]
        for issuer,sids in settings['groups']:
            for sid in sids:records.append({'security_id':sid,'issuer_id':issuer,'ticker':'T_'+sid,'risk_chain':'saved'})
        records.sort(key=lambda row:row['security_id']);columns=list(records[0]);tickers=sorted(row['ticker'] for row in records)
        days=[];day=date(2026,9,21)
        while len(days)<126:
            if day.weekday()<5:days.append(day.isoformat()+'T00:00:00')
            day-=timedelta(days=1)
        days.reverse()
        inner={'schema':'LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1','universe':{
            'type':'dataframe','index_kind':'RangeIndex','columns':columns,'data':[[row[k] for k in columns] for row in records],
            'index':list(range(77)),'dtypes':['object']*len(columns)},
            'returns':{'type':'dataframe','index_kind':'DatetimeIndex','columns':tickers,'index':days,'dtypes':['float64']*77,'data':[[0.01]*77 for _ in days]},
            'cutoff':'2026-09-21','panel_content_sha256':'e'*64,'observed_provenance_and_missing':[],
            **dict.fromkeys(('point_in_time_verified','legal_training_input_admitted','promotion_allowed','fit_performed'),False)}
        panel={'schema':'BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1','panel':inner,'source_hashes':{},
            **dict.fromkeys(('point_in_time_verified','legal_training_input_admitted','promotion_allowed','fit_performed'),False)}
        refs={'panel':settings['panel_reference'],'audit':settings['panel_audit_reference']}
        sources={str(module.ROOT/f'synthetic_{i}.py'):'c'*64 for i in range(25)}
        docs={'panel':panel,'publication':{'panel_reference':refs['panel'],'source_hashes':{},'status':'PUBLISHED_CONDITIONAL_PANEL_ONLY'},
            'old_plan':{'plan':{'context':{'parameters':module.PARAMETERS,'weight_specs':list(module.contracts.WEIGHT_SPECS),'previous_target_weights':None},'fitter_source_hashes':sources}}}
        with patch.object(module,'prepare_lazy_plan',return_value={'synthetic_only':True}) as prepare:
            result=module.assemble(docs,refs)
            self.assertEqual(result['conditional_security_count'],77)
            self.assertEqual(sum(len(sids) for _,sids in prepare.call_args.kwargs['groups']),77)
        for mutate in (lambda f:f.update(columns=[row['security_id'] for row in records]),
                       lambda f:f['data'][0].__setitem__(0,True),lambda f:f['data'][0].pop(),
                       lambda f:f['dtypes'].__setitem__(0,'object')):
            broken=deepcopy(docs);mutate(broken['panel']['panel']['returns'])
            with patch.object(module,'prepare_lazy_plan',side_effect=AssertionError('must reject first')):
                with self.assertRaises(ValueError):module.assemble(broken,refs)

    def test_source_map_cannot_shadow_loaded_code(self):
        path=next(iter(module.LOADED))
        with self.assertRaisesRegex(ValueError,'hash conflict'):module.guard({path:'0'*64})

    def test_large_exact_polynomial_allk_without_any_enumeration(self):
        with patch.object(module.contracts,'prepare_issuer_shards',side_effect=AssertionError('eager called')),patch.object(module.indexing.IssuerCombinationIndex,'unrank',side_effect=AssertionError('enumerated')):
            plan=module.prepare_lazy_plan(**args())
        self.assertEqual(plan['all_k_combination_count'],3*2**75-1)
        self.assertEqual(len(plan['cardinalities']),76)
        for row in plan['cardinalities']:
            k=row['k'];expected=(comb(75,k) if k<=75 else 0)+2*comb(75,k-1)
            self.assertEqual(row['combination_count'],expected)
        self.assertEqual(plan['necessary_bound_excluded_combination_count']+plan['planned_combination_count'],plan['all_k_combination_count'])
        self.assertTrue(all(row['necessary_bound_certificates'] for row in plan['cardinalities'][20:]))
        self.assertNotIn('shards',plan)

    def test_large_rank_slice_exact_integer_and_page_boundaries(self):
        plan=module.prepare_lazy_plan(**args());row=plan['cardinalities'][19]
        start=(2**53+1234)//1000+1
        page=module.get_shard_slice(plan,k=20,shard_start=start,shard_stop=start+2)
        self.assertEqual(page[0]['start'],start*1000)
        self.assertEqual(page[0]['stop'],page[1]['start'])
        self.assertEqual(page[0]['ordinal'],row['first_global_shard_ordinal']+start)
        self.assertEqual(page[0]['first_global_planned_task_ordinal'],3*(row['first_global_planned_combination_ordinal']+start*1000))
        last=module.get_shard_slice(plan,k=20,shard_start=row['planned_shard_count']-1,shard_stop=row['planned_shard_count'])[0]
        self.assertEqual(last['stop'],row['combination_count'])
        for kwargs in (dict(k=True,shard_start=0,shard_stop=1),dict(k=20,shard_start=False,shard_stop=1),
                       dict(k=20,shard_start=0,shard_stop=1001),dict(k=20,shard_start=0,shard_stop=row['planned_shard_count']+1)):
            with self.assertRaises(ValueError):module.get_shard_slice(plan,**kwargs)

    def test_small_pages_and_source_identity_change(self):
        settings=args(5);settings['shard_size']=2;plan=module.prepare_lazy_plan(**settings)
        card=plan['cardinalities'][3];page=module.get_shard_slice(plan,k=4,shard_start=0,shard_stop=card['planned_shard_count'])
        self.assertEqual(sum(row['combination_count'] for row in page),card['combination_count'])
        self.assertTrue(all(a['stop']==b['start'] for a,b in zip(page,page[1:])))
        settings['fitter_source_hashes'][str(module.ROOT/'synthetic_source.py')]='d'*64
        self.assertNotEqual(module.prepare_lazy_plan(**settings)['plan_id'],plan['plan_id'])
        plan['completed_canonical_task_count']=False
        with self.assertRaises(ValueError):module.get_shard_slice(plan,k=4,shard_start=0,shard_stop=1)

    def test_parameter_bool_and_existing_output(self):
        settings=args(5);settings['parameters']['fit_days']=True
        with self.assertRaises(ValueError):module.prepare_lazy_plan(**settings)
        with tempfile.TemporaryDirectory() as temporary,patch.object(module,'OUTPUT',Path(temporary)):
            with self.assertRaisesRegex(ValueError,'exists'):module.run()


if __name__=='__main__':unittest.main()
