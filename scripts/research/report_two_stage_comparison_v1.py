"""Aggregate four fixed complete independently reviewed branches, never partial annualization."""
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
import json
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.research.two_stage_execution_activity_v1 import activity
BASE=ROOT/'tmp/two_stage_bull_bear_20261029'
WINDOWS={'2021_2023':('recent_continuous_baseline_20261026_v7',{'BUY_TWO_OPENS':'buy_two_opens_2021_2023','CAP_SELL_TWO_OPENS':'cap_sell_two_opens_2021_2023'}),'2024_2026':('old_continuous_baseline_20261026_v9',{'BUY_TWO_OPENS':'buy_two_opens_2024_2026_resumed','CAP_SELL_TWO_OPENS':'cap_sell_two_opens_2024_2026'})}
def read(p):return json.loads(p.read_bytes())
def main():
    rows=[];pins={}
    def pin(p):pins[str(p.relative_to(ROOT)).replace('\\','/')]=sha256(p.read_bytes()).hexdigest()
    for window,(original,cases) in WINDOWS.items():
        bp=ROOT/'tmp'/original;original_report=read(bp/'generic_complete_report_v1.json');pin(bp/'generic_complete_report_v1.json')
        ba=read(BASE/('baseline_activity_'+window+'.json'));pin(BASE/('baseline_activity_'+window+'.json'))
        all_cases=[('BASELINE',original_report,ba)]
        for mode,name in cases.items():
            directory=BASE/name;proof=read(directory/'independent_review.json');report=read(directory/'verified_report.json')
            if proof['status']!='COMPLETE_DECLARED_INTERVAL_REVIEW_PASS' or report['status']!='COMPLETE_VERIFIED_ACCOUNT_REPORT':raise ValueError('ALL_FOUR_COMPLETE_REQUIRED')
            for filename in ['independent_review.json','verified_report.json','book.json']:
                pin(directory/filename)
            expected=report['input_hashes']
            if expected['book']!=sha256((directory/'book.json').read_bytes()).hexdigest() or expected['review']!=sha256((directory/'independent_review.json').read_bytes()).hexdigest():raise ValueError('REPORT_BINDING_MISMATCH')
            all_cases.append((mode,report,proof['activity']))
        for mode,report,act in all_cases:
            rows.append(dict(window=window,mode=mode,start=report['start_date'],end=report['end_date'],cagr=report['cagr'],maximum_drawdown=float(F(report['drawdown']['maximum_drawdown'])),filled_orders=act['filled_order_count'],buy_fills=act['buy_fills'],sell_fills=act['sell_fills'],direction_switches=act['buy_sell_direction_switch_count'],cash_unfilled=act['partially_or_fully_cash_unfilled_order_count'],repeat_cash_unfilled=act['repeated_cash_unfilled_beyond_first_by_security'],above_cap_sessions=act['above_cap_session_count'],maximum_above_cap_notional=act['maximum_above_cap_close_notional']))
    result=dict(status='FOUR_FIXED_BRANCHES_COMPLETE_INDEPENDENTLY_REVIEWED',rows=rows,source_hashes=pins,production_adopted=False,limitations=['Specified historical windows and accounting verified; point-in-time constituent/survivorship and conditional provider evidence limitations remain.','All new BUY gaps were staged; no external user deposits were synthesized.','Zero commission and five basis point slippage; gross dividends and next-open modeled fills.','Trade counts and direction changes are source-bound generated order-log statistics, not every log field separately certified.','Direction changes counted per security ID, not merged across issuer identity changes.','Slower execution may increase order count; CAP candidate explicitly permits temporary quantity-cap excess.','No parameter sweep, no additional compound candidate, no proof of future reliability.'])
    (BASE/'comparison.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    labels={'BASELINE':'原V27','BUY_TWO_OPENS':'A 新买分两次','CAP_SELL_TWO_OPENS':'B 纯限仓卖出分两次'}
    lines=['# 固定两机制完整历史账户对照','','两段指定区间均完整核验；这不等于历史数据无偏，也未自动部署。','','| 区间 | 方案 | 年化 | 最大收盘回撤 | 成交 买/卖 | 买卖方向切换 | 现金未足额记录 | 超月数量cap会话 |','|---|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:lines.append(f"| {r['window']} | {labels[r['mode']]} | {r['cagr']*100:.2f}% | {r['maximum_drawdown']*100:.2f}% | {r['filled_orders']} ({r['buy_fills']}/{r['sell_fills']}) | {r['direction_switches']} | {r['cash_unfilled']} | {r['above_cap_sessions']} |")
    lines+=['','A覆盖所有新增买入缺口，并非模拟真实入金。B只缓冲已归因于50%数量裁剪的卖出，不延迟20%退出或选股移除；临时超量风险必须另计。两次成交可能增加操作次数，不能称更少交易。','','后窗只至2026-07-30；早窗仍存在很深回撤，不能说已解决最大回撤。原历史成分、可得时点和条件性公司行动证据局限保留。这里只运行冻结的两候选，没有组合第三候选或按结果调参。','']
    (BASE/'comparison.md').write_text('\n'.join(lines),encoding='utf-8');print(result['status'])
if __name__=='__main__':main()
