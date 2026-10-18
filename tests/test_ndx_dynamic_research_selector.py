import unittest
from backtest.ndx_dynamic_research_selector import select_research_lane


def record(job, k, value, **changes):
    result = dict(task=dict(source_batch='segment_a', universe_track='research',
        selection_date='2024-02-01', decision_data_end='2024-01-31',
        job_id=job, holding_count=k, tickers=';'.join('T'+str(n) for n in range(k)),
        weight_spec='equal_weight'), status='EVALUATED',
        result=dict(return_p50=value, return_p10=value, max_drawdown_p50=.1,
                    max_drawdown_p90=.2, target_012922_distance=.1,
                    declared_constraints_passed=False, whole_lot_executable_all_windows=False),
        eligibility=dict(fractional_risk_passed=True, liquidity_passed=True, technology_scope_passed=True),
        training_semantics_sha256='a'*64)
    result['result'].update({key:result['task'][key] for key in ('tickers','holding_count','weight_spec')})
    result.update(changes)
    return result


def expected(day='2024-02-01', count=2):
    return dict(source_batch='segment_a', universe_track='research', selection_date=day,
                expected_task_count=count,decision_data_end='2024-01-31',training_semantics_sha256='a'*64)


class ResearchSelectorTests(unittest.TestCase):
    def test_variable_k_and_old_whole_lot_failure_not_gate(self):
        output = select_research_lane(expected_dates=[expected()],
            records=[record('a',4,.2),record('b',11,.4)],policy_role='RETURN')
        self.assertEqual(output['rows'][0]['selected']['task']['holding_count'],11)
        self.assertFalse(output['promotion_allowed'])
        self.assertTrue(output['cutoff_refit_required'])

    def test_no_delta_and_missing_date_preserved(self):
        output = select_research_lane(expected_dates=[expected(count=0),expected('2024-03-01',1)],
                                     records=[],policy_role='RETURN')
        self.assertEqual([row['status'] for row in output['rows']],['NO_DELTA','INPUT_INVALID'])
        self.assertFalse(output['implicit_carry_forward'])

    def test_missing_eligibility_does_not_select(self):
        output = select_research_lane(expected_dates=[expected(count=1)],
            records=[record('a',4,.2,eligibility={})],policy_role='RETURN')
        self.assertEqual(output['rows'][0]['status'],'NO_ELIGIBLE_CANDIDATE')

    def test_malformed_eligibility_preserves_invalid_date(self):
        for value in (None,[]):
            output=select_research_lane(expected_dates=[expected(count=1)],
                records=[record('a',4,.2,eligibility=value)],policy_role='RETURN')
            self.assertEqual(output['rows'][0]['status'],'INPUT_INVALID')

    def test_invalid_metric_invalidates_date_not_silent_fallback(self):
        bad = record('a',4,.2)
        bad['result']['return_p50'] = float('nan')
        output = select_research_lane(expected_dates=[expected()],
            records=[bad,record('b',5,.1)],policy_role='RETURN')
        self.assertEqual(output['rows'][0]['status'],'INPUT_INVALID')
        self.assertIsNone(output['rows'][0]['selected'])

    def test_preference_reference_preserved_without_replacement(self):
        preference = record('p',4,.1,eligibility={})
        preference['task']['tickers']='AMAT;AVGO;CDNS;GOOG'
        preference['result']['tickers']=preference['task']['tickers']
        output = select_research_lane(expected_dates=[expected()],
            records=[preference,record('b',11,.9)],policy_role='USER_PREFERENCE')
        self.assertEqual(output['rows'][0]['selected']['task']['job_id'],'p')
        self.assertEqual(output['rows'][0]['selected']['eligibility'],{})

    def test_incomparable_or_malformed_record_invalidates_date(self):
        for field,value in [('decision_data_end','2023-01-31'),('weight_spec','FAKE'),('weight_spec',None)]:
            bad=record('a',4,.9)
            if value is None:
                del bad['task'][field]
            else:
                bad['task'][field]=value
            output=select_research_lane(expected_dates=[expected()],records=[bad,record('b',5,.1)],policy_role='RETURN')
            self.assertEqual(output['rows'][0]['status'],'INPUT_INVALID')
        bad=record('a',4,.9)
        bad['training_semantics_sha256']='b'*64
        output=select_research_lane(expected_dates=[expected(count=1)],records=[bad],policy_role='RETURN')
        self.assertEqual(output['rows'][0]['status'],'INPUT_INVALID')


if __name__ == '__main__':
    unittest.main()
