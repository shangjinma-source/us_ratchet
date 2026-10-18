from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_current_quantity_portfolio_research_v2 import fixture
from test_current_quantity_v2_current_cash_sources import snapshot_fixture, month_config
from test_current_quantity_v2_intraday_reference import NOW, raw
from data.current_quantity_v2_verified_snapshot_bundle import VerifiedSnapshotBundleService
from data.current_quantity_v2_current_cash_factory import create_services


def withdrawal(base):
    descriptor = base.loader()
    evidence = b'{"status":"UNVERIFIED_COORDINATE"}'
    (base.root / 'withdrawal.json').write_bytes(evidence)
    return dict(input_path=descriptor['input_path'],
                input_sha256=descriptor['source_hashes'][descriptor['input_path']],
                descriptor_sha256='a' * 64, reason='Historical coordinate unverified',
                evidence={'withdrawal.json': sha256(evidence).hexdigest()})


class SourceWithdrawalTests(unittest.TestCase):
    def test_block_new_and_cached_keep_historical_snapshot_and_unaffected_input(self):
        with TemporaryDirectory() as folder:
            base, search, descriptor = fixture(Path(folder))
            view = base.calculate('60')
            record = withdrawal(base)
            service = VerifiedSnapshotBundleService(base, source_withdrawals=(record,))
            for operation in (lambda: service.calculate('60'),
                              lambda: service.verified_snapshot_bundle(view['research_id']),
                              lambda: service.decision(view['research_id'])):
                with self.assertRaisesRegex(ValueError, '^RESEARCH_SOURCE_WITHDRAWN$'):
                    operation()
            historical = service.snapshot(view['research_id'])
            self.assertEqual(historical['stocks'], view['stocks'])
            self.assertEqual(historical['status'], 'UNAVAILABLE')
            self.assertTrue(historical['execution_blocked'])
            self.assertEqual(historical['error_code'], 'RESEARCH_SOURCE_WITHDRAWN')
            self.assertEqual(search.call_count, 1)
            historical['source_withdrawal']['evidence'].clear()
            self.assertTrue(service.snapshot(view['research_id'])['source_withdrawal']['evidence'])
            other = deepcopy(record); other['input_sha256'] = 'b' * 64
            unaffected = VerifiedSnapshotBundleService(base, source_withdrawals=(other,))
            self.assertEqual(unaffected.calculate('60')['stocks'], view['stocks'])
            self.assertEqual(unaffected.verified_snapshot_bundle(view['research_id'])['snapshot'], view)

    def test_same_bytes_renamed_still_withdrawn_and_evidence_hash_verified(self):
        with TemporaryDirectory() as folder:
            base, _, descriptor = fixture(Path(folder))
            record = withdrawal(base)
            service = VerifiedSnapshotBundleService(base, source_withdrawals=(record,))
            renamed = deepcopy(descriptor)
            renamed['input_path'] = 'renamed.json'
            renamed['source_hashes']['renamed.json'] = record['input_sha256']
            with patch.object(base, 'loader', return_value=renamed):
                with self.assertRaisesRegex(ValueError, 'RESEARCH_SOURCE_WITHDRAWN'):
                    service.calculate('60')
            with self.assertRaisesRegex(ValueError, 'RESEARCH_SOURCE_WITHDRAWN'):
                service.require_source_hashes_admitted({'another.json': record['input_sha256']})
            (base.root / 'withdrawal.json').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'SOURCE_WITHDRAWAL_EVIDENCE_CHANGED'):
                VerifiedSnapshotBundleService(base, source_withdrawals=(record,))

    def test_real_cached_preview_accept_and_continuation_cannot_bypass(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            snapshots, view = snapshot_fixture(root)
            record = withdrawal(snapshots._service)
            calls = []
            def fetch(ticker):
                calls.append(ticker)
                return raw(ticker, 10)
            services = create_services(root=root, snapshot_service=snapshots,
                server_account_id='fixed-pool', database_path=root/'paper.sqlite3',
                fetch=fetch, clock=lambda: NOW, execution_month_mandate=month_config(root),
                unit_review_reader=lambda _: self.fail('withdrawn continuation reached unit review'))
            proposal = services['preview'].preview(view['decision_id'])
            request = dict(account_id='fixed-pool', proposal_id=proposal['proposal_id'], operation_id='accept')
            # Install the new server policy after a genuine quote/preview cache
            # exists, reproducing the stale-cache risk without HTTP overrides.
            snapshots._withdrawals = (deepcopy(record),)
            count = len(calls)
            with self.assertRaisesRegex(ValueError, 'RESEARCH_SOURCE_WITHDRAWN'):
                services['paper'].accept(**request)
            with self.assertRaisesRegex(ValueError, 'RESEARCH_SOURCE_WITHDRAWN'):
                services['sources'].capture(view['decision_id'])
            self.assertEqual(len(calls), count)
            with self.assertRaises(ValueError):
                services['store'].read('fixed-pool')
            snapshots._withdrawals = ()
            refreshed = services['preview'].preview(view['decision_id'])
            request['proposal_id'] = refreshed['proposal_id']
            accepted = services['paper'].accept(**request)
            before = services['store'].read('fixed-pool')
            snapshots._withdrawals = (deepcopy(record),)
            # Completed operation retries are history, not a new acceptance.
            self.assertEqual(services['paper'].accept(**request), accepted)
            with self.assertRaisesRegex(ValueError, 'RESEARCH_SOURCE_WITHDRAWN'):
                services['paper'].continuation_previewer(account_id='fixed-pool', expected_revision=before['ledger']['revision'])
            with self.assertRaisesRegex(ValueError, 'RESEARCH_SOURCE_WITHDRAWN'):
                services['paper'].continuation_resolver(before, 'cached-continuation', NOW)
            self.assertEqual(services['store'].read('fixed-pool'), before)
            self.assertEqual(len(calls), count + 2)


if __name__ == '__main__':
    unittest.main()
