"""Read-only current-month inputs; never publishes an executable target."""
from collections import Counter
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path

from scripts.research.describe_annual_quality_local_20261106 import select, cik_matches

ROOT = Path(__file__).resolve().parents[2]


def main():
    path = ROOT/'tmp/monthly_recovery_20261103/training_scoped_publication/manifest.json'
    raw = path.read_bytes()
    manifest = json.loads(raw)
    assert manifest['decision_date'] == '2026-10-30'
    dates = manifest['training_dates']
    assert len(dates) == 253 and dates == sorted(set(dates)) and dates[-1] == '2026-10-30'
    pins = {str(path.relative_to(ROOT)):sha256(raw).hexdigest()}
    rows = []
    # Same quarterly refresh convention as the frozen historical candidate.
    financial_cutoff = '2026-09-30'
    for candidate in manifest['candidates']:
        row = dict(security_id=candidate['security_id'], issuer_id=candidate['issuer_id'],
            ticker=candidate['ticker'], financial_cutoff=financial_cutoff)
        rows.append(row)
        issuer = candidate['issuer_id']
        if not issuer.startswith('issuer:') or not issuer[7:].isdigit():
            row['status']='ISSUER_CIK_UNAVAILABLE';continue
        cik = issuer[7:]
        facts_path=ROOT/'data/cache/candidate_pools/ndx_fundamentals/raw_companyfacts'/('CIK'+cik+'.json')
        if not facts_path.is_file():
            row['status']='COMPANYFACTS_MISSING';continue
        data=facts_path.read_bytes();pins[str(facts_path.relative_to(ROOT))]=sha256(data).hexdigest()
        facts=json.loads(data,parse_float=Decimal)
        if not cik_matches(cik,facts.get('cik')):
            row['status']='CIK_MISMATCH';continue
        financial=select(facts.get('facts',{}).get('us-gaap',{}),{},financial_cutoff)
        row['financial']=financial
        row['status']=financial['status']
        if financial['status']!='DESCRIPTIVE_RAW_SAME_VERSION':continue
        fields=financial['fields']
        row['positive_ni_ocf']=all(Fraction(fields[k]['value_exact'])>0 for k in
            ('NetIncomeLoss','NetCashProvidedByUsedInOperatingActivities'))
        prices=list(map(Fraction,candidate['raw_close']))
        assert len(prices)==253 and all(p>0 for p in prices)
        row['momentum_ratio_exact']=str(prices[-22]/prices[-253])
        row['roa_exact']=financial['ratios']['net_income_over_ending_assets']
    output=dict(status='CURRENT_MONTH_INPUT_PREFLIGHT_NOT_LIVE_SELECTION',decision_date=dates[-1],
        financial_cutoff=financial_cutoff,rows=rows,source_hashes=pins,
        counts=dict(Counter(r['status'] for r in rows)),
        positive_ni_ocf=sum(r.get('positive_ni_ocf',False) for r in rows),
        production_activated=False,orders_created=False,
        pending=['Authenticate inherited training dependencies and current identity/actions',
                 'Use fresh completed-session QQQ state through latest prior close',
                 'Financial source availability/revision checks remain conditional',
                 'Full economic admission and live account/target integration'])
    target=ROOT/'tmp/roa_november_inputs_20261106.json'
    target.write_text(json.dumps(output,default=str,indent=2),encoding='utf-8')
    print(json.dumps({k:output[k] for k in ('status','counts','positive_ni_ocf')},indent=2))


if __name__=='__main__':
    main()
