import unittest
from copy import deepcopy
from pathlib import Path
from docs.candidates.downside_resume_chain_20261105 import verify_parent,reusable,verify_prefix_progress,append_ordinary_artifact

ROOT=Path(__file__).resolve().parents[1]


class ChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent=verify_parent(ROOT,ROOT/'tmp/downside_max10_20261105_late_v2')

    def test_two_generations_keep_source_bindings_and_cumulative_budget(self):
        p=self.parent
        self.assertEqual(p['chain_depth'],2)
        self.assertEqual(len(p['book']['daily_ledger']),83)
        self.assertEqual(p['summary']['searches']['new'],5)
        self.assertEqual(p['summary']['elapsed_seconds'],376.81472619995475)
        origins={r['origin'] for r in p['records'].values()}
        self.assertEqual(len(origins),2)
        counts={o:sum(r['origin']==o for r in p['records'].values()) for o in origins}
        self.assertEqual(sorted(counts.values()),[2,3])
        for r in p['records'].values():
            self.assertEqual(r['sidecar']['evidence_binding']['research_source_hashes'],r['source_pins'])
            self.assertEqual(reusable(p,r['selection']['arguments']),r)

    def test_full_arguments_and_latest_83_rows_gate(self):
        p=self.parent;args=deepcopy(next(iter(p['records'].values()))['selection']['arguments'])
        args['account_state']['cash']='0'
        with self.assertRaisesRegex(ValueError,'FULL_ARGUMENTS'):reusable(p,args)
        self.assertFalse(verify_prefix_progress(p['book'],p['book']['daily_ledger'][:82]))
        self.assertTrue(verify_prefix_progress(p['book'],p['book']['daily_ledger']))
        changed=deepcopy(p['book']['daily_ledger']);changed[82]['cash']='wrong'
        with self.assertRaisesRegex(ValueError,'PREFIX_CHANGED'):verify_prefix_progress(p['book'],changed)

    def test_paired_artifact_amount_and_duplicate_gate(self):
        raw=dict(ticker='CEG',kind='dividends',date='2024-05-31')
        doc=dict(prepared_input_candidate=dict(metadata={'SID':dict(ticker='CEG')}),provider_event_inventory=[raw],dividend_events=[])
        row=dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id='SID',ex_date=raw['date'],payment_date='2024-06-10',amount_per_share='1/2',currency='USD',source_references=['issuer'],observed_provider_events=[raw])
        event=dict(security_id='SID',ex_date=row['ex_date'],payment_date=row['payment_date'],amount_per_share='1/2',currency='USD',withholding_rate='0')
        artifact=dict(review_rows=[row],dividend_events=[event],source_hashes={'issuer':'pin'})
        bad=deepcopy(artifact);bad['dividend_events'][0]['amount_per_share']='1'
        with self.assertRaisesRegex(ValueError,'PAIR_FIELDS'):append_ordinary_artifact(deepcopy(doc),dict(rows=[],source_hashes={}),bad)
        review=dict(rows=[],source_hashes={});append_ordinary_artifact(doc,review,artifact)
        self.assertEqual(doc['dividend_events'],[event])
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):append_ordinary_artifact(doc,review,artifact)


if __name__=='__main__':unittest.main()
