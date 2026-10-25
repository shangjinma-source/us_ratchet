"""Apply existing 253 regular-way session rule to two documented spin-offs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tmp/qqq_20201231_anchor_20261025'
EVIDENCE = {
    'CEG': dict(regular_way_start='2022-02-02', known_asof='2022-02-01',
                source_references=['https://boxoptions.com/assets/BOXOnnMemo205387.pdf',
                    'https://investors.exeloncorp.com/static-files/96e979a6-d649-4a2a-8e43-95bfd34c67b6'],
                local_evidence='docs/exc_ceg_distribution_evidence_20261025.md',
                when_issued_start='2022-01-19', when_issued_symbol='CEGVV'),
    'GEHC': dict(regular_way_start='2023-01-04', known_asof='2023-01-04',
                source_references=['https://investor.gehealthcare.com/news-releases/news-release-details/ge-healthcare-completes-spin-and-begins-trading-nasdaq',
                    'https://classic.nasdaqtrader.com/TraderNews.aspx?id=eca2022-405'],
                when_issued_symbol='GEHCV', evidence_kind='PRIMARY_NOTICE_WEB_REVIEW_NOT_RAW_HTML')}


def review():
    paths = [OUT/'monthly_member_domain_v1.json', ROOT/'tmp/free_history_price_probe_20261025_v1/AAPL.response',
             ROOT/'docs/exc_ceg_distribution_evidence_20261025.md']
    source_hashes = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    domain = json.loads(paths[0].read_bytes())
    response = json.loads(paths[1].read_bytes())
    sessions = [datetime.fromtimestamp(t, timezone.utc).date().isoformat() for t in response['chart']['result'][0]['timestamp']]
    records = []
    for window in domain['decisions']:
        cutoff = window['decision_cutoff']
        for ticker,evidence in EVIDENCE.items():
            if ticker not in window['full_members']:
                continue
            regular = [d for d in sessions if evidence['regular_way_start'] <= d <= cutoff]
            short = len(regular) < 253
            records.append(dict(ticker=ticker, decision_cutoff=cutoff,
                regular_way_session_count=len(regular), required_sessions=253,
                status='EXCLUDED_TRAINING_RULE' if short else 'HISTORY_LENGTH_RULE_SATISFIED',
                reason='INSUFFICIENT_253_SESSION_PREDECISION_HISTORY' if short else None,
                known_asof=evidence['known_asof'], evidence_available_by_decision=evidence['known_asof']<=cutoff,
                first_regular_way=evidence['regular_way_start'], when_issued_accepted_for_training=False,
                source_references=evidence['source_references'], member_preserved=True,
                distribution_holdings_valuation_exempted=False, full_price_identity_admission=False,
                regular_training_dates=regular[-253:], missing_regular_history_count=max(0,253-len(regular))))
    return dict(status='REGULAR_WAY_HISTORY_RULE_REVIEW', source_hashes=source_hashes, evidence=EVIDENCE, records=records,
        limitations=['Date counts use the existing three-security-agreed observed session calendar.',
        'Resolved training exclusion does not delete index members or remove valuation duties for distributed holdings.',
        'Other provider-left-edge gaps are not automatically new listings; this resolves only CEG and GEHC.',
        'History length passing does not certify price units, identity, completeness, or other actions.'])


if __name__ == '__main__':
    result = review()
    (OUT/'regular_way_eligibility_v1.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({ticker:{'excluded':[r['decision_cutoff'] for r in result['records'] if r['ticker']==ticker and r['status']=='EXCLUDED_TRAINING_RULE'],
                             'first_history_length_pass':next((r['decision_cutoff'] for r in result['records'] if r['ticker']==ticker and r['status']=='HISTORY_LENGTH_RULE_SATISFIED'),None)}
                      for ticker in EVIDENCE}))
