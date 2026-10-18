import copy
import unittest
from unittest.mock import patch
from scripts import ndx_latest_fourteen_panel_independent_readback_20260919 as m
import test_ndx_latest_fourteen_panel_independent_readback_20260919 as fixtures


class FourteenIndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.FourteenReadbackTests.setUpClass()
        cls.f=fixtures.FourteenReadbackTests

    def test_build_inheritance_excludes_subject_self_but_keeps_all_parent_sources(self):
        # Real direct artifact reads; expensive closure hashing stubbed only to isolate
        # the inheritance contract. This is not an independent real source audit.
        with patch.object(m.archive,'verify_expected_sources',return_value=self.f.value['archive_resolution']):
            value=m.build(m.PANEL['path'],m.PANEL['sha256'])
            self.assertEqual(value['historical_expected_source_hashes'][m.PANEL['path']],m.PANEL['sha256'])
        real_read=m.read
        def omit_parent(ref,sources):
            value=real_read(ref,sources)
            if ref==m.PANEL:
                value=copy.deepcopy(value)
                key=next(iter(self.f.old['historical_expected_source_hashes']))
                value['historical_expected_source_hashes'].pop(key,None)
            return value
        with patch.object(m,'read',side_effect=omit_parent),patch.object(m.archive,'verify_expected_sources',return_value=self.f.value['archive_resolution']):
            with self.assertRaises(ValueError):m.build(m.PANEL['path'],m.PANEL['sha256'])

    def test_saved_report_resign_and_unchanged_metadata_rejected(self):
        report=dict(schema='LATEST_FOURTEEN_CONDITIONAL_PANEL_INDEPENDENT_READBACK_V1',panel_reference=m.PANEL,old9_reference=m.OLD,old9_audit_reference=m.AUDIT,five_identity_reference=m.FIVE,details=dict(m.DETAILS),historical_expected_source_hashes={},archive_resolution={},**dict.fromkeys(m.FALSE,False))
        with patch.object(m,'build',return_value=dict(report,historical_expected_source_hashes={'bound':'hash'})),patch.object(m.prior.saved.recipe,'exclusive_publish',side_effect=AssertionError('must not publish')):
            with self.assertRaises(ValueError):m.publish_verified('unused',report)
        changed=copy.deepcopy(self.f.value)
        row=next(r for r in changed['panel']['observed_provenance_and_missing'] if r['ticker']=='GOOG')
        row['blocking_reasons']=['forged']
        with self.assertRaises(ValueError):m.inspect(changed,self.f.old,self.f.facts,self.f.proposals,self.f.wrappers)
        for defect in ('cusip','floor'):
            facts=copy.deepcopy(self.f.facts);row=next(r for r in facts['rows'] if r['ticker']=='LRCX')
            row['cusip' if defect=='cusip' else 'minimum_conditional_date']='512807108' if defect=='cusip' else '2024-10-02'
            with self.assertRaises(ValueError):m.inspect(self.f.value,self.f.old,facts,self.f.proposals,self.f.wrappers)


if __name__=='__main__':unittest.main()
