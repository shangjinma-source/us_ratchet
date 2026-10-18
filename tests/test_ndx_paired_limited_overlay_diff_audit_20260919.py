from copy import deepcopy
import unittest
from scripts import ndx_paired_limited_overlay_diff_audit_20260919 as audit
from backtest import ndx_corrected_delta_paired_overlay_limited_research as merger
from test_ndx_corrected_delta_paired_overlay_research import fixture


def case():
    parent,row=fixture()
    row['lineage']=dict(checkpoint_path='task.json',checkpoint_sha256='sha',complete_index_path=str(audit.INDEX),complete_index_sha256=audit.INDEX_SHA,
        independent_audit_path=str(audit.AUDIT),independent_audit_sha256=audit.AUDIT_SHA)
    output=merger.extend_delta_paired_overlay(parent=parent,replacements=[row],expected_tasks=[row['task']])
    source=dict(original={'task':row['task']},result={k:row[k] for k in ('result','original_result','historical_loader_provenance_gaps')},_path='task.json',_sha='sha')
    return parent,output,{row['task']['job_id']:source}


class DiffTests(unittest.TestCase):
    def test_exact_full_diff(self):
        p,o,r=case();before=deepcopy((p,o,r))
        self.assertEqual(audit.verify_record_changes(p,o,r),dict(record_count=4,paired_replaced=1,unchanged_count=3,available=2,pending=2))
        self.assertEqual((p,o,r),before)

    def test_mutations_to_untouched_economic_or_lineage_fields_rejected(self):
        for fault in ('untouched','paired_risk','lineage','audit_binding','extra_lineage','pending_result','order','count'):
            p,o,r=case()
            if fault=='untouched':o['records'][3]['result']['unchanged']=False
            elif fault=='paired_risk':o['records'][0]['result']['risk_chain_top1_max']=.9
            elif fault=='lineage':o['records'][0]['lineage']['completed_delta_paired']['checkpoint_sha256']='wrong'
            elif fault=='audit_binding':o['records'][0]['lineage']['completed_delta_paired']['independent_audit_sha256']='wrong'
            elif fault=='extra_lineage':o['records'][0]['lineage']['completed_delta_paired']['invented']=True
            elif fault=='pending_result':o['records'][2]['result']={}
            elif fault=='order':o['records'].reverse()
            else:o['available_count']+=1
            with self.assertRaises(ValueError,msg=fault):audit.verify_record_changes(p,o,r)

    def test_missing_date_replacement_rejected(self):
        p,o,r=case()
        with self.assertRaises(ValueError):audit.verify_record_changes(p,o,{})


if __name__=='__main__':unittest.main()
