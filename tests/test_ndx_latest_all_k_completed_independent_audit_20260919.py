import copy
import json
import unittest
from pathlib import Path
from scripts import ndx_latest_all_k_completed_independent_audit_20260919 as audit


class CompletedPrefixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources={};cls.plan=audit.read(dict(path=str(audit.PLAN),sha256=audit.PLAN_SHA),sources)
        cls.panel=audit.read(cls.plan['panel_reference'],sources)['panel']
        folder=audit.PLAN.parent/'tasks'
        index=audit.read(dict(path=str(folder/'index_ada688df53945ee552c913ee2fdfc938c3fe58728af99b66e02b9921aa8d751c.json'),sha256='cf25ef3630d194dfd65092f4e3dd1ecb61dd9f0ce5c9ec974b8d046a4dbbef9c'),sources)
        cls.values=[audit.read(dict(path=e['path'],sha256=e['sha256']),sources) for e in index['entries']]

    def test_real_first_two_matrix_and_risks_without_fitter(self):
        self.assertEqual(len(audit.inspect_plan(self.plan,self.panel)),764)
        for value in self.values:
            detail=audit.inspect_result(value['result'],value['task'],self.panel)
            self.assertEqual(detail['holding_count'],4)
            self.assertFalse(detail['constrained_projection_optimality_independently_verified'])

    def test_saved_result_tampering_and_boolean_anchor_rejected(self):
        value=self.values[0]
        for field,replacement in [('fit_data_sha256','0'*64),('surviving_anchor_mass',False),('declared_constraints_passed',False),('promotion_allowed',True)]:
            bad=copy.deepcopy(value['result']);bad[field]=replacement
            with self.subTest(field=field),self.assertRaises(ValueError):audit.inspect_result(bad,value['task'],self.panel)
        bad=copy.deepcopy(value['result']);sid=next(iter(bad['targets']));bad['targets'][sid]['target_weight']+=.001
        with self.assertRaises(ValueError):audit.inspect_result(bad,value['task'],self.panel)

    def test_alias_denominator_and_completed_run_confirmation(self):
        bad=copy.deepcopy(self.plan);bad['anchor_aliases'].pop()
        with self.assertRaises(ValueError):audit.inspect_plan(bad,self.panel)
        with self.assertRaises(ValueError):audit.build('unused','unused')

    def test_partition_never_promotes_gap_or_resigns_old_hash(self):
        path=str(Path('gap.csv').resolve());row=dict(expected_historical_sha256='old',archived_path='archive',archived_sha256='observed',historical_expected_bytes_preserved=False)
        contract=dict(authority_source_hashes={},rows={path:row})
        partition=audit.declared_partition({path:'old'},contract)
        self.assertEqual(partition['archive_resolutions'],[])
        self.assertFalse(partition['historical_gap_observations'][0]['historical_bytes_recovered'])
        with self.assertRaises(ValueError):audit.declared_partition({path:'observed'},contract)


if __name__=='__main__':unittest.main()
