"""Bounded local inventory only. No signals, downloads or backtest."""
import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'tmp/early_compounder_inventory_20261105'
DOMAIN = ROOT / 'tmp/qqq_20201231_anchor_20261025/monthly_member_domain_v1.json'
INVENTORY = ROOT / 'tmp/historical_news_coverage_20261027/sec_event_inventory_fiscal_identity_v5.json'
FIELDS = {
    'revenue': ['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'SalesRevenueNet'],
    'net_income': ['NetIncomeLoss', 'ProfitLoss'],
    'gross_profit': ['GrossProfit'], 'assets': ['Assets'],
    'operating_cash_flow': ['NetCashProvidedByUsedInOperatingActivities'],
    'capital_expenditure': ['PaymentsToAcquirePropertyPlantAndEquipment'],
    'cash': ['CashAndCashEquivalentsAtCarryingValue'],
    'debt_component_only': ['LongTermDebtCurrent', 'LongTermDebtNoncurrent', 'LongTermDebt'],
    'diluted_shares': ['WeightedAverageNumberOfDilutedSharesOutstanding'],
    'equity': ['StockholdersEquity'],
}

def main():
    inventory = json.loads(INVENTORY.read_bytes())
    domain = json.loads(DOMAIN.read_bytes())
    mappings = {}
    for window in inventory['windows']:
        for row in window['rows']:
            for ticker in row['tickers']:
                if row.get('cik'):
                    mappings.setdefault(ticker, set()).add(row['cik'])
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (DOMAIN, INVENTORY)}
    results = []
    for cutoff in ('2020-12-31', '2021-12-31'):
        decision = next(x for x in domain['decisions'] if x['decision_cutoff'] == cutoff)
        members = sorted(decision['full_members'])
        # Six evenly spaced names per predeclared cutoff, twelve checks maximum.
        sample = [members[i * (len(members) - 1) // 5] for i in range(6)]
        rows = []
        for ticker in members:
            ciks = sorted(mappings.get(ticker, []))
            row = dict(ticker=ticker, cik_candidates=ciks, historical_identity_certified=False,
                       fields={}, sampled=ticker in sample)
            if len(ciks) != 1:
                row['reason'] = 'MISSING_OR_AMBIGUOUS_CIK_LEAD'
                rows.append(row)
                continue
            cik = ciks[0]
            path = ROOT / f'data/cache/candidate_pools/ndx_fundamentals/raw_companyfacts/CIK{cik}.json'
            if not path.exists():
                row['reason'] = 'RAW_COMPANYFACTS_MISSING'
                rows.append(row)
                continue
            hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
            raw = json.loads(path.read_bytes()).get('facts', {}).get('us-gaap', {})
            events = [e for e in inventory['issuers'].get(cik, {}).get('events', [])
                      if e.get('acceptance', '')[:10] <= cutoff and e.get('acceptance')]
            accepted = {e['accession']: e['acceptance'] for e in events}
            for name, concepts in FIELDS.items():
                facts = [dict(f, concept=c, unit=u) for c in concepts
                         for u, values in raw.get(c, {}).get('units', {}).items() for f in values
                         if f.get('filed', '9999') <= cutoff and f.get('end', '9999') <= cutoff]
                recent = [f for f in facts if f['end'] >= str(int(cutoff[:4]) - 1) + cutoff[4:]]
                row['fields'][name] = dict(raw_prior_filing_candidate=bool(recent),
                    accepted_accession_candidate=any(f.get('accn') in accepted for f in recent),
                    latest_period_end=max((f['end'] for f in recent), default=None),
                    original_version_verified=False)
            row['available_event_count'] = len(events)
            row['latest_event'] = max(events, key=lambda e:e['acceptance']) if events else None
            row['original_review_status'] = 'NO_ORIGINAL_BINDING_IN_INVENTORY' if row['sampled'] else 'NOT_SAMPLED'
            rows.append(row)
        results.append(dict(cutoff=cutoff, member_count=len(members), sample=sample,
            universe='CONDITIONAL_HISTORICAL_NDX_NOT_ALL_US',
            membership_blockers=decision['date_membership_blockers'],
            unavailable_event_sources=decision['unavailable_event_sources'],
            existing_removed_examples=[x for x in ('ALXN','ATVI','XLNX','SGEN','PTON','LCID') if x in members],
            mapped_companyfacts=sum(bool(r['fields']) for r in rows),
            coverage={field:{kind:sum(r['fields'].get(field,{}).get(kind,False) for r in rows)
                       for kind in ('raw_prior_filing_candidate','accepted_accession_candidate','original_version_verified')}
                      for field in FIELDS}, rows=rows))
    OUT.mkdir(parents=True, exist_ok=True)
    result = dict(schema='EARLY_COMPOUNDER_LOCAL_FEASIBILITY_V1', source_hashes=hashes,
                  results=results, caveats=['Raw companyfacts are leads, not verified PIT values.',
                  'Acceptance joins use existing direct-quarter event extraction, so zero is not proof of absent submissions.',
                  'Fields are presence checks, not compatible TTM/units/valuation ratios.',
                  'Sample checks certify only missing original bindings in this inventory, not absence from every disk file.'])
    (OUT/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps([{k:v for k,v in r.items() if k!='rows'} for r in results],indent=2))

if __name__ == '__main__':
    main()
