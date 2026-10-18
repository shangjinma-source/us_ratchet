from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_saved_classification_coverage_20261003 as producer


def evidence():
    refs = {key: dict(path=key, sha256=str(index) * 64) for index, key in enumerate(producer.BOUND)}
    flags = dict.fromkeys(('point_in_time_verified', 'promotion_allowed', 'execution_authorized', 'fit_performed'), False)
    documents = dict(wiring=dict(source_hashes={}, **flags), training_panel=dict(source_hashes={}, **flags))
    documents['wiring_publication'] = dict(schema='BULK_CONDITIONAL_WIRING_PUBLICATION_V1',
        status='PUBLISHED_CONDITIONAL_METADATA_ONLY', wiring_reference=refs['wiring'], source_hashes={}, **flags)
    documents['training_publication'] = dict(schema='DATED_CONDITIONAL_TRAINING_PANEL_PUBLICATION_V1',
        status='PUBLISHED_TRAINING_PAYLOAD_NOT_FITTED', panel_reference=refs['training_panel'], source_hashes={}, **flags)
    documents['training_audit'] = dict(schema='DATED_TRAINING_PANEL_INDEPENDENT_READBACK_V1', status='PASS',
        panel_sha256=refs['training_panel']['sha256'], publication_sha256=refs['training_publication']['sha256'],
        reader_sha256=refs['training_reader']['sha256'], security_count=77, issuer_count=76,
        observed_security_count=101, training_return_rows=126, training_numeric_cells=9702,
        preserved_sidecar_count=7, evaluation_numeric_fields_in_fit_payload=0,
        **dict.fromkeys(('fit_performed', 'raw_redecoded', 'old_audit_repeated', 'point_in_time_verified',
            'legal_training_input_admitted', 'liquidity_qualification_at_training_cutoff_verified'), False))
    blobs = dict(wiring_review_report=('PASS ' + ' '.join(refs[k]['sha256'] for k in
        ('wiring', 'wiring_publication', 'wiring_reader'))).encode())
    return documents, blobs, refs


class Tests(unittest.TestCase):
    def test_saved_report_evidence_and_audit_have_distinct_contracts(self):
        arguments = evidence()
        before = deepcopy(arguments)
        producer.validate_evidence(*arguments)
        self.assertEqual(arguments, before)
        wrong = deepcopy(arguments)
        wrong[1]['wiring_review_report'] = b'PASS without bound identifiers'
        with self.assertRaises(ValueError): producer.validate_evidence(*wrong)

    def test_count_boolean_permission_numeric_and_bad_receipt_rejected(self):
        for mode in ('count', 'authority', 'receipt'):
            documents, blobs, refs = evidence()
            if mode == 'count': documents['training_audit']['evaluation_numeric_fields_in_fit_payload'] = False
            elif mode == 'authority': documents['training_panel']['point_in_time_verified'] = 0
            else: documents['training_publication']['panel_reference'] = refs['wiring']
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                producer.validate_evidence(documents, blobs, refs)

    def test_no_action_or_existing_namespace_stops_before_source_read(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('No source read')):
            with self.assertRaises(ValueError): producer.run()
            with patch.object(Path, 'exists', return_value=True):
                with self.assertRaises(ValueError): producer.run(execute=True)


if __name__ == '__main__':
    unittest.main()
