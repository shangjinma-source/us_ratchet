from scripts.research.run_news_early_three_arm_v1 import transform,SID,validate
from scripts.research.run_news_preopen_execution_probe_v1 import replay
import runpy


def answer(action,buy='1',hold='1',direction='NEGATIVE',materiality='HIGH'):
    return {'A_direct':{'action':action,'buy_fraction':buy,'holding_fraction':hold},'B_signal':{'direction':direction,'materiality':materiality}}


def test_fixed_anchor_no_compounding():
    a=answer('REDUCE_HOLDING','0','1/2')
    assert transform({SID:33},33,33,a,'A')[SID]==16
    assert transform({SID:33},33,33,a,'A')[SID]==16
    assert transform({SID:0},33,33,a,'A')[SID]==0
    assert transform({SID:8},33,33,a,'A')[SID]==8


def test_incremental_buy_and_pause_anchor():
    assert transform({SID:20},10,20,answer('REDUCE_BUY','1/2'),'A')[SID]==15
    assert transform({SID:20},10,20,answer('PAUSE_BUY','0'),'A')[SID]==10
    assert transform({SID:20},10,20,answer('EXIT','0','0'),'A')[SID]==0


def test_b_positive_no_overweight():
    assert transform({SID:33},33,33,answer('KEEP'),'B')[SID]==16
    assert transform({SID:33},33,33,answer('KEEP',direction='POSITIVE'),'B')[SID]==33
    assert transform({SID:33},33,33,answer('KEEP',materiality='MODERATE'),'B')[SID]==33


def test_real_kernel_anchor_and_expiry():
    fixture=runpy.run_path('tests/test_news_preopen_execution_probe_v1.py')['fixture'];i,b=fixture();a=answer('REDUCE_HOLDING','0','1/2')
    result=replay(i,b,'NO_CHANGE',target_transform=lambda q,state:transform(q,4,4,a,'A'))
    assert [r['shares'][SID] for r in result['book']['daily_ledger']]==[2,2,4]
    assert [t['target'][SID] for t in result['trace']]==[2,2,4]


def test_fraction_contradiction_rejected():
    try:transform({SID:33},33,33,answer('PAUSE_BUY','1'),'A')
    except ValueError:pass
    else:raise AssertionError('inconsistent action passed')


def test_unreviewed_or_wrong_answer_hash_cannot_execute():
    import tempfile,json
    from pathlib import Path
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for name,data in [('contract.json',{}),('answer.json',answer('KEEP')),('review.json',{'status':'APPROVED_FOR_FIXED_REPLAY','mechanical_pass':True,'semantic_pass':True,'source_contract_sha256':'wrong','answer_sha256':'wrong'})]:
            (root/name).write_text(json.dumps(data))
        try:validate(root,'contract.json','answer.json','review.json')
        except ValueError as error:assert str(error)=='INDEPENDENT_REVIEW_REQUIRED'
        else:raise AssertionError('unbound answer admitted')


def test_manual_path_still_requires_all_exact_action_quotes():
    from scripts.research.run_news_early_three_arm_v1 import verify_action_evidence
    a={'A_direct':{'evidence':[{'source_id':'early','quote':'actual statement'}]},'B_signal':{'evidence':[{'source_id':'early','quote':'actual statement'}]}}
    verify_action_evidence(a,'one actual statement here','early')
    a['B_signal']['evidence'][0]['quote']='actual altered statement'
    try:verify_action_evidence(a,'one actual statement here','early')
    except ValueError:pass
    else:raise AssertionError('changed quote admitted')
    a['B_signal']['evidence'][0]={'source_id':'late SEC','quote':'actual statement'}
    try:verify_action_evidence(a,'one actual statement here','early')
    except ValueError:pass
    else:raise AssertionError('other source admitted')
