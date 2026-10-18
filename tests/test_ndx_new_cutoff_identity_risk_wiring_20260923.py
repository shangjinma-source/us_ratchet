"""In-memory sealed-document fixtures; no machine wiring build or publication."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_identity_risk_wiring_20260923 as m


class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs={role:json.loads((m.BASE/path).read_bytes()) for role,(path,_) in m.BOUND.items()}

    def test_full_denominator_original_evidence_and_windows_preserved(self):
        value=m.assemble(self.docs);rows={row['ticker']:row for row in value['rows']}
        self.assertEqual(len(rows),101)
        self.assertEqual((value['candidate_security_count'],value['candidate_issuer_count']),(19,18))
        self.assertEqual(sum(row['risk_chain'] is not None for row in rows.values()),19)
        self.assertEqual(sum(row['coordinate'] is None for row in rows.values()),80)
        self.assertEqual(len(rows['GOOG']['complete_original_evidence']),2)
        self.assertEqual(rows['GOOG']['coordinate']['issuer_id'],rows['GOOGL']['coordinate']['issuer_id'])
        self.assertNotEqual(rows['GOOG']['coordinate']['security_id'],rows['GOOGL']['coordinate']['security_id'])
        self.assertEqual(rows['AMAT']['original_windows'],[{'first':'2026-03-18','last':'2026-09-17'}])
        self.assertEqual(rows['AMAT']['new_assumed_window'],{'first':'2026-03-20','last':'2026-09-21'})
        self.assertIsNone(rows['PCAR']['risk_chain']);self.assertIsNone(rows['CPRT']['risk_chain'])
        self.assertTrue(all(value[key] is False for key in m.FALSE))

    def test_overlap_class_risk_and_same_issuer_sid_attacks(self):
        for attack in ('class','risk','same_issuer_sid'):
            docs=deepcopy(self.docs)
            row=next(row for row in docs['legacy']['rows'] if row['ticker']=='GOOG')
            if attack=='class':row['security_class']='Class A'
            elif attack=='same_issuer_sid':row['security_id']='security:0001652044:02079K305';row['cusip']='02079K305'
            else:
                for mapping in docs['legacy']['selected_risk_chains_by_decision'].values():
                    if row['security_id'] in mapping:mapping[row['security_id']]='WRONG'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)

    def test_all_saved_risk_dates_not_last_wins(self):
        docs=deepcopy(self.docs);sid='security:0000804328:747525103'
        first=next(mapping for mapping in docs['legacy']['selected_risk_chains_by_decision'].values() if sid in mapping)
        first[sid]='conflicting_old_label'
        with self.assertRaisesRegex(ValueError,'conflicting legacy risk'):m.assemble(docs)

    def test_lrcx_floor_pcar_risk_and_audit_false_pass(self):
        for attack in ('lrcx','risk','audit'):
            docs=deepcopy(self.docs)
            if attack=='lrcx':docs['panel']['supplemental_dated_and_risk_provenance']['LRCX']['complete_original_fact']['old_security_continuity_inferred']=True
            elif attack=='risk':docs['facts']['rows'][0]['risk_chain']='industrial'
            else:docs['audit']['details'][0]['status']='BLOCKED_PRICE_INPUT'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)

    def test_member_deletion_and_legacy_nonmember_insertion(self):
        docs=deepcopy(self.docs);docs['observation']['observed_symbols'].pop()
        with self.assertRaises(ValueError):m.assemble(docs)
        docs=deepcopy(self.docs);docs['observation']['observed_symbols'][0]='TEAM';docs['observation']['rows'][0]['symbol']='TEAM'
        with self.assertRaises(ValueError):m.assemble(docs)

    def test_txn_old_filing_date_is_not_rewritten(self):
        docs=deepcopy(self.docs)
        next(row for row in docs['legacy']['rows'] if row['ticker']=='TXN')['evidence']['dated_evidence']['filing_date']='2026-09-21'
        with self.assertRaisesRegex(ValueError,'TXN dated fact'):m.assemble(docs)

    def test_fixed_namespace_and_source_guard(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'wiring.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
        with patch.object(m.Path,'read_bytes',return_value=b'changed'):
            with self.assertRaises(ValueError):m.guard({})


if __name__=='__main__':unittest.main()
