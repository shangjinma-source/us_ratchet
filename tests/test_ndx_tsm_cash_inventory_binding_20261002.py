"""Synthetic pointer binding only; no actual inventory or sidecar build."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_tsm_cash_inventory_binding_20261002 as m


def fixture():
    refs = {k: {'path': 'synthetic/' + k, 'sha256': 'a'*64} for k in m.BOUND}
    rows = []
    for lane in m.LANES:
        for d, e in m.CLOCK:
            securities = []
            if d != m.CLOCK[0][0] or lane == 'INCUMBENT_ADD_ONLY_CONTROL':
                for i in range(5):
                    securities.append({'security_id': m.SID if i == 0 else 'OTHER_'+str(i), 'gaps': [m.GAP],
                        'dated_identity_evidence': [], 'identity_interval_certified': False, 'provider_binding_verified': False,
                        'saved_coordinates': [{'value': {'issuer_id': m.ISSUER, 'ticker': 'TSM'}}]})
            rows.append(dict(lane=lane, decision_date=d, execution_date=e, fork_executable=False, securities=securities,
                             gaps=[dict(security_id=s['security_id'], reason=m.GAP) for s in securities]))
    inventory = dict(schema='CONDITIONAL_NEW_CASH_SIX_COORDINATE_INVENTORY_V2', rows=rows, branch_coordinate_count=36,
                     decision_clock=[list(p) for p in m.CLOCK], cash_fork_called=False, point_in_time_verified=False,
                     promotion_allowed=False, source_hashes={'old': 'b'*64})
    publication = dict(schema='CONDITIONAL_CASH_INVENTORY_V2_PUBLICATION_RECEIPT_V1', inventory_reference=refs['inventory'],
                       source_hashes=inventory['source_hashes'], status='SOURCE_LOCKED_INVENTORY_ONLY_NOT_FORK_READY', fork_executed=False)
    sidecar = dict(schema='TSM_INCUMBENT_CONDITIONAL_DATED_IDENTITY_V1', ticker='TSM', security_id=m.SID, issuer_id=m.ISSUER,
        cusip='874039100', security_class='American Depositary Shares', ordinary_shares_per_ads=5,
        fact_as_of='2018-12-31', report_date='2018-12-31', filed_date='2019-04-17', evidence_available_date='2019-04-18',
        fetched_at='2026-07-14T17:38:21+00:00', issuer_cik_binding_kind='SAVED_MANIFEST_AND_SEC_ARCHIVE_PATH_NOT_INLINE_FIELD',
        historical_2023_identity_interval_verified=False, point_in_time_verified=False, ndx_membership_verified=False,
        price_identity_verified=False, holdings_conversion_performed=False, promotion_allowed=False,
        overlay_join_assumption='Explicit synthetic conditional cross-source join', original_manifest={}, evidence=[],
        source_references={'filing': {}, 'manifest': {}})
    sidecar.update(dict.fromkeys(('price_conversion_performed', 'historical_2023_ads_ratio_verified',
        'inline_cik_field_verified', 'local_evidence_available_in_2023_verified', 'legal_identity_certified',
        'corporate_action_completeness_verified', 'live_execution_authorized', 'orders_generated',
        'fit_performed', 'account_executed', 'old_audit_repeated'), False))
    sidecar['source_hashes'] = {'sidecar-source': 'd'*64}
    sidecar_publication = dict(schema='TSM_CONDITIONAL_IDENTITY_PUBLICATION_V1',
        status='PUBLISHED_CONDITIONAL_SID_SIDECAR_ONLY', identity_reference=refs['sidecar'], source_hashes=sidecar['source_hashes'])
    return inventory, publication, sidecar, refs, sidecar_publication


class Tests(unittest.TestCase):
    def test_31_pointers_without_copy_or_gap_removal(self):
        args = fixture(); before = deepcopy(args); r = m.assemble(*args)
        self.assertEqual(args, before); self.assertEqual(len(r['rows']), 31)
        self.assertEqual(r['remaining_original_identity_gap_count'], 155)
        self.assertEqual(len({x['inventory_security_reference']['json_pointer'] for x in r['rows']}), 31)
        for row in r['rows']:
            self.assertEqual(row['original_gaps_preserved'], [m.GAP])
            self.assertNotIn('original_security_row', row)
            self.assertFalse(row['shares_or_prices_rescaled']); self.assertFalse(row['fork_executable'])

    def test_wrong_saved_coordinate_or_sid_or_duplicate_rejected(self):
        for attack in ('issuer', 'ticker', 'sid', 'duplicate'):
            args = fixture(); sec = args[0]['rows'][1]['securities'][0]
            if attack in ('issuer', 'ticker'): sec['saved_coordinates'][0]['value']['issuer_id' if attack == 'issuer' else 'ticker'] = 'wrong'
            elif attack == 'sid': sec['security_id'] = 'security:0001046179:874039100'
            else: args[0]['rows'][1]['securities'].append(deepcopy(sec))
            with self.subTest(attack=attack), self.assertRaises(ValueError): m.assemble(*args)

    def test_sidecar_class_dates_permissions_ratio_rejected(self):
        for key, value in [('security_class', 'Common Shares'), ('issuer_id', 'reportingfund'), ('ordinary_shares_per_ads', True),
                           ('point_in_time_verified', True), ('fetched_at', '2019-04-18'), ('holdings_conversion_performed', True)]:
            args = fixture(); args[2][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): m.assemble(*args)

    def test_publication_and_155_gap_denominator(self):
        args = fixture(); args[1]['inventory_reference'] = dict(args[3]['inventory'], sha256='c'*64)
        with self.assertRaises(ValueError): m.assemble(*args)

    def test_sidecar_publication_cannot_reference_other_identity(self):
        for attack in ('status', 'reference', 'sources'):
            args = fixture()
            if attack == 'status': args[4]['status'] = 'FAILED'
            elif attack == 'reference': args[4]['identity_reference'] = dict(args[3]['sidecar'], sha256='f'*64)
            else: args[4]['source_hashes'] = {}
            with self.subTest(attack=attack), self.assertRaises(ValueError): m.assemble(*args)
        args = fixture(); args[0]['rows'][1]['securities'][1]['gaps'] = []
        args[0]['rows'][1]['gaps'].pop(1)
        with self.assertRaises(ValueError): m.assemble(*args)

    def test_pending_anchor_fails_before_io(self):
        with patch.object(m, 'BOUND', {**m.BOUND, 'sidecar': ('pending', None)}), patch.object(m, 'strict') as strict:
            with self.assertRaises(ValueError): m.build()
            strict.assert_not_called()

    def test_postwrite_source_drift_preserved_no_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root/'source'; source.write_bytes(b'original'); output = root/'out'
            result = {'source_hashes': {str(source): m.digest(source.read_bytes())}}
            durable = m.durable
            def drift(path, raw):
                durable(path, raw)
                if path.name == 'bindings.json': source.write_bytes(b'drift')
            with patch.object(m, 'OUTPUT', output), patch.object(m, 'build', return_value=result) as build, patch.object(m, 'durable', side_effect=drift):
                with self.assertRaises(ValueError): m.publish()
                self.assertTrue((output/'failure.json').exists()); build.reset_mock()
                with self.assertRaises(ValueError): m.publish()
                build.assert_not_called()
