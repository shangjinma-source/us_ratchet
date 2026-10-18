from copy import deepcopy
from unittest.mock import patch
from pathlib import Path
import unittest
from scripts import ndx_dated_comparison_results_summary_independent_readback_20261003 as r
from backtest import ndx_dated_comparison_results_summary_research as producer
from test_ndx_dated_comparison_results_summary_research import fixture,saved

def case():
    a=fixture();a['task_summary_reference']=r.ref('task_summary')
    for i in (0,1,2):
        t=a['task_summary']['rows'][i];a['comparisons_by_task'][t['numerical_task_id']]=saved(t,first=i==0,missing=i==1,decision='NO_PLAN' if i==2 else 'FROZEN',execution=None if i==2 else 'REJECTED')
    return a,producer.summarize_comparisons(**a)

class Tests(unittest.TestCase):
    def test_independent_source_base_and_exact_union(self):
        bound={k:(p,h or 'a'*64) for k,(p,h) in r.BOUND.items()}
        readers={k:(p,h or 'b'*64) for k,(p,h) in r.READERS.items()}
        with patch.object(r,'BOUND',bound),patch.object(r,'READERS',readers):base=r.expected_producer_sources()
        self.assertEqual(len(base),12)
        self.assertEqual(base[str(r.CORE)],r.CORE_SHA)
        all_sources=dict(base);all_sources['comparison.json']='c'*64
        start={'source_hashes':deepcopy(base)};doc={'source_hashes':deepcopy(all_sources)};pub=deepcopy(doc)
        r.verify_source_tables(start,doc,pub,base,all_sources)
        for kind in ('empty','missing_core','missing_reader','extra','pub_extra'):
            s,d,p=deepcopy((start,doc,pub))
            if kind=='empty':s['source_hashes']={}
            elif kind=='missing_core':s['source_hashes'].pop(str(r.CORE))
            elif kind=='missing_reader':s['source_hashes'].pop(str(r.ROOT/readers['comparison'][0]))
            elif kind=='extra':d['source_hashes']['unverified.json']='d'*64
            else:p['source_hashes']['unverified.json']='d'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError):r.verify_source_tables(s,d,p,base,all_sources)

    def test_complete_projection_and_51_strata(self):
        a,tables=case();before=deepcopy(tables);r.verify_tables(tables,a['task_summary'],a['comparisons_by_task'])
        for i in range(3):
            task=a['task_summary']['rows'][i];e=a['comparisons_by_task'][task['numerical_task_id']]
            r.verify_row(tables['rows'][i],task,e['document'],e['audit'],dict(comparison_reference=e['document_reference'],independent_readback_reference=e['audit_reference']))
        self.assertEqual(tables,before)
    def test_every_metric_distance_target_and_missing_preserved(self):
        a,tables=case();task=a['task_summary']['rows'][1];e=a['comparisons_by_task'][task['numerical_task_id']];refs=dict(comparison_reference=e['document_reference'],independent_readback_reference=e['audit_reference'])
        for mutation in (lambda x:x['original_targets'][0].update(target_weight=.5),lambda x:x['tracks']['candidate_integer'].update(metrics={}),lambda x:x['nav_modes'][r.MODES[0]]['absolute_distance_comparisons']['continuous']['annualized_return'].update(candidate_minus_incumbent_distance={'exact':'1'}),lambda x:x['tracks']['incumbent_continuous']['metrics']['maximum_drawdown'].update(decimal='99'),lambda x:x['nav_modes'].pop(r.MODES[1])):
            row=deepcopy(tables['rows'][1]);mutation(row)
            with self.assertRaises(ValueError):r.verify_row(row,task,e['document'],e['audit'],refs)
    def test_domain_bool_reordering_and_missing_not_failed(self):
        for mutation in (lambda x:x.update(supplied_comparison_count=True),lambda x:x['rows'].reverse(),lambda x:x['rows'][3].update(status='FAILED'),lambda x:x['k_spec_coverage'][0].update(planned_task_count=31),lambda x:x.update(formal_comparison_passed=0)):
            a,tables=case();mutation(tables)
            with self.assertRaises(ValueError):r.verify_tables(tables,a['task_summary'],a['comparisons_by_task'])
    def test_pending_before_io(self):
        with patch.object(r,'SUMMARY_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):r.readback(execute=True)
            read.assert_not_called()

if __name__=='__main__':unittest.main()
