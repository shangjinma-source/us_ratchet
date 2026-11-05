import unittest
from copy import deepcopy
from fractions import Fraction as F
import test_downside_account_candidate_20261105 as fixture
from scripts.research import review_downside_account_20261105 as audit


def saved_tie_fixture():
    capital,returns,qqq=fixture.fixture()
    raw,side=fixture.run(capital,returns,qqq)  # Tiny candidate stream; no account run.
    selected=fixture.original_rerank(raw)
    original_id=selected['rerank_decision_id']
    product=audit.score(selected['target_quantities'],raw['binding']['search_arguments'])['product']
    selected['original_rerank_audit']=selected.pop('rerank_audit')
    selected['method']='SAME_CALL_OBSERVED_DOWNSIDE_QQQ_V1'
    selected['downside_audit']=dict(incumbent='ACTUAL_V27_SAVED_FRONTIER_CAP50_RERANK',incumbent_admitted=True,
        incumbent_product_sha256=audit.product_hash(product),selected_product_sha256=audit.product_hash(product),
        coverage=side['coverage'],tie_rule='ADMITTED_ACTUAL_V27_INCUMBENT_RETAINED_UNLESS_STRICT_PRODUCT_IMPROVEMENT',holding_count_limit=10,source_authenticated=False)
    selected['rerank_binding']=dict(schema=selected['method'],original_rerank_decision_id=original_id,
        target_quantities=selected['target_quantities'],downside_audit=selected['downside_audit'])
    selected['rerank_decision_id']=audit.canonical(selected['rerank_binding'])
    return selected,side,returns,qqq


class IndependentDownsideReview(unittest.TestCase):
    def test_small_saved_stream_tie_and_mutation(self):
        selected,side,returns,qqq=saved_tie_fixture()
        proof,result=audit.review_selection(selected,side,returns,qqq,fixture.RESEARCH)
        self.assertEqual(proof['target_quantities'],selected['target_quantities'])
        self.assertTrue(result['incumbent_admitted'])
        changed=deepcopy(selected);changed['target_quantities']={}
        with self.assertRaisesRegex(ValueError,'WINNER'):
            audit.review_selection(changed,side,returns,qqq,fixture.RESEARCH)

    def test_exact_risk_and_max10_no_integer_helper(self):
        args=dict(entered_cash='100',prices={'A':'10'},decision_date='2020-09-08')
        from datetime import date,timedelta
        days=[(date(2020,1,1)+timedelta(days=i)).isoformat() for i in range(252)]
        reference=dict.fromkeys(days,F('-1/100'));returns={'A':dict.fromkeys(days,F('-1/10'))}
        self.assertEqual(audit.risk({'A':1},args,returns,reference),(True,F(1,10000),F(1,10000)))
        self.assertFalse(audit.risk({'A':2},args,returns,reference)[0])
        selected,side,returns,qqq=saved_tie_fixture();side['max_holdings']=11
        side['integrity_sha256']=audit.evidence_hash({k:v for k,v in side.items() if k!='integrity_sha256'})
        selected['raw_selection']['downside_sidecar_sha256']=side['integrity_sha256']
        with self.assertRaisesRegex(ValueError,'MAX10'):
            audit.review_selection(selected,side,returns,qqq,fixture.RESEARCH)

    def test_codec_is_versioned_and_exact(self):
        doc=dict(encoding=audit.ENCODING,payload={audit.TAG:dict(numerator='0x1',denominator='0x3')})
        self.assertEqual(audit.unpack(doc),F(1,3))
        doc['encoding']='UNKNOWN'
        with self.assertRaisesRegex(ValueError,'VERSION'):audit.unpack(doc)
        doc['encoding']=audit.ENCODING;doc['payload'][audit.TAG]['denominator']='0x0'
        with self.assertRaisesRegex(ValueError,'DENOMINATOR'):audit.unpack(doc)


if __name__=='__main__':unittest.main()
