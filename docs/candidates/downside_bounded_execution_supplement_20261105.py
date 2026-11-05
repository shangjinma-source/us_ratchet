"""Translate only the already reviewed bounded supplement into execution evidence."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from hashlib import sha256
import json

SUPPLEMENT='tmp/risk_budget_64d_inventory_20261105/bounded_supplement.json'
EXPECTED='a8403a199107749ed6cc5ed423f46e877d0f080880dbd4487d505c749bc0f9ba'


def extend_execution_evidence(*,root,document,prices,review):
    root=Path(root);raw=(root/SUPPLEMENT).read_bytes()
    if sha256(raw).hexdigest()!=EXPECTED:raise ValueError('BOUNDED_SUPPLEMENT_CHANGED')
    source=json.loads(raw);pins={SUPPLEMENT:EXPECTED,**source['source_hashes']}
    for name,h in source['source_hashes'].items():
        if sha256((root/name).read_bytes()).hexdigest()!=h:raise ValueError('BOUNDED_EVIDENCE_CHANGED:'+name)
    output=deepcopy(document);updated=deepcopy(review);dates=output['assembled']['session_dates']
    metadata={}
    for plan in output['assembled']['monthly_inputs']:
        for sid,row in plan['search_arguments']['metadata'].items():
            ticker=row['ticker']
            if sid in metadata and metadata[sid]!=ticker:raise ValueError('SID_TICKER_CONFLICT')
            metadata[sid]=ticker
    by_ticker={}
    for sid,ticker in metadata.items():by_ticker.setdefault(ticker,set()).add(sid)
    inventory=output.get('provider_event_inventory',prices.get('provider_event_inventory',[]))
    all_pins={**output.get('source_hashes',{}),**output['assembled']['source_hashes'],**prices.get('source_hashes',{})}
    rows=[];events=[]
    for item in source['events']:
        ex=item['ex_date'];pay=item['payment_date'];ticker=item['ticker']
        if not dates[0]<ex<=dates[-1]:continue
        observed=[e for e in inventory if e['ticker']==ticker and e['date']==ex and e['kind']=='dividends']
        explicit={e['security_id'] for e in observed if e.get('security_id')}
        effective=max((p for p in output['assembled']['monthly_inputs'] if p['decision_date']<ex),key=lambda p:p['decision_date'])
        sids=explicit or {s for s,m in effective['search_arguments']['metadata'].items() if m['ticker']==ticker}
        if not sids and len(by_ticker.get(ticker,set()))==1:sids=by_ticker[ticker]
        if len(sids)!=1:raise ValueError('UNIQUE_DIVIDEND_SID_REQUIRED:'+ticker)
        sid=next(iter(sids))
        if metadata.get(sid)!=ticker:raise ValueError('SID_METADATA_BINDING_REQUIRED')
        if ex not in dates or pay<ex or F(item['amount_per_share'])<=0:raise ValueError('INVALID_BOUND_DIVIDEND')
        if not observed:raise ValueError('EXACT_PROVIDER_EX_DATE_REQUIRED:'+ticker+':'+ex)
        for event in observed:
            if event.get('security_id',sid)!=sid:raise ValueError('PROVIDER_SID_MISMATCH')
            name=event['source'];expected=all_pins.get(name)
            if not expected or sha256((root/name).read_bytes()).hexdigest()!=expected:raise ValueError('PROVIDER_SOURCE_MISMATCH:'+name)
            pins[name]=expected
        key=(sid,ex)
        prior=[e for e in output['dividend_events'] if (e['security_id'],e['ex_date'])==key]
        expected_fields=dict(payment_date=pay,amount_per_share=str(F(item['amount_per_share'])),currency='USD',withholding_rate='0')
        if prior:
            if len(prior)!=1 or any((F(prior[0][k])!=F(v) if k in ('amount_per_share','withholding_rate') else prior[0][k]!=v) for k,v in expected_fields.items()):raise ValueError('EXISTING_DIVIDEND_CONFLICT')
            continue
        row=dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=sid,ex_date=ex,payment_date=pay,
                 amount_per_share=expected_fields['amount_per_share'],currency='USD',source_references=[SUPPLEMENT,*sorted({e['source'] for e in observed})],
                 observed_provider_events=[{k:v for k,v in e.items() if k!='security_id'} for e in observed],
                 official_url=item['url'],evidence_scope=source['source_kind'],nominal_unit=item.get('unit','ISSUER_NOMINAL_PER_SHARE'))
        # Review and execution rows are produced together; no gate-only admission.
        rows.append(row);events.append(dict(event_id='bounded-gross:'+sid+':'+ex,security_id=sid,ex_date=ex,**expected_fields,
            assumption='EXPLICIT_GROSS_RESEARCH_NO_WITHHOLDING_MODELED_NOT_USER_TAX_RATE; PAYMENT_AT_SESSION_CLOSE'))
    for item in source['absence_reviews']:
        ticker=item['ticker'];sids=by_ticker.get(ticker,set())
        if len(sids)>1:raise ValueError('UNIQUE_ABSENCE_SID_REQUIRED')
        if not sids:continue
        sid=next(iter(sids))
        # Current admitted intervals both belong to early window; derive exact monthly
        # subinterval rows for early gate's strict start equality, never extend scope.
        for plan in output['assembled']['monthly_inputs']:
            start=plan['decision_date']
            if not item['start_exclusive']<=start<item['end_inclusive']:continue
            if sid not in prices.get('action_stream_missing',[]):continue
            rows.append(dict(status='REVIEWED_NO_ACTION_FOR_PERIOD',security_id=sid,start_exclusive=start,
                end_inclusive=item['end_inclusive'],source_references=[SUPPLEMENT,*source['source_hashes']],
                evidence_strength='CONDITIONAL_RETROSPECTIVE_EXACT_SUBINTERVAL_NOT_SIGNAL',
                original_scope_start=item['start_exclusive'],original_scope_end=item['end_inclusive']))
    for row in rows:
        existing=[r for r in updated['rows'] if r['status']==row['status'] and r['security_id']==row['security_id'] and
                  (r.get('ex_date'),r.get('start_exclusive'),r.get('end_inclusive'))==(row.get('ex_date'),row.get('start_exclusive'),row.get('end_inclusive'))]
        if existing:raise ValueError('DUPLICATE_SUPPLEMENT_REVIEW')
    updated['rows'].extend(rows);updated.setdefault('source_hashes',{}).update(pins)
    output['dividend_events'].extend(events)
    return output,updated,pins,dict(added_dividends=len(events),added_absence_subintervals=sum(r['status']=='REVIEWED_NO_ACTION_FOR_PERIOD' for r in rows),events=events,review_rows=rows)
