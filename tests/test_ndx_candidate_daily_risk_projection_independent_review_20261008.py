from copy import deepcopy
import unittest

from backtest import ndx_candidate_daily_risk_projection_research as subject
import test_ndx_candidate_daily_risk_projection_research as fixtures


def resolve(document, tokens):
    for token in tokens:
        document = document[token]
    return document


class Tests(unittest.TestCase):
    def test_all_locator_tokens_resolve_original_values_and_column_permutation_is_safe(self):
        arguments = fixtures.fixture()
        result = subject.project_path(**arguments)
        state = arguments['stateful_input']
        for index, row in enumerate(result['rows']):
            self.assertEqual(row['daily_index'], index)
            for sid, pointer in row['source_locator_tokens'].items():
                self.assertEqual(resolve({'daily':arguments['daily']},pointer['quantity_tokens']),arguments['daily'][index]['holdings'][sid]['shares'])
                self.assertEqual(resolve(state,pointer['price_tokens']),20 if sid == 'a/1' else 5)
                label = row['diagnostic']['label_observations'][sid]
                self.assertEqual(resolve(state,pointer['label_tokens']),label['label'])
                self.assertLessEqual(label['observation_session'],row['diagnostic']['session'])
        permuted = deepcopy(arguments)
        permuted['stateful_input']['closes']['columns'].reverse()
        for row in permuted['stateful_input']['closes']['data']: row.reverse()
        second = subject.project_path(**permuted)
        self.assertEqual([row['diagnostic'] for row in result['rows']],[row['diagnostic'] for row in second['rows']])

    def test_unknown_new_sid_bad_price_and_duplicate_alias_rejected(self):
        for attack in ('unknown','price_bool','negative','duplicate_alias','empty_future'):
            with self.subTest(attack=attack):
                arguments = fixtures.fixture()
                state = arguments['stateful_input']
                if attack == 'unknown': arguments['daily'][-1]['holdings']['unknown']={'ticker':'COL_A','shares':1}
                elif attack == 'price_bool': state['closes']['data'][-1][1]=True
                elif attack == 'negative': arguments['daily'][-1]['holdings']['a/1']['shares']=-1
                elif attack == 'duplicate_alias': state['internal_columns_by_security']['b']='COL_A'
                else: state['risk_chains_by_decision']={state['calendar'][-1]:{'a/1':'X','b':'Y'}}
                with self.assertRaises(ValueError): subject.project_path(**arguments)


if __name__ == '__main__': unittest.main()
