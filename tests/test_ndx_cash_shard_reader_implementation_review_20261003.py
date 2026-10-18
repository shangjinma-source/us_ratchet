"""Independent adversarial synthetic review; no actual shard/readback execution."""
from copy import deepcopy
from decimal import Inexact, localcontext
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_cash_topup_neighbor_shard_independent_readback_20261003 as reader
from test_ndx_cash_topup_neighbor_shard_independent_readback_20261003 import shard_fixture, inspect, seal


class ReviewTests(unittest.TestCase):
    def test_resealed_cash_holdings_all_five_checks_and_score_rejected(self):
        original=shard_fixture()
        raw=original[4][1]['payload']['result']['branches'][0]['evaluated_plans'][0]
        attacks=['cash','holding','feasible','fees']+['check:'+k for k in raw['risk']['checks']]
        for attack in attacks:
            data=deepcopy(original[:-1])+(original[-1],)
            value=data[4][1]['payload']['result']['branches'][0]['evaluated_plans'][0]
            if attack=='cash':
                key=next(k for k in value if 'cash' in k and type(value[k]) is str)
                value[key]='9999999'
            elif attack=='holding':
                sid=next(iter(value['proposed_holdings']));value['proposed_holdings'][sid]+=1
            elif attack=='feasible':value['feasible']=not value['feasible']
            elif attack=='fees':value['fees_usd']='-1'
            else:
                key=attack.split(':',1)[1];value['risk']['checks'][key]=not value['risk']['checks'][key]
            with self.subTest(attack=attack),self.assertRaises(ValueError):inspect(data)

    def test_partial_and_external_cannot_relabel_as_new_completed(self):
        data=shard_fixture(external=True)
        with patch.object(reader,'FIRST_ID',data[1][0]['task_id']):
            result=inspect(data)
            self.assertEqual(result['new_arithmetic_checked_count'],1)
            self.assertEqual(result['outcome_counts']['EXTERNALLY_REFERENCED'],1)
            bad=deepcopy(data[:-1])+(data[-1],)
            bad[4][0]['payload']=deepcopy(bad[4][0]['payload'])
            bad[4][0]['payload']['first_raw']['sha256']='f'*64
            with self.assertRaises(ValueError):inspect(bad)
            # Even fully resealed three-stage returns cannot stand in for the fixed prior point.
            replacement=shard_fixture(external=False)
            with self.assertRaises(ValueError):inspect(replacement)
        clean=shard_fixture();p,tasks,d,start,records,ext,oracle=clean
        completion,raw=seal(records,d)
        for ending in (b'{',b'\n{',b'\n'):
            with self.subTest(ending=ending),self.assertRaises(ValueError):
                reader.inspect_complete_shard(started=start,completion=completion,journal_bytes=raw+ending,
                    tasks=tasks,prepared=p,descriptor=d,context_sha256='c'*64,external_references=ext,independent_result=oracle)

    def test_full_math_context_contract_and_no_files_in_inspector(self):
        data=shard_fixture();expected=inspect(data)
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True
            with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure inspection must not read files')):
                self.assertEqual(inspect(data),expected)
        bad=deepcopy(data[:-1])+(data[-1],)
        bad[3]['contract_sha256']='b'*64
        with self.assertRaises(ValueError):inspect(bad)
        for field in reader.FALSE:
            bad=deepcopy(data[:-1])+(data[-1],)
            bad[3][field]=0
            with self.subTest(flag=field),self.assertRaises(ValueError):inspect(bad)


if __name__=='__main__':unittest.main()
