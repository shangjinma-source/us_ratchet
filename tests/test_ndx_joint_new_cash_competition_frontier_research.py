"""Independent tiny synthetic full-domain oracle, no source/price IO or fit."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from itertools import product
from pathlib import Path
import builtins
import hashlib
import json
import unittest
from unittest.mock import patch

from backtest import ndx_variable_cardinality_new_cash_problem_research as A
from backtest import ndx_joint_new_cash_competition_frontier_research as B


def case(names=('A','B','C')):
    return dict(evidence_facts=dict(conditional_inventory=[dict(security_id=sid,issuer_id='I'+sid,
        ticker=sid,risk_chain='R'+sid) for sid in names]),
        prior_book=dict(holdings={},cash='0',currency='USD',as_of='2026-09-30',cash_includes_event=False),
        cash_event=dict(amount='2',currency='USD',decision_date='2026-09-30',execution_date='2026-10-01',
            available_at='2026-09-30T19:00:00Z'),
        price_context=dict(currency='USD',stage='DECISION_KNOWN_PRICES',decision_at='2026-09-30T20:00:00Z',
            session_timezone='UTC',basis='SYNTHETIC',prices={sid:dict(price='1',lot_size=1,
                available_at='2026-09-30T19:00:00Z',price_date='2026-09-30',basis='SYNTHETIC') for sid in names}),
        policy=dict(risk_parameters=dict(max_single_weight='1',min_single_weight='0',top_weight_cap='1',
            minimum_effective_n_ratio='0',risk_chain_top1_cap='1'),transaction_cost_bps='0',minimum_cash_buffer='0',currency='USD'),
        domain_kind='WHOLE_LOT_QUANTITIES')


def covariance(raw, values=None):
    ids = sorted(raw['price_context']['prices'])
    return dict(schema='EXPLICIT_SYNTHETIC_RATIONAL_COVARIANCE_V1',security_ids=ids,
        values=values if values is not None else [[int(i==j)*(i+1) for j in range(len(ids))] for i in range(len(ids))],
        return_unit='ONE_STEP_DECIMAL_RETURN_SQUARED',available_at='2026-09-30T19:00:00Z',timing_scope='SYNTHETIC_TRAINING_ONLY')


def prepare(raw, cov=None):
    return B.prepare_synthetic_joint_competition(prepared_problem=A.prepare_synthetic_new_cash_problem(synthetic_case=raw),
        synthetic_covariance=covariance(raw) if cov is None else cov)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def resign_A(problem):
    problem['problem_id'] = digest({key:value for key,value in problem.items() if key != 'problem_id'})


def independent_oracle(raw, cov):
    """Read only raw synthetic inputs, independently enumerate all coordinates."""
    facts = raw['evidence_facts']
    metadata = {row['security_id']:row for row in facts['conditional_inventory']+facts.get('frozen_only_securities',[])}
    buys = sorted(row['security_id'] for row in facts['conditional_inventory']
        if row['security_id'] not in facts.get('conditional_exclusions',{}))
    q = {sid:Fraction(value) for sid,value in raw['prior_book']['holdings'].items()}
    prices = {sid:Fraction(row['price']) for sid,row in raw['price_context']['prices'].items()}
    lots = {sid:row['lot_size'] for sid,row in raw['price_context']['prices'].items()}
    cash = Fraction(raw['prior_book']['cash'])+Fraction(raw['cash_event']['amount'])
    buffer = Fraction(raw['policy']['minimum_cash_buffer'])
    factor = 1+Fraction(raw['policy']['transaction_cost_bps'])/10000
    budget = cash-buffer
    wealth = cash+sum((prices[sid]*count for sid,count in q.items()),Fraction(0))
    risk = {key:Fraction(value) for key,value in raw['policy']['risk_parameters'].items()}
    tol = Fraction(1,1000000000)
    if budget < 0:
        return []
    caps = {sid:int(budget/(prices[sid]*lots[sid]*factor)) for sid in buys}
    records = []
    for rank,counts in enumerate(product(*(range(caps[sid]+1) for sid in buys))):
        increments = dict(zip(buys,counts))
        final = {sid:q.get(sid,0)+lots[sid]*increments.get(sid,0) for sid in metadata}
        active = {sid:count for sid,count in final.items() if count>0}
        gross = sum((prices[sid]*lots[sid]*n for sid,n in increments.items()),Fraction(0))
        fee = gross*(factor-1)
        cash_after = cash-gross-fee
        stock = sum((prices[sid]*count for sid,count in active.items()),Fraction(0))
        weights = {sid:prices[sid]*count/stock for sid,count in active.items()} if stock else {}
        unique = len({metadata[sid]['issuer_id'] for sid in active}) == len(active)
        checks = [None]*5
        if weights:
            ordered = sorted(weights.values(),reverse=True)
            chains = {}
            for sid,value in weights.items():
                chain = metadata[sid]['risk_chain']
                chains[chain] = chains.get(chain,Fraction(0))+value
            checks = [max(ordered)<=risk['max_single_weight']+tol,
                min(ordered)>=risk['min_single_weight']-tol,
                sum(ordered[:3])<=risk['top_weight_cap']+tol,
                1/sum(value*value for value in ordered)>=risk['minimum_effective_n_ratio']*len(ordered)-tol,
                max(chains.values())<=risk['risk_chain_top1_cap']+tol]
        if not unique:
            category = 'ISSUER_CONFLICT'
        elif cash_after < buffer:
            category = 'CASH_REJECTED'
        elif not weights:
            category = 'ALL_CASH_CONTROL'
        elif not all(checks):
            category = 'RISK_REJECTED'
        else:
            category = 'FEASIBLE'
        objectives = None
        if category == 'FEASIBLE':
            vector = [weights.get(sid,Fraction(0)) for sid in cov['security_ids']]
            variance = sum((vector[i]*Fraction(cov['values'][i][j])*vector[j]
                for i in range(len(vector)) for j in range(len(vector))),Fraction(0))
            objectives = (variance,gross/wealth)
        records.append(dict(rank=rank,increments=increments,final=final,weights=weights,category=category,
            objectives=objectives,gross=gross,fee=fee,cash=cash_after,stock=stock,k=len(active),checks=checks,
            issuer_unique=unique,wealth=wealth))
    return records


def nondominated(records):
    feasible = [row for row in records if row['category']=='FEASIBLE']
    result = set()
    for row in feasible:
        dominated = False
        for other in feasible:
            if (all(left<=right for left,right in zip(other['objectives'],row['objectives']))
                and any(left<right for left,right in zip(other['objectives'],row['objectives']))):
                dominated = True
                break
        if not dominated:
            result.add(row['rank'])
    return result


class JointFrontierTests(unittest.TestCase):
    def assert_full_oracle(self, raw, cov=None):
        cov = covariance(raw) if cov is None else cov
        competition = prepare(raw,cov)
        expected = independent_oracle(raw,cov)
        result = B.run_synthetic_joint_frontier(competition=competition,work_budget=len(expected)+1)
        self.assertEqual(result['status'],'COMPLETE_SYNTHETIC_INTEGER_DOMAIN')
        self.assertEqual(len(result['classified_records']),len(expected))
        for actual,oracle in zip(result['classified_records'],expected):
            self.assertEqual(actual['rank'],oracle['rank'])
            self.assertEqual(actual['buy_lots'],oracle['increments'])
            self.assertEqual({sid:Fraction(value) for sid,value in actual['final_quantities'].items()},oracle['final'])
            self.assertEqual({sid:Fraction(value) for sid,value in actual['weights'].items()},oracle['weights'])
            self.assertEqual(actual['category'],oracle['category'])
            self.assertEqual(actual['issuer_unique'],oracle['issuer_unique'])
            self.assertEqual(list(actual['risk_checks'].values()),oracle['checks'])
            for key,expected_value in [('actual_buy_notional',oracle['gross']),('actual_fee',oracle['fee']),
                    ('remaining_cash',oracle['cash']),('final_stock_value',oracle['stock'])]:
                self.assertEqual(Fraction(actual[key]),expected_value)
            self.assertEqual(oracle['stock']+oracle['cash'],oracle['wealth']-oracle['fee'])
            self.assertEqual(None if actual['training_objectives'] is None else tuple(map(Fraction,actual['training_objectives'])),oracle['objectives'])
        for row in result['all_k_frontiers']:
            k = row['holding_count']
            compatible = [record for record in expected if record['k']==k and record['issuer_unique']]
            self.assertEqual(int(row['issuer_compatible_quantity_box_count']),len(compatible))
            self.assertEqual(int(row['processed_quantity_count']),len(compatible))
            self.assertEqual(row['unsearched_quantity_count'],'0')
            self.assertEqual({record['rank'] for record in row['training_frontier']},nondominated(compatible))
            self.assertEqual(int(row['feasible_full_domain_count_or_null']),sum(record['category']=='FEASIBLE' for record in compatible))
        self.assertEqual({record['rank'] for record in result['overall_training_frontier']},nondominated(expected))
        self.assertEqual(int(result['coverage']['raw_quantity_box_count']),len(expected))
        self.assertEqual(int(result['coverage']['issuer_incompatible_box_count']),sum(not record['issuer_unique'] for record in expected))
        self.assertFalse(result['coverage']['training_dominance_used_to_prune_economic_domain'])
        return competition,result,expected

    def test_full_three_issuer_domain_scores_and_all_frontiers(self):
        competition,result,expected = self.assert_full_oracle(case())
        self.assertEqual(len(expected),27)
        self.assertEqual([int(row['issuer_compatible_quantity_box_count']) for row in result['all_k_frontiers']],[6,12,8])
        self.assertEqual(result['all_cash_control']['training_objectives'],None)
        self.assertTrue(all(value is None for value in result['all_cash_control']['risk_checks'].values()))
        self.assertEqual(result['zero_buy_control']['positive_holding_count'],0)
        self.assertEqual(competition['core']['pretrade_wealth'],'2')

    def test_cash_event_once_fractional_old_lots_fees_buffer(self):
        raw = case()
        raw['prior_book'].update(holdings={'A':'0.5'},cash='1')
        raw['cash_event']['amount'] = '3'
        raw['policy'].update(transaction_cost_bps='1000',minimum_cash_buffer='1')
        raw['price_context']['prices']['A']['price'] = '2'
        raw['price_context']['prices']['B'].update(price='2',lot_size=1)
        competition,result,expected = self.assert_full_oracle(raw)
        self.assertEqual(competition['core']['pretrade_wealth'],'5')
        self.assertEqual(competition['core']['cash'],'4')
        for record in expected:
            self.assertEqual((record['final']['A']-Fraction(1,2))%1,0)
            if record['objectives'] is not None:
                self.assertEqual(record['objectives'][1],record['gross']/5)
        self.assertEqual(result['zero_buy_control']['final_quantities']['A'],'1/2')

    def test_share_class_locks_old_ineligible_and_weighted_per_k_counts(self):
        raw = case(('A','AA','B','C'))
        raw['evidence_facts']['conditional_inventory'][1]['issuer_id'] = 'IA'
        raw['prior_book']['holdings'] = {'A':'0.5'}
        raw['evidence_facts']['conditional_exclusions'] = {'A':'INELIGIBLE_OLD'}
        _,result,expected = self.assert_full_oracle(raw)
        self.assertTrue(all(record['final']['A']==Fraction(1,2) for record in expected))
        self.assertTrue(any(record['category']=='ISSUER_CONFLICT' for record in expected))
        self.assertTrue(all(record['final']['AA']==0 for record in expected if record['category']=='FEASIBLE'))
        self.assertEqual([int(row['issuer_compatible_quantity_box_count']) for row in result['all_k_frontiers']],[1,4,4])
        self.assertIsNone(result['all_cash_control'])
        raw['prior_book']['holdings']['AA'] = '0.25'
        _,result,expected = self.assert_full_oracle(raw)
        self.assertTrue(all(row['issuer_compatible_quantity_box_count']=='0' for row in result['all_k_frontiers']))
        self.assertTrue(all(record['category']=='ISSUER_CONFLICT' for record in expected))

    def test_frozen_only_old_sid_and_odd_lot(self):
        raw = case(('B','C'))
        raw['evidence_facts']['frozen_only_securities'] = [dict(security_id='A',issuer_id='IA',ticker='A',risk_chain='RA')]
        raw['prior_book']['holdings'] = {'A':'0.125'}
        raw['price_context']['prices']['A'] = deepcopy(raw['price_context']['prices']['B'])
        raw['price_context']['prices']['B']['lot_size'] = 2
        _,result,expected = self.assert_full_oracle(raw)
        self.assertTrue(all(row['final']['A']==Fraction(1,8) for row in expected))
        self.assertNotIn('A',result['classified_records'][0]['buy_lots'])

    def test_equal_objective_actions_are_all_retained(self):
        raw = case()
        _,result,_ = self.assert_full_oracle(raw,covariance(raw,[[1,1,1],[1,1,1],[1,1,1]]))
        rows = {row['holding_count']:row for row in result['all_k_frontiers']}
        self.assertEqual(len(rows[1]['training_frontier']),3)
        self.assertEqual(len(rows[2]['training_frontier']),3)
        self.assertEqual(len(result['overall_training_frontier']),3)
        self.assertEqual(len({tuple(row['training_objectives']) for row in rows[1]['training_frontier']}),1)

    def test_preselected_target_omits_better_issuer_and_l1_can_be_strictly_worse(self):
        raw = case()
        raw['prior_book']['holdings'] = {'A':1}
        raw['cash_event']['amount'] = '1'
        # A/B saved target is not passed to the production API.
        _,result,expected = self.assert_full_oracle(raw,covariance(raw,[[4,0,0],[0,4,0],[0,0,0]]))
        buy_b = next(row for row in expected if row['increments']=={'A':0,'B':1,'C':0})
        buy_c = next(row for row in expected if row['increments']=={'A':0,'B':0,'C':1})
        target = {'A':Fraction(1,2),'B':Fraction(1,2),'C':Fraction(0)}
        l1 = lambda row:sum(abs(row['weights'].get(sid,0)-weight) for sid,weight in target.items())
        self.assertLess(l1(buy_b),l1(buy_c))
        self.assertGreater(buy_b['objectives'][0],buy_c['objectives'][0])
        self.assertEqual(buy_b['objectives'][1],buy_c['objectives'][1])
        k2 = next(row for row in result['all_k_frontiers'] if row['holding_count']==2)
        self.assertEqual({row['rank'] for row in k2['training_frontier']},{buy_c['rank']})
        self.assertIn(buy_b['rank'],{row['rank'] for row in result['classified_records']})
        self.assertEqual(k2['economic_CAGR_DD_frontier_status'],'NOT_EVALUATED')

    def test_budget_zero_resume_chunks_equal_one_shot(self):
        competition = prepare(case())
        full = B.run_synthetic_joint_frontier(competition=competition,work_budget=100)
        for budget in (1,2,5,9,27):
            with self.subTest(budget=budget):
                result = B.run_synthetic_joint_frontier(competition=competition,work_budget=0)
                self.assertEqual(result['status'],'BUDGET_STOPPED')
                self.assertEqual(result['coverage']['newly_classified_tuples'],0)
                self.assertEqual(result['coverage']['unsearched_raw_quantity_count'],'27')
                while result['status'] == 'BUDGET_STOPPED':
                    prior_cursor = result['resume_state']['cursor']
                    result = B.run_synthetic_joint_frontier(competition=competition,work_budget=budget,
                        resume_state=json.loads(json.dumps(result['resume_state'])),expected_resume_sha256=result['resume_sha256'])
                    self.assertLessEqual(result['coverage']['newly_classified_tuples'],budget)
                    self.assertEqual(result['coverage']['resume_prefix_validation_tuples'],prior_cursor)
                    for row in result['all_k_frontiers']:
                        self.assertEqual(int(row['processed_quantity_count'])+int(row['unsearched_quantity_count']),
                            int(row['issuer_compatible_quantity_box_count']))
                self.assertEqual(result['resume_state'],full['resume_state'])
                self.assertEqual(result['all_k_frontiers'],full['all_k_frontiers'])
                self.assertEqual(result['overall_training_frontier'],full['overall_training_frontier'])

    def test_resume_tampering_self_rehash_wrong_problem_and_bool_rejected(self):
        competition = prepare(case())
        partial = B.run_synthetic_joint_frontier(competition=competition,work_budget=5)
        original = partial['resume_state']
        attacks = (
            lambda state:state.update(cursor=6),
            lambda state:state.update(cursor=-1),
            lambda state:state.update(cursor=True),
            lambda state:state.update(cursor=28),
            lambda state:state.update(prefix_hash='a'*64),
            lambda state:state['per_k']['1'].update(processed=999),
            lambda state:state['per_k']['1'].update(processed=True),
            lambda state:state['classified_records'].pop(),
            lambda state:state['classified_records'].append(deepcopy(state['classified_records'][0])),
            lambda state:state['classified_records'][1].update(actual_fee='999'),
            lambda state:state.update(unrecognized='extra'))
        for index,attack in enumerate(attacks):
            with self.subTest(index=index):
                state = deepcopy(original)
                attack(state)
                with self.assertRaises(ValueError):
                    B.run_synthetic_joint_frontier(competition=competition,work_budget=2,resume_state=state,
                        expected_resume_sha256=digest(state))
        with self.assertRaisesRegex(ValueError,'digest drift'):
            B.run_synthetic_joint_frontier(competition=competition,work_budget=1,resume_state=original,expected_resume_sha256='0'*64)
        with self.assertRaises(ValueError):
            B.run_synthetic_joint_frontier(competition=competition,work_budget=1,resume_state=original)
        other = case()
        other['cash_event']['amount'] = '3'
        with self.assertRaisesRegex(ValueError,'binding mismatch'):
            B.run_synthetic_joint_frontier(competition=prepare(other),work_budget=1,resume_state=original,
                expected_resume_sha256=partial['resume_sha256'])

    def test_complete_state_replay_and_frontier_loss_attacks(self):
        competition = prepare(case())
        full = B.run_synthetic_joint_frontier(competition=competition,work_budget=100)
        resumed = B.run_synthetic_joint_frontier(competition=competition,work_budget=0,
            resume_state=full['resume_state'],expected_resume_sha256=full['resume_sha256'])
        self.assertEqual(resumed['resume_state'],full['resume_state'])
        self.assertEqual(resumed['coverage']['newly_classified_tuples'],0)
        state = deepcopy(full['resume_state'])
        state['per_k']['1']['frontier'].pop()
        with self.assertRaisesRegex(ValueError,'prefix replay mismatch'):
            B.run_synthetic_joint_frontier(competition=competition,work_budget=1,resume_state=state,expected_resume_sha256=digest(state))

    def test_lazy_raw_rank_stream_and_bad_ranks(self):
        competition = prepare(case())
        stream = B.iter_synthetic_quantity_candidates(competition=competition,start_rank=0)
        self.assertEqual(next(stream)['buy_lots'],{'A':0,'B':0,'C':0})
        self.assertEqual(next(stream)['buy_lots'],{'A':0,'B':0,'C':1})
        self.assertEqual([row['rank'] for row in B.iter_synthetic_quantity_candidates(competition=competition,start_rank=25)],[25,26])
        self.assertEqual(list(B.iter_synthetic_quantity_candidates(competition=competition,start_rank=27)),[])
        for rank in (True,-1,28,0.0):
            with self.assertRaises(ValueError):
                next(B.iter_synthetic_quantity_candidates(competition=competition,start_rank=rank))

    def test_zero_wealth_rejected_and_negative_budget_empty_failed_control(self):
        raw = case()
        raw['cash_event']['amount'] = '0'
        with self.assertRaisesRegex(ValueError,'Positive pretrade total wealth'):
            prepare(raw)
        raw = case()
        raw['policy']['minimum_cash_buffer'] = '3'
        competition,result,expected = self.assert_full_oracle(raw)
        self.assertEqual(expected,[])
        self.assertIsNone(competition['core']['caps'])
        self.assertEqual(result['coverage']['raw_quantity_box_count'],'0')
        self.assertEqual(result['zero_buy_control']['category'],'CASH_REJECTED')
        self.assertEqual(result['zero_buy_control']['remaining_cash'],'2')
        self.assertEqual(result['zero_buy_control']['training_objectives'],None)
        self.assertEqual(result['coverage']['all_cash_processed'],'0')
        self.assertEqual(result['stop_certificate']['claim'],'EMPTY_FEASIBLE_DOMAIN_NEGATIVE_CASH_BUDGET_CERTIFICATE')
        self.assertEqual(result['stop_certificate']['empty_domain_proof'],dict(left='0',comparison='>',right='-1',
            reason='NONNEGATIVE_BUY_COST_EXCEEDS_NEGATIVE_AVAILABLE_BUDGET'))

    def test_exact_psd_singular_zero_pivot_and_negative_offdiagonal(self):
        raw = case()
        for matrix in ([[0,0,0],[0,1,1],[0,1,1]],[[1,-1,0],[-1,1,0],[0,0,0]],
                [[0,0,0],[0,0,0],[0,0,0]],
                [['1/3','1/6',0],['1/6','1/3',0],[0,0,Decimal('0.1')]]):
            self.assert_full_oracle(raw,covariance(raw,matrix))
        for matrix in ([[0,1,0],[1,1,0],[0,0,1]],[[1,2,0],[2,1,0],[0,0,1]],
                [[-1,0,0],[0,1,0],[0,0,1]],[[1,1,0],[0,1,0],[0,0,1]]):
            with self.assertRaises(ValueError):
                prepare(raw,covariance(raw,matrix))

    def test_numeric_resource_limits_before_exponent_materialization(self):
        raw = case()
        for value in ('1e999999999','1e-999999999',Decimal('1e999999999'),Fraction(2**600,1),2**600):
            cov = covariance(raw)
            cov['values'][0][0] = value
            with self.assertRaisesRegex(ValueError,'resource limit'):
                prepare(raw,cov)

    def test_small_matrix_oracle_all_risk_checks_counts_frontiers(self):
        contexts = 0
        for fee,buffer,old,lot,shared in product(('0','500'),('0','1'),('0','0.5'),(1,2),(False,True)):
            raw = case()
            raw['policy'].update(transaction_cost_bps=fee,minimum_cash_buffer=buffer)
            raw['policy']['risk_parameters'].update(max_single_weight='0.7',min_single_weight='0.1',
                top_weight_cap='1',minimum_effective_n_ratio='0.7',risk_chain_top1_cap='0.8')
            raw['prior_book']['holdings'] = {'A':old}
            raw['price_context']['prices']['B']['lot_size'] = lot
            if shared:
                raw['evidence_facts']['conditional_inventory'][1]['risk_chain'] = 'RA'
            self.assert_full_oracle(raw)
            contexts += 1
        self.assertEqual(contexts,32)

    def test_original_risk_not_relaxed_by_synthetic_frontier(self):
        raw = case()
        raw['policy']['risk_parameters'].update(max_single_weight='0.45',min_single_weight='0.05',
            top_weight_cap='0.8',minimum_effective_n_ratio='0.7',risk_chain_top1_cap='0.55')
        _,result,expected = self.assert_full_oracle(raw)
        self.assertEqual(result['overall_training_frontier'],[])
        self.assertTrue(all(record['category']!='FEASIBLE' for record in expected))

    def test_A_self_rehash_cannot_forge_consumed_mathematical_fields(self):
        raw = case()
        original = A.prepare_synthetic_new_cash_problem(synthetic_case=raw)
        mutations = (
            lambda a:a['domain_formula']['coordinate_caps_or_null'].update(A=99),
            lambda a:a['domain_formula']['coordinate_caps_or_null'].update(A=True),
            lambda a:a['domain_formula'].update(old_stock_value='999'),
            lambda a:a['domain_formula'].update(total_cash_before_buys='4'),
            lambda a:a['domain_formula'].update(fee_factor='2'),
            lambda a:a['all_k_rows'][0].update(full_conditional_composition_count='999'),
            lambda a:a['conditional_inventory'].update(security_count=999),
            lambda a:a['policy'].update(risk_tolerance='0.1'),
            lambda a:a.update(qualified_inventory_or_null=[]),
            lambda a:a['authority'].update(execution_authorized=True))
        for index,mutate in enumerate(mutations):
            with self.subTest(index=index):
                forged = deepcopy(original)
                mutate(forged)
                resign_A(forged)
                with self.assertRaises(ValueError):
                    B.prepare_synthetic_joint_competition(prepared_problem=forged,synthetic_covariance=covariance(raw))

    def test_context_covariance_units_float_late_and_source_claims_rejected_or_unbound(self):
        raw = case()
        for mutate in (lambda c:c.update(security_ids=['A','B']),lambda c:c.update(timing_scope='EVALUATION'),
                lambda c:c.update(available_at='2026-10-01T00:00:00Z'),lambda c:c.update(return_unit='PERCENT'),
                lambda c:c['values'][0].__setitem__(0,True),lambda c:c['values'][0].__setitem__(0,0.1),
                lambda c:c['values'][0].__setitem__(0,Decimal('NaN')),lambda c:c.update(extra=True)):
            cov = covariance(raw)
            mutate(cov)
            with self.assertRaises(ValueError):
                prepare(raw,cov)
        late = case()
        late['price_context']['prices']['A']['available_at'] = '2026-10-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'context blocked'):
            prepare(late)
        conditional = A.prepare_new_cash_problem(**case())
        with self.assertRaisesRegex(ValueError,'Synthetic UNBOUND'):
            B.prepare_synthetic_joint_competition(prepared_problem=conditional,synthetic_covariance=covariance(raw))

    def test_no_source_IO_no_fit_and_continuous_remains_unknown(self):
        raw = case()
        problem = A.prepare_synthetic_new_cash_problem(synthetic_case=raw)
        cov = covariance(raw)
        with (patch.object(builtins,'open',side_effect=AssertionError('No source IO')),
              patch.object(Path,'read_bytes',side_effect=AssertionError('No price/source IO'))):
            competition = B.prepare_synthetic_joint_competition(prepared_problem=problem,synthetic_covariance=cov)
            result = B.run_synthetic_joint_frontier(competition=competition,work_budget=100)
        self.assertTrue(all(value is False for value in result['authority'].values()))
        self.assertEqual(result['continuous']['status'],'NOT_IMPLEMENTED')
        self.assertEqual(result['continuous']['weight_domain'],'UNCOUNTABLE')
        self.assertEqual(result['continuous']['unsearched_regions'],'UNKNOWN')
        self.assertEqual(result['real_objective_status'],'UNREGISTERED')
        self.assertEqual(result['plan_rows'],[])
        self.assertIsNone(result['current_account'])
        self.assertIsNone(result['current_new_money'])
        raw['domain_kind'] = 'CONTINUOUS_INCREMENTAL_DOLLARS'
        with self.assertRaisesRegex(ValueError,'continuous remains UNKNOWN'):
            prepare(raw)

    def test_competition_mutation_deepcopy_and_budget_types(self):
        raw = case()
        competition = prepare(raw)
        original = deepcopy(competition)
        result = B.run_synthetic_joint_frontier(competition=competition,work_budget=1)
        result['classified_records'][0]['final_quantities']['A'] = '99'
        self.assertEqual(competition,original)
        for budget in (True,-1,1.0):
            with self.assertRaises(ValueError):
                B.run_synthetic_joint_frontier(competition=competition,work_budget=budget)
        for mutate in (lambda c:c['core'].update(pretrade_wealth='99'),lambda c:c.update(extra=True),
                lambda c:c['authority'].update(winner_selected=True)):
            modified = deepcopy(competition)
            mutate(modified)
            modified['competition_id'] = digest({k:v for k,v in modified.items() if k!='competition_id'})
            with self.assertRaises(ValueError):
                B.run_synthetic_joint_frontier(competition=modified,work_budget=1)


if __name__ == '__main__':
    unittest.main()
