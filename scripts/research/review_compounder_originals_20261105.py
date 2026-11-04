"""Read five existing sampled filings; no network, signals or trades."""
import json
import re
import hashlib
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'tmp/early_compounder_inventory_20261105'
CONCEPTS = {'RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues',
            'SalesRevenueNet', 'GrossProfit', 'Assets',
            'NetCashProvidedByUsedInOperatingActivities',
            'WeightedAverageNumberOfDilutedSharesOutstanding',
            'WeightedAverageNumberOfSharesOutstandingBasic', 'EntityCommonStockSharesOutstanding'}

def main():
    results = []
    inventory = json.loads((ROOT/'tmp/historical_news_coverage_20261027/sec_event_inventory_fiscal_identity_v5.json').read_bytes())
    for locator in json.loads((OUT/'original_locators.json').read_bytes()):
        path = ROOT / locator['path']
        html = path.read_bytes()
        soup = BeautifulSoup(html, 'lxml')
        cik = path.parent.parent.name.replace('issuer_', '')
        compact = path.parent.name
        accession = compact[:10]+'-'+compact[10:12]+'-'+compact[12:]
        header_path = ROOT / f'data/cache/candidate_pools/ndx_fundamentals/sic_history_v1/raw_headers/{int(cik)}/{accession}.header.txt'
        header = header_path.read_text()
        accepted = datetime.strptime(re.search(r'<ACCEPTANCE-DATETIME>(\d{14})', header)[1], '%Y%m%d%H%M%S').replace(tzinfo=ZoneInfo('America/New_York')).isoformat()
        form = re.search(r'CONFORMED SUBMISSION TYPE:\s*(\S+)', header)[1]
        report_end = re.search(r'CONFORMED PERIOD OF REPORT:\s*(\d+)', header)[1]
        contexts = {}
        for context in soup.find_all('xbrli:context'):
            def content(tag):
                node = context.find('xbrli:'+tag)
                return node.get_text(strip=True) if node else None
            identifier = context.find('xbrli:identifier')
            contexts[context['id']] = dict(entity_cik=identifier.get_text(strip=True) if identifier else None,
                start=content('startdate'), end=content('enddate') or content('instant'),
                dimensional=bool(context.find('xbrli:segment') or context.find('xbrli:scenario')))
        units = {u['id']: [m.get_text(strip=True) for m in u.find_all('xbrli:measure')]
                 for u in soup.find_all('xbrli:unit')}
        raw_path = ROOT / f'data/cache/candidate_pools/ndx_fundamentals/raw_companyfacts/CIK{cik}.json'
        facts = json.loads(raw_path.read_bytes())['facts']
        records = []
        for fact in soup.find_all('ix:nonfraction'):
            name = fact.get('name','')
            if ':' not in name or name.split(':')[1] not in CONCEPTS:
                continue
            context = contexts.get(fact.get('contextref'), {})
            if not context or context['dimensional']:
                continue
            if not context['entity_cik'] or int(context['entity_cik']) != int(cik):
                raise ValueError('CONTEXT_ENTITY_MISMATCH')
            text = fact.get_text(strip=True).replace(',', '').replace('−','-').replace('—','0').replace('–','0')
            if text in ('', '-'): text = '0'
            value = Decimal(text.strip('()')) * (Decimal(10) ** int(fact.get('scale',0)))
            if fact.get('sign') == '-' or text.startswith('('): value = -value
            namespace, concept = name.split(':')
            measures = units.get(fact.get('unitref'), [])
            unit = measures[0].split(':')[-1] if len(measures)==1 else '|'.join(measures)
            matching = [f for f in facts.get(namespace,{}).get(concept,{}).get('units',{}).get(unit,[])
                        if f.get('accn') == accession and f.get('end') == context['end'] and f.get('start') == context['start']]
            values = sorted({str(Decimal(str(f['val']))) for f in matching})
            duration = (datetime.fromisoformat(context['end'])-datetime.fromisoformat(context['start'])).days+1 if context['start'] else None
            record = dict(concept=name, context_id=fact.get('contextref'), unit=unit, **context,
                          duration_days=duration, original_value=str(value), companyfacts_values=values,
                          exact_match=bool(matching) and all(Decimal(v)==value for v in values),
                          period_type='instant' if duration is None else 'quarter' if 70<=duration<=105 else 'cumulative_or_other_duration')
            if record not in records: records.append(record)
        event_acceptances = sorted({e['acceptance'] for e in inventory['issuers'][cik]['events'] if e['accession']==accession})
        acceptance_matches = bool(event_acceptances) and all(datetime.fromisoformat(a)==datetime.fromisoformat(accepted) for a in event_acceptances)
        if not acceptance_matches:
            raise ValueError('ACCEPTANCE_MISMATCH')
        results.append(dict(path=locator['path'], sha256=hashlib.sha256(html).hexdigest(),
            header_path=str(header_path.relative_to(ROOT)), header_sha256=hashlib.sha256(header_path.read_bytes()).hexdigest(),
            companyfacts_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            cik=cik, accession=accession, acceptance_eastern=accepted, form=form, report_end=report_end,
            acceptance_matches_existing_event_inventory=acceptance_matches,
            original_filing_not_amendment=form=='10-Q', records=records,
            limitations=['Acceptance is SEC filing time, not verified earliest earnings release.',
                        'Original 10-Q does not certify full revision chain or latest available filing at cutoff.',
                        'Diluted weighted shares are not market capitalization shares.']))
    (OUT/'five_originals_review.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    for r in results:
        print(r['path'],r['acceptance_eastern'],len(r['records']),sum(x['exact_match'] for x in r['records']))

if __name__ == '__main__': main()
