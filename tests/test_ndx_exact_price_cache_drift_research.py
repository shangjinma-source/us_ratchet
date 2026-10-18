import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backtest import ndx_exact_price_cache_drift_research as drift
from scripts import ndx_delta_paired_snapshot_limited_drift_audit_research as audit


class ExactDriftTests(unittest.TestCase):
    def test_real_authority_exact26_maps_to_hard_manifest_and_selected_plan(self):
        contract=drift.load_contract()
        self.assertEqual(len(contract['exceptions']),26)
        self.assertFalse(contract['historical_full_source_closure_verified'])
        self.assertEqual(contract['authority_source_hashes'][str(drift.REPORT)],drift.REPORT_SHA)

    def test_exact_old_current_pair_only_and_nonexempt_source_never_waived(self):
        with tempfile.TemporaryDirectory() as directory:
            csv=Path(directory)/'ADI.csv';other=Path(directory)/'immutable_context.json'
            csv.write_bytes(b'new');other.write_bytes(b'context')
            old=hashlib.sha256(b'old').hexdigest();new=drift.file_sha(csv);h=drift.file_sha(other)
            contract=dict(authority_source_hashes={},exceptions={str(csv):dict(expected_historical_sha256=old,observed_current_sha256=new)})
            expected={str(csv):old,str(other):h}
            with patch.object(drift,'load_contract',return_value=contract):
                result=drift.verify_expected_sources(expected,contract)
                self.assertNotIn(str(csv),result['verified_source_hashes'])
                self.assertEqual(result['verified_source_hashes'],{str(other):h})
                self.assertEqual(result['historical_gap_observations'][0]['expected_historical_sha256'],old)
                with self.assertRaisesRegex(ValueError,'Different historical SHA'):drift.verify_expected_sources({str(csv):new},contract)
                other.write_bytes(b'different')
                with self.assertRaisesRegex(ValueError,'Non-exempt'):drift.verify_expected_sources(expected,contract)
                other.write_bytes(b'context');csv.write_bytes(b'newer')
                with self.assertRaisesRegex(ValueError,'changed again'):drift.verify_expected_sources(expected,contract)

    def test_exception_list_tampering_and_wrong_complete_index_reject(self):
        with patch.object(drift,'load_contract',return_value=dict(authority_source_hashes={},exceptions={})):
            with self.assertRaisesRegex(ValueError,'hard-bound'):drift.verify_expected_sources({},dict(exceptions={'extra.csv':{}},authority_source_hashes={}))
        with self.assertRaisesRegex(ValueError,'complete614'):audit.audit_limited(index_path='wrong',index_sha256='0'*64)

    def test_gap_and_loaded_source_observation_must_still_match(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.yaml';path.write_bytes(b'current')
            gap=dict(path=str(path),observed_current_sha256=drift.file_sha(path))
            audit.check_config_observations([gap]);path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'config observation'):audit.check_config_observations([gap])

    def test_private_verifier_binding_keeps_strict_globals_and_partitions_old_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            expected={};exceptions={}
            for i in range(26):
                path=Path(directory)/f'{i}.csv';path.write_bytes(b'current')
                old=hashlib.sha256(b'old').hexdigest();expected[str(path)]=old
                exceptions[str(path)]=dict(expected_historical_sha256=old,observed_current_sha256=drift.file_sha(path))
            config=Path(directory)/'config.yaml';config.write_bytes(b'config')
            gap=dict(path=str(config),observed_current_sha256=drift.file_sha(config))
            contract=dict(authority_source_hashes={},exceptions=exceptions)
            def scalar_stub(index_path,index_sha):
                verify_sources_and_gaps(expected,[gap])
                return dict(source_hashes=dict(expected),tasks=[dict(gap=gap)])
            original_verify=audit.strict.verify_sources_and_gaps
            with (patch.object(drift,'load_contract',return_value=contract),patch.object(audit.strict,'audit_complete',scalar_stub)):
                result=audit.audit_limited(index_path=audit.INDEX,index_sha256=audit.INDEX_SHA)
                self.assertIs(audit.strict.verify_sources_and_gaps,original_verify)
                self.assertNotIn('source_hashes',result)
                self.assertTrue(set(expected).isdisjoint(result['verified_source_hashes']))
                self.assertEqual(len(result['historical_price_cache_gap_observations']),26)
                self.assertFalse(result['strict_no_gap_audit_passed'])
                Path(next(iter(expected))).write_bytes(b'changed-again')
                with self.assertRaisesRegex(ValueError,'changed again'):
                    audit.publish_limited(Path(directory)/'report.json',result)


if __name__=='__main__':unittest.main()
