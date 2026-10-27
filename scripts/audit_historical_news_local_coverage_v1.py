"""Read only declared public SEC caches and two frozen research accounts. No network."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ('recent_continuous_baseline_20261026_v7', 'old_continuous_baseline_20261026_v9')


def read(path):
    raw = path.read_bytes()
    return json.loads(raw), dict(path=path.relative_to(ROOT).as_posix(), sha256=sha256(raw).hexdigest())


def main():
    roots = [ROOT/'data/cache/research/current_92_sec_submissions_capture_20260919_v1',
             ROOT/'data/cache/research/current_sec_exchange_refresh_20260919_v1',
             ROOT/'data/cache/research/three_historical_cusip_capture_20260919_v1',
             ROOT/'tmp/current_five_sec_refresh_20261015_v1', ROOT/'data/cache/news/raw']
    roots += sorted((ROOT/'data/cache/candidate_pools').glob('**/raw_submissions'))
    roots += [ROOT/'tmp'/name for name in ('previous10_sec_identity_recapture_20261016_v1',
        'remaining75_sec_identity_capture_20261016_v1', 'remaining86_sec_identity_capture_20261016_v1',
        'remaining_nine_sec_capture_author_review_20261009_v1', 'remaining_nine_sec_capture_author_review_20261009_v2')]
    facts_root = ROOT/'data/cache/candidate_pools/ndx_fundamentals/raw_companyfacts'
    submissions, facts, ticker_candidates = defaultdict(list), defaultdict(list), defaultdict(set)
    rejected = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.stat().st_size > 30_000_000:
                continue
            try:
                document, evidence = read(path)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(document, dict) or not document.get('cik') or not isinstance(document.get('filings'), dict):
                continue
            cik = str(int(document['cik'])).zfill(10)
            recent = document['filings'].get('recent', {})
            dates = recent.get('filingDate', [])
            acceptance = recent.get('acceptanceDateTime', [])
            evidence.update(cik=cik, tickers=document.get('tickers', []), filings=[])
            for i, day in enumerate(dates):
                value = acceptance[i] if i < len(acceptance) else None
                evidence['filings'].append(dict(date=day, acceptance=value,
                    accession=recent.get('accessionNumber', [])[i] if i < len(recent.get('accessionNumber', [])) else None))
            submissions[cik].append(evidence)
            for ticker in document.get('tickers', []):
                ticker_candidates[ticker].add(cik)
    for path in sorted(facts_root.glob('CIK*.json')):
        try:
            document, evidence = read(path)
            cik = str(int(document['cik'])).zfill(10)
            if path.stem != 'CIK'+cik or not isinstance(document.get('facts'), dict):
                raise ValueError('FACT_IDENTITY_OR_SCHEMA')
            evidence.update(cik=cik, entity_name=document.get('entityName'))
            facts[cik].append(evidence)
        except (ValueError, KeyError) as error:
            rejected.append(dict(path=path.relative_to(ROOT).as_posix(), reason=str(error)))
    windows = []
    for name in WINDOWS:
        directory = ROOT/'tmp'/name
        inputs, input_pin = read(directory/'execution_inputs.json')
        book, book_pin = read(directory/'book.json')
        plans = inputs['assembled']['monthly_inputs']
        domain, metadata = set(), defaultdict(list)
        held = {sid for row in book['daily_ledger'] for sid, count in row['shares'].items() if count}
        traded = {row['security_id'] for row in book['order_log']
                  if row.get('security_id') and row.get('event') == 'ASSUMED_NEXT_OPEN_FILLED'}
        for plan in plans:
            domain.update(plan['search_arguments']['prices'])
            for sid, meta in plan['search_arguments']['metadata'].items():
                metadata[sid].append(meta)
        start, end = inputs['assembled']['session_dates'][0], inputs['assembled']['session_dates'][-1]
        rows = []
        for sid in sorted(domain | held | traded):
            tickers = sorted({m['ticker'] for m in metadata[sid] if m.get('ticker')})
            match = re.fullmatch(r'security:(\d{10}):[^:]+', sid)
            proven = match.group(1) if match else None
            candidates = sorted({c for ticker in tickers for c in ticker_candidates[ticker]})
            cik = proven or (candidates[0] if len(candidates) == 1 else None)
            entries = submissions.get(cik, [])
            filing_rows = {r['accession']:r for entry in entries for r in entry['filings'] if start <= r['date'] <= end}
            rows.append(dict(security_id=sid, tickers=tickers, in_price_domain=sid in domain,
                actually_held=sid in held, actually_traded=sid in traded,
                cik=cik, cik_proven_in_frozen_identity=bool(proven),
                cik_mapping_status='FROZEN_SID_CIK' if proven else 'CURRENT_SUBMISSIONS_TICKER_LEAD_NOT_HISTORICAL_PROOF' if cik else 'UNRESOLVED',
                candidate_ciks=candidates, submissions_sources=[{k:v for k,v in x.items() if k!='filings'} for x in entries],
                companyfacts_sources=facts.get(cik, []), interval_filings=len(filing_rows),
                interval_filings_with_acceptance=sum(bool(r['acceptance']) for r in filing_rows.values()),
                missing_historical_acceptance=not filing_rows or any(not r['acceptance'] for r in filing_rows.values()),
                historical_acceptance_completeness='NOT_ESTABLISHED_RECENT_SUBMISSIONS_ONLY'))
        def counts(selected):
            return dict(securities=len(selected), cik_proven=sum(r['cik_proven_in_frozen_identity'] for r in selected),
                cik_resolved_or_lead=sum(bool(r['cik']) for r in selected), submissions_present=sum(bool(r['submissions_sources']) for r in selected),
                facts_present=sum(bool(r['companyfacts_sources']) for r in selected),
                any_interval_acceptance=sum(r['interval_filings_with_acceptance']>0 for r in selected),
                missing_historical_acceptance=sum(r['missing_historical_acceptance'] for r in selected))
        windows.append(dict(window=name, start=start, end=end, inputs=input_pin, book=book_pin,
            price_domain=counts([r for r in rows if r['in_price_domain']]),
            held_or_traded=counts([r for r in rows if r['actually_held'] or r['actually_traded']]), rows=rows))
    output=ROOT/'tmp/historical_news_coverage_20261027'
    output.mkdir(exist_ok=True)
    result=dict(scope=[p.relative_to(ROOT).as_posix() for p in roots+[facts_root]],
        scope_note='Explicit public cache roots only; absent means absent in this inventory, not everywhere on disk.',
        limitations=['Current ticker matches are leads, not dated identity proof.',
            'Companyfacts latest snapshots may contain revised values; presence is not PIT usability.',
            'Acceptance availability does not prove full historical filings coverage or release time.',
            'No losing-stock selection; complete price domain and actual holdings/trades audited.'],
        submissions_ciks=len(submissions), facts_ciks=len(facts), rejected=rejected, windows=windows)
    (output/'coverage.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    lines = ['# 本地历史新闻/财报数据覆盖清点', '',
        '完整价格域及实际持仓/成交域均纳入，没有按亏损筛选。以下为指定公开缓存目录内的存在性检查，不是历史PIT准入。', '',
        '| 窗口 / 域 | SID数 | 冻结身份含CIK | CIK或唯一ticker线索 | submissions | companyfacts | 有区间acceptance | 无/缺acceptance |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for window in windows:
        for scope in ('price_domain', 'held_or_traded'):
            count = window[scope]
            lines.append('| '+window['window']+' / '+scope+' | '+ ' | '.join(str(count[key]) for key in (
                'securities','cik_proven','cik_resolved_or_lead','submissions_present','facts_present',
                'any_interval_acceptance','missing_historical_acceptance'))+' |')
    lines += ['', '早窗research SID不含CIK；当前submissions ticker匹配只作线索，未冒充已证历史身份。后窗CIK来自冻结SID，仍不代表全部历史原文/时间已核验。',
        '有acceptance仅表示区间内至少一份已缓存申报有该字段；完整历史覆盖对所有行仍标NOT_ESTABLISHED。Companyfacts为现时快照，修订值不可直接当当时已知。',
        '逐SID、缓存文件路径/hash、基准输入/book hash、所有扫描目录与缺口见coverage.json。旧raw未重建虚假采集时间。']
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps([{k:v for k,v in window.items() if k not in ('rows','inputs','book')} for window in windows],indent=2))


if __name__ == '__main__':main()
