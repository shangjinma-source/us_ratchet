"""Coverage must retain all securities while exposing issuer and PIT gaps."""
import unittest
from copy import deepcopy
import json

import pandas as pd

from scripts import ndx_full_membership_coverage_research as audit


def fixtures():
    proxy = pd.DataFrame([dict(report_date='2023-12-31', available_date='2024-03-01',
        accession_number='ONE', ticker=ticker, cusip=cusip, isin='ISIN' + cusip, name=ticker)
        for ticker, cusip in (('GOOG', '02079K107'), ('GOOGL', '02079K305'), ('A', '000000001'))])
    identities = pd.DataFrame([dict(cusip=row.cusip, available_from='2020-01-01',
        security_id='security:' + row.cusip, issuer_id='issuer:GOOGLE' if row.ticker.startswith('GOOG') else 'issuer:A',
        identity_status='resolved') for row in proxy.itertuples()])
    taxonomy = pd.DataFrame([dict(security_id=row.security_id, status='accepted',
        evidence_available_date='2024-03-02', selection_dates='2024-03-01', risk_chain='CHAIN')
        for row in identities.itertuples()])
    old = pd.DataFrame([dict(ticker='GOOG', issuer_id='issuer:GOOGLE')])
    panel = pd.DataFrame({'GOOG': [.1]})
    return proxy, identities, taxonomy, old, panel


class FullMembershipCoverageTests(unittest.TestCase):
    def test_distinct_share_classes_retained_and_issuer_count_not_security_count(self):
        proxy, identities, taxonomy, old, panel = fixtures()
        result = audit.audit_snapshot(proxy, cutoff='2024-03-01', universe=old, returns=panel,
            nominal=panel, identities=identities, taxonomy=taxonomy)
        self.assertEqual(result['proxy_security_count'], 3)
        self.assertEqual(result['locally_mapped_issuer_count'], 2)
        self.assertEqual(len(result['candidates']), 3)
        self.assertEqual(result['added_proxy_tickers'], ['A', 'GOOGL'])
        self.assertEqual(result['missing_return_columns_in_old_inputs'], ['GOOGL', 'A'])
        self.assertEqual(result['candidates'][-1]['cusip'], '000000001')
        self.assertIsNone(result['exact_membership_issuer_count'])
        self.assertFalse(result['full_issuer_upper_bound_verified'])

    def test_filing_available_on_execution_day_is_not_known_at_prior_close(self):
        proxy, *_ = fixtures()
        with self.assertRaises(ValueError): audit.snapshot_asof(proxy, '2024-02-29')
        self.assertEqual(len(audit.snapshot_asof(proxy, '2024-03-01')), 3)

    def test_future_or_ambiguous_identity_not_dropped_or_promoted(self):
        proxy, identities, taxonomy, old, panel = fixtures()
        identities.loc[2, 'available_from'] = '2024-03-02'
        duplicated = identities.iloc[[0]].copy()
        duplicated['security_id'] = 'security:OTHER'
        identities = pd.concat([identities, duplicated], ignore_index=True)
        result = audit.audit_snapshot(proxy, cutoff='2024-03-01', universe=old, returns=panel,
            nominal=panel, identities=identities, taxonomy=taxonomy)
        self.assertEqual(result['proxy_security_count'], 3)
        self.assertEqual(result['unresolved_local_identity_tickers'], ['GOOG', 'A'])
        self.assertEqual(len(result['unresolved_local_risk_tickers']), 3)
        self.assertTrue(all(not row['provider_price_identity_verified'] for row in result['candidates']))

    def test_duplicate_security_snapshot_rejected(self):
        proxy, *_ = fixtures()
        with self.assertRaises(ValueError):
            audit.snapshot_asof(pd.concat([proxy, proxy.iloc[[0]]]), '2024-03-01')

    def test_conflicting_status_on_same_identity_cannot_be_deduplicated_away(self):
        proxy, identities, taxonomy, old, panel = fixtures()
        conflict = identities.iloc[[0]].copy()
        conflict['identity_status'] = 'unresolved'
        for frame in (pd.concat([identities, conflict]), pd.concat([conflict, identities])):
            result = audit.audit_snapshot(proxy, cutoff='2024-03-01', universe=old, returns=panel,
                nominal=panel, identities=frame, taxonomy=taxonomy)
            self.assertIn('GOOG', result['unresolved_local_identity_tickers'])

    def test_inventory_duplicate_or_reordered_date_cannot_hide_coverage(self):
        original = json.loads(audit.INVENTORY.read_bytes())
        audit.validate_inventory(original)
        for fault in ('duplicate', 'reordered'):
            inventory = deepcopy(original)
            if fault == 'duplicate': inventory['reports'][1] = deepcopy(inventory['reports'][0])
            else: inventory['reports'].reverse()
            with self.assertRaises(ValueError): audit.validate_inventory(inventory)


if __name__ == '__main__':
    unittest.main()
