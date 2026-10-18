"""Bounded synthetic oracle attacks; never builds or publishes the 101-channel audit."""
from copy import deepcopy
from decimal import localcontext, Inexact, Rounded
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import test_ndx_new_cutoff_channels_independent_audit_20260923 as fixture

m=fixture.m


class IndependentOracleReview(unittest.TestCase):
    def test_reverse_later_factor_and_dividend_does_not_change_returns(self):
        raw,calendar,policies=fixture.fixture()
        body=json.loads(raw);r=body['chart']['result'][0];stamp=r['timestamp'][90]
        r['events']['splits'][str(stamp)]=dict(date=stamp,numerator=1,denominator=5,splitRatio='1:5')
        policies.append(dict(session=calendar[90],kind='ORDINARY_SPLIT',numerator=1,denominator=5))
        got=m.derive(json.dumps(body).encode(),'TEST',calendar,policies)
        self.assertEqual(got['quote_rows'][0]['nominal_close'],'40.2')
        self.assertEqual(got['quote_rows'][10]['nominal_close'],'20.1')
        self.assertEqual(got['quote_rows'][90]['nominal_close'],'100.5')
        self.assertTrue(all(v['price_return']==0 for v in got['price_returns']))
        self.assertEqual(len(got['price_returns']),126)

    def test_volume_first_day_boundary_is_inclusive(self):
        for index,blocked in ((63,False),(64,True)):
            raw,calendar,policies=fixture.fixture(event_index=index)
            got=m.derive(raw,'TEST',calendar,policies)
            self.assertEqual(got['liquidity']['rows'] is None,blocked)
            self.assertEqual(len(got['quote_rows']),127)

    def test_decimal_host_traps_do_not_change_independent_arithmetic(self):
        raw,calendar,policies=fixture.fixture()
        expected=m.derive(raw,'TEST',calendar,policies)
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True;context.traps[Rounded]=True
            self.assertEqual(m.derive(raw,'TEST',calendar,policies),expected)

    def test_policy_denominator_and_bool_price_are_rejected(self):
        raw,calendar,policies=fixture.fixture()
        for bad in ([],policies+deepcopy(policies)):
            with self.assertRaises(ValueError):m.derive(raw,'TEST',calendar,bad)
        body=json.loads(raw);body['chart']['result'][0]['indicators']['quote'][0]['open'][50]=True
        with self.assertRaises(ValueError):m.derive(json.dumps(body).encode(),'TEST',calendar,policies)

    def test_source_conflict_and_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'raw';path.write_bytes(b'first')
            ref=dict(path=str(path),sha256=hashlib.sha256(b'first').hexdigest())
            sources={};self.assertEqual(m.read(ref,sources),b'first')
            other=dict(ref,sha256=hashlib.sha256(b'other').hexdigest())
            with self.assertRaisesRegex(ValueError,'Conflicting'):m.read(other,sources)
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'bytes'):m.read(ref,sources)


if __name__=='__main__':unittest.main()
