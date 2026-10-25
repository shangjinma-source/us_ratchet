from pathlib import Path
import unittest
from unittest.mock import patch
from data.strategy_daily_rebinding_reader import ArchivedRebindingDailyEvidenceReader
from data.strategy_daily_rolling_admission_v3 import RollingDailyAdmissionV3
from data.strategy_daily_composition_v3 import DailyCompositionV3
from data.strategy_account_runtime import build_runtime
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
import test_strategy_account_rolling_router as fixtures


class AdmissionTests(unittest.TestCase):
    def test_actual_rolling_archive_resolves_current_bound_provider_inside_one_snapshot(self):
        f=fixtures.RollingRouterTests();f.setUp();self.addCleanup(f.doCleanups)
        target=f.router.generate(**f.fixture.request())
        runtime=f.fixture.built[0]
        real=build_runtime(root=f.fixture.root,configuration=f.fixture.configuration,clock=lambda:f.fixture.now)
        runtime.execution_provider=real.execution_provider
        reader=ArchivedRebindingDailyEvidenceReader(root=f.fixture.root,
            archive_root=Path(f.fixture.root)/"dailyarchive",parent_receipt_path=None,
            trusted_parent_sha256=None,source_paths={})
        service=RollingDailyAdmissionV3(monthly=f.router,reader=reader,clock=lambda:f.fixture.now,
                                       validate_code=lambda:None)
        seen=[]
        def compose(**kwargs):
            self.assertIsNotNone(f.router._active_snapshot)
            self.assertIs(kwargs["execution_provider"].__func__,StrategyAccountEvidenceProvider.execution)
            self.assertIs(kwargs["execution_provider"].__self__,real.execution_provider.__self__)
            self.assertEqual(kwargs["fee_bps"],runtime.selection.fees)
            seen.append(kwargs["execution_provider"])
            return DailyCompositionV3(**kwargs)
        before=f.router.accounts.read();calls=f.calls;selections=f.fixture.selection_calls
        with patch("data.strategy_daily_rolling_admission_v3.DailyCompositionV3",side_effect=compose):
            result=service.preview(expected_revision=before["revision"],target_id=target["target_id"])
        self.assertEqual(result["status"],"WAIT")
        self.assertEqual(result["detail_status"],"DAILY_PREVIEW_DISABLED")
        self.assertEqual(f.calls,calls+1);self.assertEqual(len(seen),1)
        self.assertEqual(f.router.accounts.read(),before);self.assertEqual(f.fixture.selection_calls,selections)
        self.assertFalse((Path(f.fixture.root)/"dailyarchive").exists())
        # A subsequent archive change must fail; no reuse of a cached old provider.
        f.snapshot=dict(f.snapshot,archive_sha256="0"*64)
        with self.assertRaises(ValueError):
            service.preview(expected_revision=before["revision"],target_id=target["target_id"])
