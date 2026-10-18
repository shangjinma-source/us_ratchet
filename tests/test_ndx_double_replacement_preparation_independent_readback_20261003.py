import json
import tempfile
import unittest
from contextlib import contextmanager
from copy import deepcopy
from decimal import localcontext,Inexact
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from scripts import ndx_double_replacement_preparation_independent_readback_20261003 as m
from scripts import ndx_double_replacement_preparation_20261003 as producer
from test_ndx_double_replacement_preparation_20261003 import physical


@contextmanager
def prepared(root):
    bound,refs=physical(root);parent=root/'synthetic-preparation';output=root/'independent'
    with patch.multiple(producer,BOUND=bound,OUTPUT=parent),patch.object(producer,'resource'):
        prep=producer.run(execute=True)
    pub=parent/'publication.json'
    changes=dict(PRODUCER_SHA=m.hashlib.sha256(m.PRODUCER.read_bytes()).hexdigest(),BOUND=bound,PARENT=parent,OUTPUT=output,PREPARATION_SHA=prep['sha256'],PUBLICATION_SHA=m.hashlib.sha256(pub.read_bytes()).hexdigest())
    with patch.multiple(m,**changes):yield refs,prep


class Tests(unittest.TestCase):
    def test_independent_joint_count_small_oracle_and_enormous_triangle(self):
        for a in (Fraction(1,3),Fraction(2),Fraction(7,5)):
            for b in (Fraction(2,7),Fraction(1),Fraction(3,2)):
                for budget in (Fraction(-1),Fraction(1),Fraction(3),Fraction(9,2)):
                    expected=sum(a*x+b*y<=budget for x in range(1,33) for y in range(1,33))
                    self.assertEqual(m.independent_joint_count(a,b,budget),expected)
        n=10**80+7
        self.assertEqual(m.independent_joint_count(Fraction(1),Fraction(1),Fraction(n)),n*(n-1)//2)
        self.assertEqual(m.independent_joint_count(Fraction(1001,100),Fraction(3003,200),Fraction(50)),4)

    def test_physical_success_no_account_or_producer_call_by_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            with prepared(Path(tmp)) as (refs,prep):
                original=Path.read_bytes;account=m.ROOT/m.ACCOUNT_CLAIM[0]
                def checked(path):
                    self.assertNotEqual(path,account);return original(path)
                from backtest import ndx_double_replacement_domain_research as domain
                from backtest import ndx_two_positive_integer_budget_domain_research as helper
                with patch.object(Path,'read_bytes',checked),patch.object(producer,'run',side_effect=AssertionError('producer call')),patch.object(domain,'prepare_double_replacement_domain',side_effect=AssertionError('domain call')),patch.object(helper,'count_points',side_effect=AssertionError('helper call')):
                    result=m.readback(execute=True)
                report=json.loads(Path(result['path']).read_bytes());self.assertEqual(report['status'],'PASS')
                self.assertEqual(report['inspection']['integer_count'],160);self.assertEqual(report['inspection']['scenario_count'],40);self.assertEqual(report['inspection']['unselected_control_count'],24)
                self.assertNotIn(str(account),report['source_hashes']);self.assertIn(str(account),report['declared_parent_sources'])
                self.assertFalse(report['risk_evaluator_called']);self.assertFalse(report['full_transitive_source_closure_reverified'])
                with self.assertRaisesRegex(ValueError,'retry'):m.readback(execute=True)

    def test_independent_arithmetic_and_full_projection_reject_resigned_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            with prepared(Path(tmp)) as (refs,prep):
                docs={k:m.decode(Path(refs[k]['path']).read_bytes()) for k in ('policy','inputs','input_publication','inventory','inventory_publication','scenarios')}
                raw=m.decode((m.PARENT/'preparation.json').read_bytes())['preparation']
                with localcontext() as c:
                    c.prec=2;c.traps[Inexact]=True
                    good=m.inspect_domain(documents=docs,references=refs,saved_preparation=raw)
                self.assertEqual(good['integer_count'],160)
                for fault in ('cap','fee','issuer','ordinal','row','missing','authority'):
                    saved=deepcopy(raw);body=saved['document'];case=body['cases'][0];pair=case['pairs'][0]
                    if fault=='cap':pair['financial_integer_count']+=1
                    elif fault=='fee':pair['financial_bound']['sell_fee_usd']='0'
                    elif fault=='issuer':pair['issuer_exclusion_certificate']['conflicts']={'fake':['A','C']}
                    elif fault=='ordinal':case['pairs'][-1]['first_global_ordinal']+=1
                    elif fault=='row':case['identity']['original_input_row']['holdings']['ZERO']=1
                    elif fault=='missing':body['cases'].pop()
                    else:body['point_in_time_verified']=True
                    saved['content_sha256']=m.digest(body)
                    with self.subTest(fault=fault),self.assertRaises(ValueError):m.inspect_domain(documents=docs,references=refs,saved_preparation=saved)

    def test_late_source_and_own_report_drift_preserve_failure(self):
        for mode in ('source','output'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                with prepared(Path(tmp)) as (refs,prep):
                    original=m.save
                    def save(name,value):
                        r=original(name,value)
                        if name=='independent_readback.json':
                            target=Path(refs['policy']['path']) if mode=='source' else m.OUTPUT/'started.json'
                            target.write_bytes(b'late drift')
                        return r
                    with patch.object(m,'save',side_effect=save),self.assertRaises(ValueError):m.readback(execute=True)
                    self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertTrue((m.OUTPUT/'independent_readback.json').exists())
                    with self.assertRaisesRegex(ValueError,'retry'):m.readback(execute=True)

    def test_pending_rejects_before_io_and_failed_parent_is_not_success(self):
        with patch.object(m,'PREPARATION_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('source IO')),patch.object(Path,'exists',side_effect=AssertionError('source IO')):
            with self.assertRaisesRegex(ValueError,'anchor'):m.readback(execute=True)
        with tempfile.TemporaryDirectory() as tmp:
            with prepared(Path(tmp)):
                (m.PARENT/'failure.json').write_bytes(b'failure')
                with self.assertRaisesRegex(ValueError,'namespace'):m.readback(execute=True)


if __name__=='__main__':unittest.main()
