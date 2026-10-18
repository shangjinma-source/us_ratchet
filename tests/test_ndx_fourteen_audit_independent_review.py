"""Independent all-combination and source-contract counterexamples, no fit."""
import copy
import itertools
import unittest
from unittest.mock import patch
from scripts import ndx_fourteen_incremental_independent_audit_20260919 as m


def fixture():
    rows=[dict(security_id='s'+str(i).zfill(2),ticker='T'+str(i),issuer_id='i'+str(i),risk_chain='r'+str(i)) for i in range(14)]
    def document(rows):
        return dict(cutoff='2026-09-17',universe=dict(columns=list(rows[0]),data=[list(r.values()) for r in rows]))
    entries=[]
    for k in range(4,15):
        for chosen in itertools.combinations(rows,k):
            for spec in ('equal_weight','constrained_fixed_shrinkage'):
                task=dict(cutoff='2026-09-17',selected={r['security_id']:{key:r[key] for key in ('ticker','issuer_id','risk_chain')} for r in chosen},holding_count=k,weight_spec=spec,parameters=dict(m.scalar.PARAMS),previous_target_weights=None)
                old=all(int(r['ticker'][1:])<9 for r in chosen);identifier=m.scalar.digest(task)
                entries.append(dict(task=task,task_id=identifier,result_reused=False,input_equivalent_to_old_task=old,completed_old_result_verified=old,completed_old_result_reference={'path':'old','sha256':'a'*64} if old else None,old_equivalent_task_id=identifier if old else None,status='OLD_INPUT_EQUIVALENT_RESULT_REFERENCE_VERIFIED_NOT_IMPORTED' if old else 'PENDING_OLD_OR_NEW'))
    return {'delta':{'tasks':entries}},document(rows),document(rows[:9])


class IndependentAuditReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan,cls.panel,cls.old=fixture()

    def test_exact_full_combination_set_and_old_new_partition(self):
        new,old=m.inspect_plan(self.plan,self.panel,self.old)
        self.assertEqual((len(new),len(old)),(31064,764))
        oldrow=next(r for r in self.plan['delta']['tasks'] if r['input_equivalent_to_old_task'])
        newrow=next(r for r in self.plan['delta']['tasks'] if not r['input_equivalent_to_old_task'])
        originals=copy.deepcopy([oldrow,newrow])
        try:
            for target,source in ((oldrow,originals[1]),(newrow,originals[0])):
                for field in ('input_equivalent_to_old_task','completed_old_result_verified','completed_old_result_reference','status'):
                    target[field]=source[field]
                target['old_equivalent_task_id']=target['task_id'] if target['input_equivalent_to_old_task'] else None
            with self.assertRaises(ValueError):m.inspect_plan(self.plan,self.panel,self.old)
        finally:
            for target,source in zip((oldrow,newrow),originals):target.clear();target.update(source)

    def test_resigned_selected_identity_and_parameters_cannot_replace_panel(self):
        row=next(r for r in self.plan['delta']['tasks'] if not r['input_equivalent_to_old_task']);original=copy.deepcopy(row)
        for field in ('issuer_id','ticker','risk_chain','parameters','previous','spec'):
            with self.subTest(field=field):
                try:
                    if field in ('issuer_id','ticker','risk_chain'):row['task']['selected'][next(iter(row['task']['selected']))][field]='fabricated'
                    elif field=='parameters':row['task']['parameters']['shrinkage_intensity']=.1
                    elif field=='previous':row['task']['previous_target_weights']={}
                    else:row['task']['weight_spec']='unknown'
                    row['task_id']=m.scalar.digest(row['task'])
                    with self.assertRaises(ValueError):m.inspect_plan(self.plan,self.panel,self.old)
                finally:row.clear();row.update(copy.deepcopy(original))

    def test_publication_cannot_upgrade_reuse_or_resign_deleted_source(self):
        value=dict(schema=m.SCHEMA,index_reference=dict(path='index',sha256='a'*64),old_result_imported_count=0,historical_expected_source_hashes={'required':'b'*64},archive_resolution={'verified':'bound'},**dict.fromkeys((*m.FALSE,'old_result_numerical_audit_repeated','solver_called','owner_check_result_called','constrained_projection_optimality_independently_verified','risk_chain_projection_metadata_independently_recomputed'),False))
        with patch.object(m,'build',return_value=value),patch.object(m.scalar,'exclusive_publish',side_effect=AssertionError('No publication')):
            m.verify(value)
            for field in ('old_result_imported_count','sources','extra'):
                bad=copy.deepcopy(value)
                if field=='sources':bad['historical_expected_source_hashes']={};bad['archive_resolution']={}
                elif field=='extra':bad['provider_identity_verified']=True
                else:bad[field]=764
                with self.assertRaises(ValueError):m.publish_verified('unused',bad)

    def test_projection_metadata_cannot_be_dropped_or_upgraded(self):
        # Isolate the full-field schema gate; scalar numeric checks run separately.
        task=self.plan['delta']['tasks'][0]['task']
        value=dict.fromkeys(m.RESULT_KEYS)
        value.update(anchor_policy='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED',numerical_projection='V3_CERTIFIED_RECOVERY_ORIGINAL_PROBE_CLOSURE',risk_chain_projection_relaxed=False,single_name_projection_relaxed=False,top3_projection_semantics_relaxed=False,projection_reconstruction_audit=dict(schema='ndx_projection_reconstruction_audit_v1',scope='NUMERICAL_PROJECTION_RECOVERY_NOT_ECONOMIC_QUALIFICATION',attempt_count=0,attempts=[],prior_results_reused=False,promotion_allowed=False))
        m.result_schema(value,task)
        for defect in ('drop','numeric_bool','policy','scope','extra'):
            bad=copy.deepcopy(value)
            if defect=='drop':bad.pop('risk_chain_projection_relaxed')
            elif defect=='numeric_bool':bad['risk_chain_projection_relaxed']=0
            elif defect=='policy':bad['anchor_policy']='ACTUAL_HOLDINGS'
            elif defect=='scope':bad['projection_reconstruction_audit']['scope']='ECONOMICALLY_QUALIFIED'
            else:bad['identity_verified']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.result_schema(bad,task)


if __name__=='__main__':unittest.main()
