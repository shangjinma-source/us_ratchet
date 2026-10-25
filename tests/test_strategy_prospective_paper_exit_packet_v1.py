from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_prospective_paper_exit_packet_v1 import CODE_PATHS, apply_paper_exit_packet
from test_strategy_prospective_paper_integration_v1 import fixture
from test_monthly_cap_topup_packet import packet, target


class PaperExitTests(unittest.TestCase):
    def test_exit_survives_rebound_restart_and_same_month_reset_attempt(self):
        with TemporaryDirectory() as folder:
            daily = fixture(folder, extra_code_paths=CODE_PATHS)
            before = deepcopy(daily)
            selected = daily['selection_result']
            raw = json.dumps(packet(target(20000, {'B': 20}), {'B': [1000, 800, 1100]}))
            for old, new in [('2026-10-20', '2026-11-02'),
                             ('2026-10-21', '2026-11-03'), ('2026-10-22', '2026-11-04')]:
                raw = raw.replace(old, new)
            inputs = json.loads(raw)
            inputs['base_target']['origin_reference'] = selected['decision_id']
            store = MonthlyPeakExitStore(Path(folder) / 'independent-risk.sqlite')
            args = dict(selection_result=selected, selection_arguments=daily['selection_arguments'],
                        inputs=inputs, risk_store=store, decision_date='2026-11-02',
                        expected_previous_session=None)
            result = apply_paper_exit_packet(**args)
            self.assertEqual(result['monthly_cap_view']['target_quantities'], {'B': 10})
            self.assertEqual(result['effective_target_quantities'], {'B': 0})
            self.assertEqual(daily, before)
            self.assertIsNone(store.read(daily['book']['account_id']))
            args.update(risk_store=MonthlyPeakExitStore(store.path), expected_previous_session='2026-11-04')
            self.assertEqual(apply_paper_exit_packet(**args)['effective_target_quantities'], {'B': 0})
            # A separately verified same-month selection changes the baseline,
            # not the registration or the already triggered exit.
            second_folder = Path(folder) / 'reselected'
            second_folder.mkdir()
            second = fixture(second_folder, monthly_price='500', extra_code_paths=CODE_PATHS)
            reselected_inputs = deepcopy(inputs)
            reselected_inputs['base_target']['origin_reference'] = second['selection_result']['decision_id']
            revised = apply_paper_exit_packet(**dict(args,
                selection_result=second['selection_result'],
                selection_arguments=second['selection_arguments'], inputs=reselected_inputs))
            self.assertEqual(revised['risk_namespace'], result['risk_namespace'])
            self.assertEqual(revised['monthly_cap_view']['target_quantities'], {'B': 20})
            self.assertEqual(revised['effective_target_quantities'], {'B': 0})
            saved = store.read(result['risk_namespace'])
            with self.assertRaisesRegex(ValueError, 'SAME_MONTH_RESET_FORBIDDEN'):
                apply_paper_exit_packet(**dict(args, decision_date='2026-11-03',
                                              authorized_monthly_reset='2026-11-03'))
            missing = deepcopy(inputs)
            missing['histories']['B']['closes'].pop(1)
            with self.assertRaises(ValueError):
                apply_paper_exit_packet(**dict(args, inputs=missing))
            self.assertEqual(store.read(result['risk_namespace']), saved)


if __name__ == '__main__':
    unittest.main()
