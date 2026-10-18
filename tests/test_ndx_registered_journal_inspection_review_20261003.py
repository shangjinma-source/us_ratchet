from copy import deepcopy
import unittest
from backtest import ndx_registered_scoring_journal_inspection_research as reader
from test_ndx_registered_scoring_journal_inspection_research import fixture,resign


class Review(unittest.TestCase):
    def test_invalid_saved_assembly_is_validation_evidence_not_success(self):
        kwargs,_,rows=fixture()
        for value in (None,{'schema':'BAD_RETURN'}):
            changed=deepcopy(rows[:2]+rows[-1:]);changed[1]['payload']['assembled']=value
            changed[-1]['payload'].update(outcome='VALIDATION_FAILURE',failed_stage='START',error=dict(type='ValueError',message='invalid returned assembly',traceback='saved'))
            bad=deepcopy(kwargs);bad['journal_bytes']=resign(changed)
            out=reader.inspect_scoring_journal(**bad)
            self.assertEqual(out['status_counts'],{'VALIDATION_FAILURE':1})
            self.assertEqual(out['numerical_success_claim_count'],0)
            self.assertFalse(out['tasks'][0]['fit_dispatch_observed'])
        invalid=deepcopy(rows);invalid[1]['payload']['assembled']=None
        bad=deepcopy(kwargs);bad['journal_bytes']=resign(invalid)
        with self.assertRaises((ValueError,TypeError)):reader.inspect_scoring_journal(**bad)

    def test_failed_inspection_saved_before_validation_does_not_authorize_success(self):
        kwargs,_,rows=fixture();changed=deepcopy(rows)
        changed[-2]['payload']['inspection']={'status':'REJECTED','diagnostic':'original'}
        changed[-1]['payload'].update(outcome='VALIDATION_FAILURE',failed_stage='INSPECTION',error=dict(type='ValueError',message='inspection rejected',traceback='saved'))
        bad=deepcopy(kwargs);bad['journal_bytes']=resign(changed)
        out=reader.inspect_scoring_journal(**bad)
        self.assertEqual(out['numerical_success_claim_count'],0)
        self.assertTrue(out['whole_shard_terminal_evidence_complete'])
        changed[-1]=deepcopy(rows[-1]);bad['journal_bytes']=resign(changed)
        with self.assertRaises(ValueError):reader.inspect_scoring_journal(**bad)

    def test_partial_score_return_preserves_dispatch_uncertainty(self):
        kwargs,_,rows=fixture()
        kwargs['journal_bytes']=b''.join(reader.encode(row)+b'\n' for row in rows[:5])+b'{"unfinished_return"'
        out=reader.inspect_scoring_journal(**kwargs)
        self.assertEqual(out['unresolved_task_ids'],[kwargs['expected_jobs'][0]['job_id']])
        self.assertTrue(out['tasks'][0]['score_dispatch_observed'])
        self.assertFalse(out['whole_shard_terminal_evidence_complete'])
        self.assertFalse(out['automatic_retry_allowed']);self.assertFalse(out['bytes_truncated'])


if __name__=='__main__':unittest.main()
