import copy
import unittest
from backtest import ndx_conditional_panel_incremental_plan_research as m
from test_ndx_latest_conditional_all_k_refit_20260919 import panel,PARAMETERS

def fixture(n):
    value=panel(n)
    value['observed_provenance_and_missing']=[dict(ticker='T'+str(i),coordinate_assumption={'id':i},risk_assumption={'risk':i},channel_audit_assertion={'sha':str(i)}) for i in range(n)]
    value['panel_content_sha256']=m.core.panel_digest(value)
    return value

def build(a,b,oldparams=None,newparams=None,newsources=None):
    return m.build_incremental_plan(old_panel=a,new_panel=b,old_parameters=oldparams or PARAMETERS,new_parameters=newparams or PARAMETERS,
        old_fitter_sources={'fitter.py':'a'*64},new_fitter_sources=newsources or {'fitter.py':'a'*64})

class IncrementTests(unittest.TestCase):
    def test_dynamic_fourteen_counts_no_completed_reuse(self):
        result=build(fixture(9),fixture(14))
        self.assertEqual([result[k] for k in ('all_issuer_unique_combinations','necessary_bound_excluded_combinations','new_canonical_count','input_equivalent_old_count','new_input_count')],[16383,469,31828,764,31064])
        self.assertFalse(result['any_result_reused'])
        self.assertTrue(all(r['status']=='PENDING_OLD_OR_NEW' and not r['completed_old_result_verified'] for r in result['tasks']))

    def test_matrix_metadata_and_parameter_or_source_changes(self):
        a,b=fixture(4),fixture(5)
        bad=copy.deepcopy(b);bad['returns'].iloc[0,0]=.01;bad['panel_content_sha256']=m.core.panel_digest(bad)
        with self.assertRaises(ValueError):build(a,bad)
        bad=copy.deepcopy(b);bad['universe'].loc[0,'risk_chain']='changed';bad['panel_content_sha256']=m.core.panel_digest(bad)
        with self.assertRaises(ValueError):build(a,bad)
        changed=dict(PARAMETERS,shrinkage_intensity=.3)
        self.assertEqual(build(a,b,newparams=changed)['input_equivalent_old_count'],0)
        self.assertEqual(build(a,b,newsources={'fitter.py':'b'*64})['input_equivalent_old_count'],0)

    def test_bool_parameter_and_stale_panel_digest(self):
        with self.assertRaises(ValueError):build(fixture(4),fixture(5),newparams=dict(PARAMETERS,fit_days=True))
        a,b=fixture(4),fixture(5);b['universe'].loc[4,'risk_chain']='change'
        with self.assertRaises(ValueError):build(a,b)

    def test_exact_budget_duplicate_ticker_and_invalid_return(self):
        sources={'fitter.py':'a'*64}
        with self.assertRaises(ValueError):m.enumerate_inputs(fixture(20),PARAMETERS,sources)
        with self.assertRaises(ValueError):m.enumerate_inputs(fixture(5),PARAMETERS,sources,exact_limit=1)
        with self.assertRaises(ValueError):m.enumerate_inputs(fixture(4),PARAMETERS,sources,exact_limit=True)
        for mutate in ('ticker','return'):
            p=fixture(5)
            if mutate=='ticker':p['universe'].loc[4,'ticker']='T0'
            else:p['returns'].iloc[0,0]=-1.
            p['panel_content_sha256']=m.core.panel_digest(p)
            with self.assertRaises(ValueError):m.enumerate_inputs(p,PARAMETERS,sources)

if __name__=='__main__':unittest.main()
