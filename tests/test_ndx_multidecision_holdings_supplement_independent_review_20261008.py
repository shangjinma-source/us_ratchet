from copy import deepcopy
import json
import unittest

from backtest import ndx_multidecision_holdings_supplement_research as subject
import test_ndx_multidecision_holdings_supplement_research as fixtures


class Tests(unittest.TestCase):
    def test_every_daily_and_risk_row_matches_original_raw_and_deepcopy(self):
        arguments = fixtures.fixture()
        saved = subject.build_supplement(**arguments)
        tables = {table['name']: table['rows'] for table in saved['tables']}
        for row in tables['完整每日原记录']:
            original = arguments['raw_documents'][row[0]][row[1]]
            n = next(i for i, value in enumerate(original['document']['result']['daily']) if value['session'] == row[5])
            self.assertEqual(json.loads(row[6]), original['document']['result']['daily'][n])
            self.assertEqual(json.loads(row[7]), dict(original['reference'], json_pointer=f'/result/daily/{n}'))
        for row in tables['每日原风险与缺口']:
            original = next(day for day in arguments['raw_documents'][row[0]][row[1]]['document']['result']['daily'] if day['session'] == row[5])
            self.assertEqual(None if row[7] is None else json.loads(row[7]), original.get('risk'))
            self.assertEqual(json.loads(row[8]), original.get('risk_chains'))
            self.assertEqual(json.loads(row[9]), original.get('risk_chain_observation_dates'))
        self.assertEqual(sum(row[6] is None for row in tables['每日SID原持仓']), 24)
        saved['original_raw_bundles_preserved']['candidate'][8]['document']['result']['daily'][1]['session'] = 'changed'
        self.assertNotEqual(arguments['raw_documents']['candidate'][8]['document']['result']['daily'][1]['session'], 'changed')

    def test_missing_slots_duplicate_identity_calendar_and_parent_attacks(self):
        for kind in ('slot', 'duplicate', 'calendar', 'parent', 'issuer', 'ticker', 'whole_alias'):
            with self.subTest(kind=kind):
                args = fixtures.fixture()
                if kind == 'slot': args['raw_documents']['control'].pop()
                elif kind == 'duplicate': args['candidate_inputs']['inputs']['rows'][4]['source_slots'] *= 2
                elif kind == 'calendar': args['raw_documents']['candidate'][8]['document']['result']['daily'][1]['session'] = '2100-01-01'
                elif kind == 'parent': args['control_execution']['input_references']['inputs']['sha256'] = 'f'*64; args['references']['control_inputs'] = dict(path='control_inputs',sha256='a'*64)
                elif kind == 'issuer': args['raw_documents']['candidate'][8]['document']['result']['daily'][1]['holdings']['candidate-1']['issuer_id'] = 'wrong'
                elif kind == 'ticker': args['control_inputs']['inputs']['original_control_preserved']['complete_original_definition']['securities'][0]['ticker'] = 'CONTROL_SID_COLUMN_0'
                else: args['raw_documents']['control'][1]['document']['result']['daily'][1]['tickers']['control-0'] = 'wrong'
                with self.assertRaises(ValueError): subject.build_supplement(**args)


if __name__ == '__main__':
    unittest.main()
