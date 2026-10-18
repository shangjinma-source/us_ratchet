import copy,unittest
from backtest import ndx_dated_workbook_extension_tables_research as m
from backtest import ndx_dated_path_risk_display_research as paths
from backtest import ndx_saved_risk_chain_display_research as chains
from backtest import ndx_saved_risk_classification_coverage_research as classification
from test_ndx_dated_path_risk_display_research import fixture as path_fixture
from test_ndx_saved_risk_classification_coverage_research import fixture as classification_fixture

def fixture(missing=False):
    full=paths.project_saved_comparison(**path_fixture(missing=missing));chain=chains.project_chain_display(full)
    collection=paths.collect_projections([full]);row=collection['tasks'][0];shared=collection['shared_paths'];aggregates={}
    summary=dict(numerical_task_id=row['numerical_task_id'],k=4,weight_spec={'kind':'equal'})
    row['original_task_summary_row']=summary;chain['original_task_summary_row']=copy.deepcopy(summary);chain['projection_input_references']=copy.deepcopy(row['input_references']);chain['preserved_evidence_sidecars']=copy.deepcopy(row['preserved_evidence_sidecars'])
    for role in ('incumbent_integer','incumbent_continuous'):
        key=row['tracks'][role]['shared_path_id'];aggregates[key]=dict(identity=shared[key]['identity'],aggregation=chain['tracks'][role]);chain['tracks'][role]={'shared_aggregate_id':key}
    return row,chain,shared,aggregates

class Tests(unittest.TestCase):
    def test_six_paths_risk_exact_missing_cash(self):
        args=fixture();before=copy.deepcopy(args);out=m.project_task_display(*args)
        self.assertEqual(len(out['series']),6);self.assertTrue(all(len(s['slots'])==127 for s in out['series'].values()));self.assertEqual(args,before)
        self.assertEqual(out['risk_tracks']['candidate_integer'],args[1]['tracks']['candidate_integer'])
        self.assertEqual(out['series']['candidate_integer']['slots'][0]['display_value'],1.)
        missing=m.project_task_display(*fixture(True));self.assertTrue(all(x['display_value'] is None for x in missing['series']['candidate_integer']['slots']))
    def test_identity_calendar_and_underflow(self):
        for alter in ('task','calendar','shared'):
            args=list(fixture())
            if alter=='task':args[1]['numerical_task_id']='f'*64
            elif alter=='calendar':args[1]['calendar'].pop()
            else:next(iter(args[2].values()))['identity']['role']='wrong'
            with self.assertRaises(ValueError):m.project_task_display(*args)
        self.assertEqual(m.display_number('1e-400')['display_status'],'OUTSIDE_DISPLAY_PRECISION');self.assertIsNone(m.display_number('1e-400')['display_value']);self.assertEqual(m.display_number('0')['display_value'],0.)
    def test_classification_counts_original_rows(self):
        coverage=classification.summarize_saved_classification(**classification_fixture());out=m.project_classification(coverage)
        self.assertEqual(out['rows'],coverage['rows']);self.assertEqual(out['counts']['unknown_label_rows'],23)
        coverage['counts']['training_selected_security_count']=78
        with self.assertRaises(ValueError):m.project_classification(coverage)
    def test_packages_full_order_limits_and_last(self):
        rows=[dict(task_ordinal=i,numerical_task_id=('%064x'%i),data_row_count=7,estimated_bytes=5) for i in range(5)]
        out=m.plan_display_packages(rows,dict(max_rows_per_sheet=5,max_rows_per_package=15,max_estimated_bytes_per_package=100),expected_task_ids=[r['numerical_task_id'] for r in rows])
        self.assertEqual([p['data_page_row_counts'] for p in out['packages']],[[5,5,4],[5,5,4],[5,2]]);self.assertEqual(out['packages'][-1]['stop_task_ordinal'],5)
        rows[-1]['data_row_count']=16
        with self.assertRaises(ValueError):m.plan_display_packages(rows,dict(max_rows_per_sheet=5,max_rows_per_package=15,max_estimated_bytes_per_package=100),expected_task_ids=[r['numerical_task_id'] for r in rows])
    def test_false_sidecars_classification_and_complete_external_index(self):
        for alter in ('formal','sidecar','limits'):
            args=list(fixture())
            if alter=='formal':args[0]['formal_comparison_passed']=True
            elif alter=='sidecar':args[1]['preserved_evidence_sidecars']={}
            else:args[1]['limitations_preserved']={}
            with self.assertRaises(ValueError):m.project_task_display(*args)
        for alter in ('sid','label'):
            coverage=classification.summarize_saved_classification(**classification_fixture())
            if alter=='sid':coverage['rows'][1]['security_id']=coverage['rows'][0]['security_id']
            else:coverage['rows'][0]['saved_risk_chain']=None
            with self.assertRaises(ValueError):m.project_classification(coverage)
        row=dict(task_ordinal=0,numerical_task_id='1'*64,data_row_count=1,estimated_bytes=1)
        with self.assertRaises(ValueError):m.plan_display_packages([row],expected_task_ids=['1'*64,'2'*64])
        with self.assertRaises(ValueError):m.plan_display_packages([row],{},expected_task_ids=['1'*64])
if __name__=='__main__':unittest.main()
