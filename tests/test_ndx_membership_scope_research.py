from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from backtest import ndx_membership_scope_research as scope


CONTRACT = Path(__file__).resolve().parents[1] / 'config/ndx_membership_scope_research_v1.yaml'


class MembershipScopeTests(unittest.TestCase):
    def test_bound_contract_removes_sector_filter_but_not_other_guards(self):
        digest = hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
        result = scope.load_membership_scope_contract(path=CONTRACT, expected_sha256=digest)
        self.assertTrue(result['scope_changed'])
        self.assertFalse(result['industry_filter_applied'])
        self.assertFalse(result['membership_evidence_verified'])
        self.assertFalse(result['point_in_time_verified'])
        self.assertFalse(result['full_universe_coverage_verified'])
        self.assertFalse(result['promotion_allowed'])
        contract = result['contract']
        self.assertEqual(contract['membership_contract']['unknown_membership_policy'], 'EXCLUDE_AND_REPORT_NOT_ACCEPT')
        self.assertTrue(contract['unchanged_guards']['original_five_risk_thresholds_preserved'])
        self.assertTrue(contract['unchanged_guards']['original_liquidity_thresholds_preserved'])
        self.assertEqual(contract['cardinality_contract']['maximum_k'], 'VERIFIED_ELIGIBLE_POOL_DISTINCT_ISSUER_COUNT')
        self.assertIsNone(contract['cardinality_contract']['fixed_k'])

    def test_membership_unknown_backfill_or_hash_only_acceptance_rejected(self):
        original = yaml.safe_load(CONTRACT.read_text())
        for key, value in (
                ('unknown_membership_policy', 'ACCEPT'), ('permitted_status', 'UNKNOWN'),
                ('current_snapshot_historical_backfill_allowed', True),
                ('observation_date_equals_effective_date_assumed', True),
                ('source_hash_alone_proves_membership', True),
                ('evidence_information_cutoff', 'NEXT_OPEN_EXECUTION_DATE'),
                ('membership_effective_asof', 'EXECUTION_SESSION'),
                ('announced_future_membership_policy', 'ACCEPT_BEFORE_EFFECTIVE'),
                ('evidence_available_by_decision_required', False),
                ('membership_effective_on_decision_required', False)):
            changed = deepcopy(original)
            changed['membership_contract'][key] = value
            with self.assertRaises(ValueError, msg=key): scope.validate_membership_scope_contract(changed)

    def test_no_legacy_full_coverage_or_scope_change_denial(self):
        original = yaml.safe_load(CONTRACT.read_text())
        for section, key, value in (
                ('scope_change', 'scope_changed', False),
                ('scope_change', 'industry_filter_applied', True),
                ('legacy_evidence_contract', 'strict_technology_role', 'FULL_NASDAQ_100'),
                ('legacy_evidence_contract', 'legacy_subsets_prove_full_membership_coverage', True),
                ('unchanged_guards', 'risk_threshold_override_allowed', True),
                ('unchanged_guards', 'original_identity_requirements_preserved', False),
                ('cardinality_contract', 'fixed_k', 8),
                ('mutation_boundary', 'order_creation_allowed', True),
                ('mutation_boundary', 'promotion_allowed', True)):
            changed = deepcopy(original)
            changed[section][key] = value
            with self.assertRaises(ValueError, msg=key): scope.validate_membership_scope_contract(changed)

    def test_bool_integer_confusion_and_industry_allowlist_injection_rejected(self):
        original = yaml.safe_load(CONTRACT.read_text())
        for fault in ('schema_bool', 'bool_as_int', 'industry_filter'):
            changed = deepcopy(original)
            if fault == 'schema_bool': changed['schema_version'] = True
            if fault == 'bool_as_int': changed['scope_change']['scope_changed'] = 1
            if fault == 'industry_filter': changed['membership_contract']['accepted_risk_chains'] = ['semiconductor_equipment']
            with self.assertRaises(ValueError, msg=fault): scope.validate_membership_scope_contract(changed)

    def test_bad_hash_and_rehashed_duplicate_yaml_key_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SHA differs'):
            scope.load_membership_scope_contract(path=CONTRACT, expected_sha256='0' * 64)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scope.yaml'
            raw = CONTRACT.read_bytes() + b'\nschema_version: 1\n'
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                scope.load_membership_scope_contract(path=path, expected_sha256=hashlib.sha256(raw).hexdigest())

    def test_changed_contract_or_module_during_load_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scope.yaml'
            path.write_bytes(CONTRACT.read_bytes())
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            original = scope.validate_membership_scope_contract

            def changed(contract):
                original(contract)
                path.write_text('changed')

            with patch.object(scope, 'validate_membership_scope_contract', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'source changed'):
                    scope.load_membership_scope_contract(path=path, expected_sha256=digest)
            with patch.object(scope, '_LOADED_SHA', '0' * 64):
                with self.assertRaisesRegex(ValueError, 'source drift'):
                    scope.load_membership_scope_contract(path=CONTRACT,
                        expected_sha256=hashlib.sha256(CONTRACT.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
