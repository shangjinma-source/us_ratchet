"""Independent bounded rational microdomains; no real portfolio/economic run."""
import builtins
from copy import deepcopy
from fractions import Fraction as F
from itertools import combinations, product
from pathlib import Path
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from backtest import ndx_variable_cardinality_new_cash_problem_research as subject

def inputs():
    ids=[('X','I0','R0'),('XA','I0','R0'),('Y','I1','R1'),('Z','I2','R1')]
    return dict(evidence_facts={'conditional_inventory':[dict(security_id=s,issuer_id=i,ticker=s,risk_chain=r) for s,i,r in ids]},
        prior_book=dict(holdings={},cash='0',currency='USD',as_of='2026-09-30',cash_includes_event=False),
        cash_event=dict(amount='4',currency='USD',decision_date='2026-09-30',execution_date='2026-10-01',available_at='2026-09-30T18:00:00Z'),
        price_context=dict(currency='USD',stage='DECISION_KNOWN_PRICES',decision_at='2026-09-30T20:00:00Z',session_timezone='America/New_York',basis='EXPLICIT_SYNTHETIC',
            prices={s:dict(price='1',lot_size=1,available_at='2026-09-30T19:00:00Z',price_date='2026-09-30',basis='EXPLICIT_SYNTHETIC') for s,_,_ in ids}),
        policy=dict(risk_parameters=dict(max_single_weight='0.8',min_single_weight='0.02',top_weight_cap='1',minimum_effective_n_ratio='0.4',risk_chain_top1_cap='0.9'),transaction_cost_bps='0',minimum_cash_buffer='0',currency='USD'),
        domain_kind='WHOLE_LOT_QUANTITIES')

class IndependentMicrodomainTests(unittest.TestCase):
    def test_every_tuple_multiclass_fractional_old_fees_lots_and_all_k(self):
        checked=passed=0
        for cash,fee,buffer,old,exclude,lot in product(('2','4'),('0','125'),('0','0.5'),('0','0.5'),(False,True),(1,2)):
            data=inputs();data['cash_event']['amount']=cash
            data['policy'].update(transaction_cost_bps=fee,minimum_cash_buffer=buffer)
            data['prior_book']['holdings']={'X':old}
            data['price_context']['prices']['Y']['lot_size']=lot
            if exclude:data['evidence_facts']['conditional_exclusions']={'Z':'EXPLICIT_UNBOUND_EXCLUSION'}
            result=subject.prepare_new_cash_problem(**data)
            identities={r['security_id']:r for r in data['evidence_facts']['conditional_inventory']}
            buy=sorted(set(identities)-set(data['evidence_facts'].get('conditional_exclusions',{})))
            budget=F(cash)-F(buffer);factor=1+F(fee)/10000
            caps={s:int(budget/(F(data['price_context']['prices'][s]['price'])*data['price_context']['prices'][s]['lot_size']*factor)) for s in buy}
            self.assertEqual(result['domain_formula']['coordinate_caps_or_null'],caps)
            self.assertEqual(list(r['holding_count'] for r in result['all_k_rows']),[1,2,3])
            self.assertEqual([r['composition_count'] for r in result['conditional_inventory']['all_k_denominators']],['4','5','2'])
            actual_box=1
            for cap in caps.values():actual_box*=cap+1
            self.assertEqual(int(result['bounding_box_count_or_null']),actual_box)
            for point in product(*(range(caps[s]+1) for s in buy)):
                checked+=1;increment=dict(zip(buy,point))
                quantities={s:(F(old) if s=='X' else F(0))+increment.get(s,0)*data['price_context']['prices'][s]['lot_size'] for s in identities}
                cost=sum(increment[s]*data['price_context']['prices'][s]['lot_size']*factor for s in buy)
                positive={s:q for s,q in quantities.items() if q>0}
                total=sum(positive.values(),F(0));w={s:q/total for s,q in positive.items()} if total else {}
                # Formula reconstruction receives no subject cap/certificate as oracle input.
                d=result['domain_formula'];from_output={s:F(result['frozen_prior_book']['quantities'].get(s,'0'))+increment.get(s,0)*d['lot_sizes'][s] for s in identities}
                self.assertEqual(from_output,quantities)
                self.assertEqual(cost,sum(increment[s]*d['lot_sizes'][s]*F(d['fee_factor']) for s in buy))
                if not w or cost>budget or len({identities[s]['issuer_id'] for s in positive})!=len(positive):continue
                risk={k:F(v) for k,v in data['policy']['risk_parameters'].items()};tol=F(1,10**9)
                chains={r['risk_chain']:sum(value for s,value in w.items() if identities[s]['risk_chain']==r['risk_chain']) for r in identities.values()}
                admissible=(max(w.values())<=risk['max_single_weight']+tol and min(w.values())>=risk['min_single_weight']-tol and sum(sorted(w.values(),reverse=True)[:3])<=risk['top_weight_cap']+tol and 1/sum(v*v for v in w.values())>=risk['minimum_effective_n_ratio']*len(w)-tol and max(chains.values())<=risk['risk_chain_top1_cap']+tol)
                if admissible:
                    passed+=1;row=result['all_k_rows'][len(w)-1]
                    self.assertEqual(row['status'],'NOT_PRUNED_NECESSARY_ONLY');self.assertEqual(row['necessary_certificates'],[]);self.assertEqual(row['domain_necessary_reasons'],[])
                    for lower in d['frozen_weight_lower_bounds']:
                        actual=w[lower['identity']] if lower['kind']=='SECURITY' else chains[lower['identity']]
                        self.assertLessEqual(F(lower['lower_bound']),actual)
            frozen_positive={'X'} if F(old)>0 else set()
            candidates=set(buy)-frozen_positive
            expected=[]
            for k in (1,2,3):
                count=0
                for choice in combinations(sorted(candidates),k-len(frozen_positive)) if k>=len(frozen_positive) else ():
                    support=frozen_positive|set(choice)
                    if len({identities[s]['issuer_id'] for s in support})==len(support):count+=1
                expected.append(str(count))
            self.assertEqual([r['frozen_old_conditional_composition_count'] for r in result['all_k_rows']],expected)
        self.assertGreater(checked,1000);self.assertGreater(passed,0)
        type(self).tuple_count=checked;type(self).feasible_count=passed

    def test_frozen_outside_inventory_and_issuer_conflict_never_delete_old(self):
        data=inputs();data['evidence_facts']['frozen_only_securities']=[dict(security_id='OLD',ticker='OLD',issuer_id='I3',risk_chain='R3')]
        data['prior_book']['holdings']={'OLD':'0.125'}
        data['price_context']['prices']['OLD']=deepcopy(data['price_context']['prices']['X'])
        result=subject.prepare_new_cash_problem(**data)
        self.assertEqual(result['frozen_prior_book']['quantities'],{'OLD':'1/8'})
        self.assertEqual(len(result['all_k_rows']),4)
        self.assertEqual([r['frozen_old_conditional_composition_count'] for r in result['all_k_rows']],['1','4','5','2'])
        data['prior_book']['holdings'].update(X='0.25',XA='0.5')
        result=subject.prepare_new_cash_problem(**data)
        self.assertEqual(result['frozen_prior_book']['quantities'],{'OLD':'1/8','X':'1/4','XA':'1/2'})
        self.assertTrue(all(r['status']=='STRUCTURALLY_INFEASIBLE' and r['frozen_old_conditional_composition_count'] is None for r in result['all_k_rows']))

    def test_strict_tolerance_equality_and_continuous_domain_not_lot_pruned(self):
        data=inputs()
        for i,r in enumerate(data['evidence_facts']['conditional_inventory']):r['issuer_id']='DISTINCT'+str(i)
        data['policy']['risk_parameters'].update(top_weight_cap='0.749999999',max_single_weight='1',risk_chain_top1_cap='1',min_single_weight='0',minimum_effective_n_ratio='0')
        result=subject.prepare_new_cash_problem(**data)
        self.assertFalse(result['all_k_rows'][3]['necessary_certificates'])
        data['policy']['risk_parameters']['top_weight_cap']='0.749999998999999999999'
        result=subject.prepare_new_cash_problem(**data)
        self.assertTrue(any(c['reason']=='TOP3_UNIVERSAL_LOWER_BOUND_ABOVE_CAP' for c in result['all_k_rows'][3]['necessary_certificates']))
        data=inputs();data['cash_event']['amount']='0.1';data['domain_kind']='CONTINUOUS_INCREMENTAL_DOLLARS'
        data['policy']['risk_parameters'].update(max_single_weight='1',min_single_weight='0',risk_chain_top1_cap='1',minimum_effective_n_ratio='0')
        result=subject.prepare_new_cash_problem(**data)
        self.assertIsNone(result['domain_formula']['coordinate_caps_or_null']);self.assertIsNone(result['domain_formula']['whole_lot_activation_upper_or_null'])
        self.assertTrue(all(r['status']=='NOT_PRUNED_NECESSARY_ONLY' for r in result['all_k_rows']))

    def test_new_york_midnight_and_dst_same_instant_offsets(self):
        for day,execution,local,utc in [('2026-10-08','2026-10-09','2026-10-08T20:30:00-04:00','2026-10-09T00:30:00Z'),('2026-11-02','2026-11-03','2026-11-02T20:30:00-05:00','2026-11-03T01:30:00Z')]:
            data=inputs();data['prior_book']['as_of']=day
            data['cash_event'].update(decision_date=day,execution_date=execution,available_at=local)
            data['price_context']['decision_at']=local
            for mark in data['price_context']['prices'].values():mark.update(available_at=local,price_date=day)
            a=subject.prepare_new_cash_problem(**data)
            data['cash_event']['available_at']=utc;data['price_context']['decision_at']=utc
            for mark in data['price_context']['prices'].values():mark['available_at']=utc
            b=subject.prepare_new_cash_problem(**data)
            self.assertEqual(a['problem_id'],b['problem_id']);self.assertEqual(b['context_blockers'],[])
            self.assertIs(b['exchange_session_timezone_verified'],False)

    def test_untrusted_references_never_read_and_all_authority_remains_false(self):
        ZoneInfo('America/New_York') # runtime TZif resolution explicitly allowed before the source IO trap.
        data=inputs();data['evidence_facts'].update(qualified=True,source_hashes={'TRAP':'a'*64},authority={'execution_authorized':True})
        data['evidence_facts']['input_references']={role:dict(path='TRAP/'+role,sha256='a'*64) for role,_ in subject.SOURCE_REQUIREMENTS}
        old=deepcopy(data)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Caller source IO')) as read,patch.object(builtins,'open',side_effect=AssertionError('Caller source open')) as opened:
            result=subject.prepare_new_cash_problem(**data)
            self.assertEqual(read.call_count,0);self.assertEqual(opened.call_count,0)
        self.assertEqual(data,old);self.assertEqual(result['status'],'SOURCE_BLOCKED');self.assertEqual(len(result['source_checks']),10)
        self.assertTrue(all(x['status']=='SOURCE_BLOCKED' and x['qualification_established'] is False for x in result['source_checks']))
        self.assertTrue(all(v is False for v in result['authority'].values()));self.assertIsNone(result['qualified_inventory_or_null']);self.assertIsNone(result['qualified_all_k_denominators_or_null'])
        self.assertIsNone(result['current_account']);self.assertIsNone(result['current_new_money']);self.assertEqual(result['plan_rows'],[])
        result['frozen_prior_book']['quantities']['X']='999';result['conditional_inventory']['securities'].clear()
        self.assertEqual(data,old)

if __name__=='__main__':unittest.main()
