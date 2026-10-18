import unittest
from copy import deepcopy
from unittest.mock import patch
from test_ndx_single_replacement_domain_research import fixture
from backtest import ndx_single_replacement_domain_research as domain
from backtest import ndx_single_replacement_execution_registration_research as m


def fixture_plan():
    args = fixture()
    base = args['original_rows'][0]
    args['original_rows'] = []
    for i in range(40):
        row = deepcopy(base); row['input_row']['scenario_id'] = 'case'+str(i)
        row['input_reference']['json_pointer'] = '/rows/'+str(i)
        args['original_rows'].append(row)
    args['action_contract']['expected_scenario_ids'] = ['case'+str(i) for i in range(40)]
    prepared = domain.prepare_single_replacement_domain(**args)
    return dict(prepared=prepared, preparation_reference={'path':'saved/prep.json','sha256':'a'*64},
                preparation_audit_reference={'path':'saved/audit.json','sha256':'b'*64},
                evaluator_reference={'path':'saved/evaluator.py','sha256':m.EVALUATOR_SHA}, shard_size=32)


class Tests(unittest.TestCase):
    def test_complete_original_partition_and_frozen_shard_identity(self):
        a = fixture_plan(); before = deepcopy(a)
        with patch.object(domain, 'unrank', side_effect=AssertionError('No enumeration')):
            r = m.build_execution_registration(**a)
        self.assertEqual(a, before)
        d = r['document']; self.assertEqual(d['scenario_count'],40)
        self.assertEqual(d['integer_count'], 560)
        expected = domain.shard_page(a['prepared'],shard_size=32,shard_start=0,shard_stop=18)
        self.assertEqual(d['shards'],expected['shards'])
        self.assertEqual(d['shards'][-1]['identity']['stop'],560)

    def test_resigned_partition_and_boolean_rejected(self):
        for attack in ('count','gap','ordinal','size','evaluator'):
            a = fixture_plan(); d = a['prepared']['document']
            if attack == 'count': d['integer_count'] -= 1
            elif attack == 'gap': d['cases'][-1]['pairs'][-1]['first_global_ordinal'] += 1
            elif attack == 'ordinal': d['cases'][0]['scenario_index'] = False
            elif attack == 'size': a['shard_size'] = True
            else: a['evaluator_reference']['sha256'] = 'c'*64
            a['prepared']['content_sha256'] = m.digest(d)
            with self.subTest(attack=attack),self.assertRaises(ValueError): m.build_execution_registration(**a)

    def test_failed_and_unknown_prefix_never_retry_or_shrink(self):
        r = m.build_execution_registration(**fixture_plan())
        rows = [dict(global_ordinal=0,outcome='INFEASIBLE'),dict(global_ordinal=1,outcome='EVALUATION_EXCEPTION')]
        out = m.summarize_execution_prefix(registration=r,terminal_rows=rows)
        self.assertEqual(out['undispatched_count'],558)
        unknown = m.summarize_execution_prefix(registration=r,terminal_rows=rows[:1],unresolved_ordinal=1)
        self.assertEqual(unknown['undispatched_start'],2)
        for bad in (rows+[dict(global_ordinal=2,outcome='FEASIBLE')],[dict(global_ordinal=1,outcome='FEASIBLE')]):
            with self.assertRaises(ValueError): m.summarize_execution_prefix(registration=r,terminal_rows=bad)


if __name__ == '__main__': unittest.main()
