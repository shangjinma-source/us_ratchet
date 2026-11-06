from copy import deepcopy
import unittest
from test_strategy_account_archived_holding_charts import ArchivedHoldingTests


class ProfiledChartCompatibilityTests(ArchivedHoldingTests):
    def test_profiled_archive_legacy_saved_target_and_bootstrap(self):
        self.archive['schema'] = 'PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1'
        self.assertEqual(self.bars(self.charts(self.configuration))['ticker'], 'AAA')
        self.target(self.configuration, 'saved')
        self.assertEqual(self.bars(self.charts())['ticker'], 'AAA')

    def test_profiled_configuration_and_same_ticker_wrong_sid(self):
        from data.strategy_continuous32_runtime import RUNTIME_PATHS
        from data.strategy_continuous32_target_decision import PROFILE_ID
        import json
        self.configuration.update(schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1', selector_profile=PROFILE_ID,
                                  runtime_pins={p:'3'*64 for p in RUNTIME_PATHS})
        self.archive={'schema':'PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1','entries':[]}
        self.add('profile.json', self.configuration)
        self.assertEqual(self.bars(self.charts(self.configuration))['ticker'], 'AAA')
        manifest=json.loads((self.root/'manifest.json').read_bytes())
        manifest['candidates'][0]['security_id']='sid:OTHER'
        self.configuration['training_sha256']=self.put('manifest.json', manifest)
        self.archive['entries']=[];self.add('wrong-sid.json', self.configuration)
        with self.assertRaisesRegex(ValueError, 'HOLDING_CHART_APPROVED_SOURCE_REQUIRED'):
            self.bars(self.charts(self.configuration))

    def test_unknown_archive_and_mutated_archive_rejected(self):
        self.archive['schema'] = 'UNKNOWN'
        with self.assertRaisesRegex(ValueError, 'INVALID_RUNTIME_ARCHIVE'):
            self.bars(self.charts(self.configuration))
        self.archive['schema'] = 'PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1'
        charts = self.charts(self.configuration)
        (self.root/'archive.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'CHART_SOURCE_CHANGED'):
            self.bars(charts)

if __name__ == '__main__': unittest.main()
