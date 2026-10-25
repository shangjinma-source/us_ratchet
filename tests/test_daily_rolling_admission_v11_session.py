"""Cross-session cap routing only; does not certify a new session's signal."""
from contextlib import nullcontext
from datetime import datetime
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import test_daily_composition_v3 as fixtures
from data.strategy_daily_rolling_admission_v11 import RollingDailyAdmissionV11

class SessionCapRoutingTests(TestCase):
    def test_new_york_date_controls_cap_database_and_provider_is_not_mutated(self):
        with TemporaryDirectory() as folder:
            c=fixtures.CompositionTests().setup_case(folder)
            legacy=SimpleNamespace(path=Path(folder)/'legacy.sqlite3',clock=lambda:c.clock[0].isoformat(),max_history_rows=100,max_history_bytes=1000000)
            legacy.path.touch()
            def limits(**kwargs):return {}
            original_limits=partial(limits,cap_store=legacy);c.provider.limits=original_limits
            original_market=SimpleNamespace(identity=object(),fetch=object(),clock=lambda:c.clock[0],workers=1,max_mark_age=120)
            c.provider.market=original_market
            runtime=SimpleNamespace(execution_provider=c.provider.execution,selection=SimpleNamespace(fees='10'))
            c.monthly.root=Path(folder);c.monthly.snapshot_operation=lambda:nullcontext()
            c.monthly._for_target=lambda target:(runtime,{})
            daily=RollingDailyAdmissionV11(monthly=c.monthly,reader=c.reader,clock=lambda:c.clock[0],validate_code=lambda:None,policy_execution_enabled=True,policy_id=fixtures.POLICY)
            observed=[]
            def service(**kwargs):
                provider=kwargs['execution_provider'].__self__
                observed.append(Path(provider.limits.keywords['cap_store'].path).name)
                return SimpleNamespace(preview=lambda **request:{'status':'TEST_ROUTING_ONLY'})
            prefix='data.strategy_daily_rolling_admission_v11.'
            with patch(prefix+'validate_account_identity_coverage'),patch(prefix+'DailyMarketCaptureV3'),patch(prefix+'HaltMarketCaptureV1'),patch(prefix+'DailyCompositionV7',side_effect=service):
                for moment in ('2026-10-22T23:59:00+00:00','2026-10-23T00:01:00+00:00','2026-10-23T04:01:00+00:00'):
                    c.clock[0]=datetime.fromisoformat(moment)
                    daily.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])
            self.assertEqual(observed,['halt_pullback_caps_v2_2026-10-22.sqlite3']*2+['halt_pullback_caps_v2_2026-10-23.sqlite3'])
            self.assertIs(c.provider.market,original_market)
            self.assertIs(c.provider.limits,original_limits)
