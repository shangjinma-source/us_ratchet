import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_latest_all_k_completed_audit_publish_v2_20260919 as m

class PublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=m.old.read(dict(path=str(m.old.PLAN),sha256=m.old.PLAN_SHA),{})
        cls.index=m.old.read(dict(path=str(m.old.PLAN.parent/'tasks/index_ada688df53945ee552c913ee2fdfc938c3fe58728af99b66e02b9921aa8d751c.json'),sha256='cf25ef3630d194dfd65092f4e3dd1ecb61dd9f0ce5c9ec974b8d046a4dbbef9c'),{})
        cls.value=json.loads((m.old.PLAN.parent/'completed_2_independent_audit.json').read_bytes())
        cls.value.update(schema=m.SCHEMA,numerical_reader_schema='LATEST_ALL_K_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V1')
    def test_actual_two_detail_contract_without_build_or_fit(self):
        m.validate_report(self.value,self.plan,self.index)
    def test_two_failures_preserve_canonical_order_after_sorted_json(self):
        value=copy.deepcopy(self.value);row=value['details'][0]
        for key in ('MAX_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT'):row['five_risk_checks'][key]=False
        row.update(risk_pass=False,risk_failures=['MAX_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT'])
        value.update(risk_pass_count=1,risk_fail_count=1)
        value=json.loads(json.dumps(value,sort_keys=True))
        m.validate_report(value,self.plan,self.index)
    def test_schema_scope_count_risk_and_identity_mutation_rejected(self):
        for defect in ('schema','scope','count','alias','checks','reference','summary','optimality'):
            v=copy.deepcopy(self.value)
            if defect=='schema':v['schema']='UNRELATED'
            if defect=='scope':v['promotion_allowed']=True
            if defect=='count':v['completed']=True
            if defect=='alias':v['alias_equivalence_verified']=True
            if defect=='checks':v['details'][0]['five_risk_checks']['MAX_SINGLE_WEIGHT']=1
            if defect=='reference':v['details'][0]['checkpoint_reference']['sha256']='0'*64
            if defect=='summary':v['risk_pass_count']=0
            if defect=='optimality':v['details'][0]['constrained_projection_optimality_independently_verified']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_report(v,self.plan,self.index)
    def test_original_publication_scope_exploit_does_not_write(self):
        for change in ('scope','schema'):
            v=copy.deepcopy(self.value);m.old.archive.merge(v['historical_expected_source_hashes'],m.LOADED)
            if change=='scope':v['promotion_allowed']=True
            else:v['schema']='UNRELATED'
            with tempfile.TemporaryDirectory() as d,patch.object(m.old,'exclusive_publish',side_effect=AssertionError('publication forbidden')):
                target=Path(d)/'audit.json'
                with self.assertRaises(ValueError):m.publish_verified(target,v)
                self.assertFalse(target.exists())
    def test_removed_inherited_source_resigned_partition_and_extra_flag_rejected(self):
        original=copy.deepcopy(self.value);m.old.archive.merge(original['historical_expected_source_hashes'],m.LOADED)
        for change in ('source','extra'):
            value=copy.deepcopy(original)
            if change=='source':
                key=next(k for k in value['historical_expected_source_hashes'] if k not in m.LOADED)
                del value['historical_expected_source_hashes'][key];value['archive_resolution']={}
            else:value['newly_certified_identity']=True
            with patch.object(m,'build',return_value=original),tempfile.TemporaryDirectory() as directory:
                target=Path(directory)/'audit.json'
                with self.assertRaises(ValueError):m.publish_verified(target,value)
                self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
