"""Offline dated research mapping candidates, never automatic PIT admission."""
import csv
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = dict(
        identity='data/cache/candidate_pools/ndx_taxonomy_v2_annual_repair_plan/security_identity.csv',
        crosswalk='data/cache/candidate_pools/ndx_fundamentals/cik_crosswalk.csv',
        holdings='data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv',
        inputs='tmp/recent_continuous_baseline_20261026_v7/execution_inputs.json',
        book='tmp/recent_continuous_baseline_20261026_v7/book.json')
    pins = {name:dict(path=path,sha256=sha256((ROOT/path).read_bytes()).hexdigest()) for name,path in paths.items()}
    tables = {name:list(csv.DictReader((ROOT/paths[name]).open(encoding='utf-8-sig'))) for name in ('identity','crosswalk','holdings')}
    inputs=json.loads((ROOT/paths['inputs']).read_bytes())
    book=json.loads((ROOT/paths['book']).read_bytes())
    dates={}
    for row in book['daily_ledger']:
        for sid,q in row['shares'].items():
            if q:dates.setdefault(sid,set()).add(row['date'])
    for row in book['order_log']:
        if row.get('event')=='ASSUMED_NEXT_OPEN_FILLED':dates.setdefault(row['security_id'],set()).add(row['date'])
    aliases={r['security_id']:r for r in inputs['dated_ticker_aliases']}
    metadata={sid:m for plan in inputs['assembled']['monthly_inputs'] for sid,m in plan['search_arguments']['metadata'].items()}
    rows=[]
    for sid,days in sorted(dates.items()):
        ticker=metadata[sid]['ticker'];names={ticker}
        if sid in aliases:names.update((aliases[sid]['before'],aliases[sid]['after']))
        identities=[r for r in tables['identity'] if names.intersection(r['ticker_set'].split(';')) and r['identity_status']=='resolved']
        ciks={r['cik'].zfill(10) for r in identities}
        crosswalk=[r for r in tables['crosswalk'] if r['ticker'] in names]
        cusips={r['cusip'] for r in identities}
        observations=[r for r in tables['holdings'] if r['ticker'] in names and r['cusip'] in cusips and r['available_date']<=max(days)]
        observations.sort(key=lambda r:(r['available_date'],r['ticker'],r['cusip']))
        prior=[r for r in observations if r['available_date']<=min(days)]
        rows.append(dict(research_security_id=sid,ticker=ticker,cik=next(iter(ciks)) if len(ciks)==1 else None,
            mapping_status='DATED_LOCAL_MAPPING_CANDIDATE_NOT_PIT_ADMITTED' if len(ciks)==1 and observations else 'GAP',
            first_actual_exposure=min(days),last_actual_exposure=max(days),identity_rows=identities,
            crosswalk_rows=crosswalk,alias=aliases.get(sid),dated_observations=observations,
            available_observation_before_first_exposure=bool(prior),
            earliest_prior=prior[0] if prior else None,
            source_references=pins,
            gaps=['Research SID links to historical ticker/CUSIP rows, but original issuer filing proof of CIK identity is not reverified here.',
                  'Historical holdings report dates are observations, not proof of uninterrupted ticker/class identity.',
                  'CIK crosswalk method may use current ticker; it is retained and not promoted to historical proof.'] +
                 ([] if prior else ['No cached holdings identity observation available before first exposure.'])))
    result=dict(status='RESEARCH_MAPPING_CANDIDATES_ONLY',source_hashes=pins,rows=rows,
                original_filing_identity_verified=False,point_in_time_certified=False)
    out=ROOT/'tmp/historical_news_identity_20261027';out.mkdir(exist_ok=True)
    (out/'mapping_candidate.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# 早窗18个实际持仓/成交证券的历史身份核查','','找到历史身份表、原报告日期/可用日期和ticker-CUSIP观察，可复用为独立研究映射候选；未将当今ticker映射提升为已证PIT。原基准不变。','',
           '| ticker | CIK候选 | 首暴露 | 首暴露前已有日期观察 | crosswalk方法 |','|---|---|---|---|---|']
    for r in rows:lines.append('| '+' | '.join([r['ticker'],r['cik'] or '缺口',r['first_actual_exposure'],str(r['available_observation_before_first_exposure']),';'.join(sorted({x['mapping_method'] for x in r['crosswalk_rows']}))])+' |')
    lines += ['', '逐条历史观察、报告source_locator、CUSIP、身份表行、原alias、文件sha256均在mapping_candidate.json。CIK候选不是证券全生命周期已证；原始发行人文件中的CIK/名称/证券类别链尚需针对事件日期核对。尤其crosswalk采用sec_current_ticker_exact的行仍有历史证明缺口。',
              'META/FB使用基准已冻结2022-06-09更名关系；SGEN多CUSIP不合并为单一证券类证明。不得用汇总observation_from/to宣称之间每天都有原始证据。']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps(dict(securities=len(rows),unique_cik_candidates=sum(bool(r['cik']) for r in rows),
        prior_observation=sum(r['available_observation_before_first_exposure'] for r in rows),report=str(out)),indent=2))


if __name__=='__main__':main()
