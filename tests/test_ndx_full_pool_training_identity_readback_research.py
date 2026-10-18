"""Bounded pure identity tests. Producer records are explicit synthetic declarations, never helper calls."""
from copy import deepcopy
from datetime import date,timedelta
from fractions import Fraction
from pathlib import Path
import ast
import hashlib
import json
import unittest
from unittest.mock import patch
from backtest import ndx_full_pool_training_identity_readback_research as subject


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def matrix(rows=None,m=2,n=3):
    rows=rows if rows is not None else [['0','1/5'],['1/5','0'],['1/10','1/10']]
    return dict(model_id=subject.MODEL,ordered_security_ids=[f'S{i}' for i in range(m)],
                training_dates=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(n)],shape=[n,m],cells=rows)


def declared_producer(mat,means=None,samples=None,entries=None):
    n,m=mat['shape'];pairs=[(i,j) for i in range(m) for j in range(i,m)];p=len(pairs)
    means=means if means is not None else ['1/10','1/10']
    samples=samples if samples is not None else ['1/100','-1/100','1/100']
    entries=entries if entries is not None else ['1/100','-13/2000','1/100']
    cov=[[None]*m for _ in range(m)]
    for (i,j),value in zip(pairs,entries):cov[i][j]=cov[j][i]=value
    ledger=[];offset=0
    for i in range(m):ledger.append(dict(kind='MEAN',column=i,cost=n+1,start=offset,stop=offset+n+1));offset+=n+1
    for i,j in pairs:ledger.append(dict(kind='PAIR',i=i,j=j,cost=4*n+4,start=offset,stop=offset+4*n+4));offset+=4*n+4
    def maxbits(values):
        numbers=[Fraction(x) for x in values]
        return [max(abs(x.numerator).bit_length() for x in numbers),max(x.denominator.bit_length() for x in numbers)]
    bits=maxbits(means+samples+entries);digest=hashlib.sha256(canonical(mat)).hexdigest()
    return dict(schema='EXACT_TRAINING_MOMENTS_V1',model_id=subject.MODEL,input_binding='UNBOUND_PURE_INPUT_NOT_SOURCE_AUTHENTICATED',
                matrix_sha256=digest,status='COMPLETE',null_coordinates=[],
                mean_tasks=[dict(column=i,status='COMPUTED',value=x) for i,x in enumerate(means)],
                pair_tasks=[dict(i=i,j=j,status='COMPUTED',sample=s,value=v) for (i,j),s,v in zip(pairs,samples,entries)],
                full_covariance=cov,arithmetic_ledger=ledger,
                work=dict(unit='REGISTERED_RATIONAL_PRIMITIVES_V1',scope=subject.PRODUCER_SCOPE,requested=offset,spent=offset,unused=0,
                          actual_primitive_counts=dict(mean_accumulations=n*m,mean_divisions=m,pair_center_subtractions=2*n*p,pair_products=n*p,
                          pair_accumulations=n*p,sample_divisions=p,shrink_multiplications=2*p,shrink_additions=p),
                          mean_columns_completed=m,pair_entries_completed=p,required_tasks=m+p,pending_tasks=0,source_blocked_tasks=0,
                          matrix_validation_cells=n*m,fraction_parses=n*m,validation_is_outside_primitive_budget=True,
                          input_max_fraction_bits=maxbits([x for row in mat['cells'] for x in row]),intermediate_max_fraction_bits=bits,
                          output_max_fraction_bits=bits,source_io_calls=0,guard_calls=0,resume_replay_tasks=0,
                          independent_certificate_recheck_tasks=0,gcd_internal_operations=None,wall_elapsed_seconds=0.0),
                certificate=dict(kind='COMPLETE_CENTERED_GRAM_PLUS_DIAGONAL',n=n,ddof=1,lambda_exact='7/20',matrix_sha256=digest,independently_checked=False),
                qualified_inventory=None,current_account=None,current_new_money=None,plan_rows=[],permissions={k:False for k in subject.PERMISSIONS})


class IdentityReadback(unittest.TestCase):
    def call(self,budget=47,mat=None,result=None):
        mat=matrix() if mat is None else mat;result=declared_producer(mat) if result is None else result
        return subject.verify_raw_cross_moment_identity(matrix=mat,numerical_result=result,work_budget=budget)

    def test_hand_two_security_three_observation_exact47(self):
        mat=matrix();original=declared_producer(mat);before=deepcopy((mat,original))
        result=self.call(mat=mat,result=original)
        self.assertTrue(result['status'].startswith('PASS_INDEPENDENT'))
        self.assertEqual([t['value'] for t in result['mean_tasks']],['1/10','1/10'])
        self.assertEqual([t['sample'] for t in result['pair_tasks']],['1/100','-1/100','1/100'])
        self.assertEqual([t['value'] for t in result['pair_tasks']],['1/100','-13/2000','1/100'])
        counts=result['work']['actual_primitive_counts']
        self.assertEqual(counts,dict(mean_accumulations=6,mean_divisions=2,raw_cross_products=9,raw_cross_accumulations=9,
                                  mean_products=3,correction_multiplications=3,cross_correction_subtractions=3,sample_divisions=3,
                                  shrink_multiplications=6,shrink_additions=3))
        self.assertEqual(result['work']['spent'],47);self.assertEqual(original['work']['spent'],56)
        self.assertEqual(result['work']['full_coordinates_independently_compared'],4)
        self.assertNotIn('full_covariance',result)
        self.assertEqual((mat,original),before)
        self.assertFalse(result['producer_declarations']['intermediate_maxima_independently_replayed'])
        self.assertFalse(original['certificate']['independently_checked'])
        result['pair_tasks'][0]['value']='changed';self.assertEqual(original,before[1])

    def test_atomic_budget_zero_partial_exact_boundaries(self):
        for budget,spent,means,pairs in [(0,0,0,0),(3,0,0,0),(4,4,1,0),(7,4,1,0),(8,8,2,0),(20,8,2,0),(21,21,2,1),(34,34,2,2),(46,34,2,2),(47,47,2,3)]:
            with self.subTest(budget=budget):
                r=self.call(budget);w=r['work']
                self.assertEqual((w['spent'],w['means_verified'],w['pairs_verified']),(spent,means,pairs))
                self.assertEqual(w['unused'],budget-spent);self.assertEqual(w['pending_tasks'],5-means-pairs)
                self.assertEqual(sum(w['actual_primitive_counts'].values()),spent)
                self.assertEqual(r['certificate']['independent_arithmetic_readback_complete'],budget==47)

    def test_parameter_gates_precede_input_or_producer(self):
        with patch.object(subject,'_matrix',side_effect=AssertionError('input read')):
            for value in (None,True,-1,1.0,787557):
                with self.assertRaises(ValueError):subject.verify_raw_cross_moment_identity(matrix=None,numerical_result=None,work_budget=value)
            with self.assertRaises(NotImplementedError):subject.verify_raw_cross_moment_identity(matrix=None,numerical_result=None,work_budget=0,resume={})
        with self.assertRaisesRegex(ValueError,'dimensional'):self.call(48)

    def test_runtime_dual_gate_precedes_matrix(self):
        from types import SimpleNamespace
        with patch.object(subject.sys,'get_int_max_str_digits',return_value=4300),patch.object(subject,'_matrix',side_effect=AssertionError('input')):
            with self.assertRaisesRegex(ValueError,'runtime'):self.call()
        with patch.object(subject.sys,'flags',SimpleNamespace(int_max_str_digits=4300)),patch.object(subject,'_matrix',side_effect=AssertionError('input')):
            with self.assertRaisesRegex(ValueError,'runtime'):self.call()

    def test_input_exact_literal_and_closed_dimensions(self):
        for text in (None,True,1,0.1,'nan','1e-2','-0','1/1','2/4','0/3','1/0','-1',str(1<<53),'1/'+str(1<<56)):
            mat=matrix();mat['cells'][0][0]=text
            with self.subTest(text=text),self.assertRaises((ValueError,TypeError)):
                subject.verify_raw_cross_moment_identity(matrix=mat,numerical_result={},work_budget=0)
        for alter in (lambda m:m.update(extra=1),lambda m:m.update(shape=[True,2]),lambda m:m['ordered_security_ids'].__setitem__(1,'S0'),
                      lambda m:m['training_dates'].__setitem__(0,'20260101'),lambda m:m['cells'].pop()):
            mat=matrix();alter(mat)
            with self.assertRaises(ValueError):subject.verify_raw_cross_moment_identity(matrix=mat,numerical_result={},work_budget=0)

    def test_all_closed_nested_shapes_and_typed_declarations(self):
        modifications=[lambda r:r.update(extra=True),lambda r:r.update(status='PARTIAL_PENDING_BUDGET'),lambda r:r.update(full_covariance=None),
            lambda r:r['mean_tasks'][0].update(extra=0),lambda r:r['pair_tasks'][0].update(extra=0),lambda r:r['work'].update(extra=0),
            lambda r:r['permissions'].update(extra=False),lambda r:r['certificate'].update(extra=0),lambda r:r['arithmetic_ledger'][0].update(extra=0),
            lambda r:r['work'].update(unused=False),lambda r:r['work']['actual_primitive_counts'].update(mean_accumulations=True),
            lambda r:r['arithmetic_ledger'][0].update(start=False),lambda r:r['mean_tasks'][0].update(column=False),
            lambda r:r['pair_tasks'][0].update(i=False),lambda r:r['certificate'].update(independently_checked=0),
            lambda r:r['certificate'].update(independently_checked=True),lambda r:r['permissions'].update(fit_performed=0),
            lambda r:r['work'].update(wall_elapsed_seconds=float('nan')),lambda r:r.update(current_new_money=20000),
            lambda r:r.update(matrix_sha256='0'*64)]
        for change in modifications:
            p=declared_producer(matrix());change(p)
            with self.subTest(change=change),self.assertRaises(ValueError):self.call(0,result=p)

    def test_coordinated_numeric_restatement_rejected_by_actual_identity(self):
        mat=matrix()
        # All producer sample/value/lower/upper/outputbits consistent; raw identity still disagrees.
        p=declared_producer(mat,samples=['1/100','-1/100','1/100'],entries=['1/100','-1/100','1/100'])
        with self.assertRaisesRegex(ValueError,'sample/entry mismatch'):self.call(mat=mat,result=p)
        p=declared_producer(mat,means=['1/5','1/10'])
        with self.assertRaisesRegex(ValueError,'mean mismatch'):self.call(mat=mat,result=p)
        # Changed matrix and both self-digests cannot authenticate unchanged numerical values.
        mat['cells'][0][0]='1/10';p=declared_producer(mat)
        with self.assertRaisesRegex(ValueError,'mean mismatch'):self.call(mat=mat,result=p)

    def test_cov_every_coordinate_and_max_bits_ledger_checks(self):
        for row in range(2):
            for column in range(2):
                p=declared_producer(matrix());p['full_covariance'][row][column]='0'
                with self.assertRaisesRegex(ValueError,'covariance coordinate'):self.call(0,result=p)
        for change in (lambda r:r['work'].update(output_max_fraction_bits=[0,0]),
                       lambda r:r['work'].update(intermediate_max_fraction_bits=[14246,1]),
                       lambda r:r['work'].update(input_max_fraction_bits=[0,1]),
                       lambda r:r['arithmetic_ledger'][-1].update(stop=55)):
            p=declared_producer(matrix());change(p)
            with self.assertRaises(ValueError):self.call(0,result=p)
        p=declared_producer(matrix());p['work']['intermediate_max_fraction_bits']=[14245,14138]
        r=self.call(result=p);self.assertFalse(r['producer_declarations']['intermediate_maxima_independently_replayed'])

    def test_full77_shape_only_mock_budget_zero_no_true77_moments(self):
        mat=matrix([['0']*77 for _ in range(126)],m=77,n=126);p=77*78//2
        original=declared_producer(mat,means=['0']*77,samples=['0']*p,entries=['0']*p)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            r=subject.verify_raw_cross_moment_identity(matrix=mat,numerical_result=original,work_budget=0)
        self.assertEqual(r['work']['complete_cost'],787556)
        self.assertEqual(r['work']['producer_full_coordinates_associated'],5929)
        self.assertEqual(r['work']['original_numeric_ascii_all_copies'],12012)
        self.assertEqual(r['work']['pending_tasks'],3080)
        self.assertEqual(r['work']['spent'],0);self.assertEqual(r['work']['full_coordinates_independently_compared'],0)
        self.assertEqual(r['work']['validation']['fraction_constructions'],9702+6083)

    def test_independent_small_centered_oracle_additional_rank_deficient_case(self):
        # Test oracle is small explicit centered Gram, different from subject raw-cross identity.
        rows=[['1/7','0','1/7'],['2/7','0','2/7']];mat=matrix(rows,m=3,n=2)
        values=[[Fraction(x) for x in row] for row in rows]
        means=[sum(row[i] for row in values)/2 for i in range(3)]
        samples=[];entries=[]
        for i in range(3):
            for j in range(i,3):
                sample=sum((row[i]-means[i])*(row[j]-means[j]) for row in values)
                samples.append(str(sample));entries.append(str(sample if i==j else sample*Fraction(13,20)))
        original=declared_producer(mat,list(map(str,means)),samples,entries)
        r=self.call(75,mat,original) # 3*3+6*11
        self.assertTrue(r['status'].startswith('PASS_'))
        self.assertEqual(r['work']['spent'],75);self.assertEqual(r['work']['full_coordinates_independently_compared'],9)
        self.assertEqual(r['pair_tasks'][3]['value'],'0')

    def test_pure_import_surface_and_absence_of_producer_calls(self):
        tree=ast.parse(Path(subject.__file__).read_text(encoding='utf-8-sig'))
        imports=[node.module or '' for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node,ast.Import) for alias in node.names]
        self.assertTrue(set(imports)<= {'datetime','fractions','hashlib','json','math','re','sys','time'})
        for forbidden in ('prepare_exact_training_moments','check_exact_training_moment_certificate','validate_complete','exec','eval','compile','open'):
            self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id==forbidden for n in ast.walk(tree)))
