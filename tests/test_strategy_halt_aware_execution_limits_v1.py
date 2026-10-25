from hashlib import sha256
import unittest
import test_strategy_account_execution_limits as fixtures
from core.strategy_account_ledger import canonical
from data.strategy_halt_gap_diagnostic_v1 import HEADER,SOURCE_URL
from data.strategy_halt_aware_execution_limits_v1 import build_execution_limits
from data.strategy_halt_aware_pullback_sources_v1 import candidate_from_yahoo_bytes


class HaltLimitsTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ExecutionLimitsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def build(self,package,review,targets):
        class Cap:
            def candidate(self,**kwargs):
                return candidate_from_yahoo_bytes(previous_cap=None,**kwargs)
        return build_execution_limits(state=self.fixture.state,target_quantities=targets,
            market_capture=package,unit_review=review,cap_store=Cap(),now=self.fixture.now.isoformat())

    def test_missing_halt_evidence_blocks_buy_not_sell(self):
        package,review=self.fixture.package()
        with self.assertRaisesRegex(ValueError,'HALT_EXECUTION_EVIDENCE_REQUIRED'):
            self.build(package,review,{'AAA':5})
        result=self.build(package,review,{})
        self.assertEqual(result['limits']['BBB']['sell'],'10')
        self.assertFalse(result['limits']['BBB']['buy_evaluated'])

    def test_both_validation_and_candidate_receive_bound_halt_source(self):
        package,review=self.fixture.package()
        raw=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+'</tr></table>').encode()
        receipt=canonical(dict(url=SOURCE_URL,http_status=200,bytes=len(raw),raw_sha256=sha256(raw).hexdigest(),
            started_at=self.fixture.now.isoformat(),received_at=self.fixture.now.isoformat()))
        package['files'].update({'halt.raw':raw,'halt.receipt':receipt})
        package['source_hashes'].update({key:sha256(value).hexdigest() for key,value in [('halt.raw',raw),('halt.receipt',receipt)]})
        package['halt_evidence']=dict(raw_path='halt.raw',receipt_path='halt.receipt')
        result=self.build(package,review,{'AAA':5})
        self.assertTrue(result['limits']['AAA']['buy_evaluated'])
        self.assertIn('halt.raw',result['limits']['AAA']['source_hashes'])
        self.assertNotIn('halt.raw',result['limits']['BBB']['source_hashes'])
