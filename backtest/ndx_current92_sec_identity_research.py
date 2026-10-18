"""Pure current issuer observations for a fixed dated-map refresh; no security join."""
import re
from scripts import ndx_current_nine_identity_readback_20260919 as prior


def expected_refresh(issuer_map):
    if issuer_map.get('schema')!='CURRENT101_CONDITIONAL_ISSUER_MAP_V1':raise ValueError('Original conditional map required')
    rows=issuer_map['rows']
    if len(rows)!=101 or len({r['ticker'] for r in rows})!=101:raise ValueError('Complete distinct 101 input required')
    refresh={};fresh=[]
    for row in rows:
        ticker=row['ticker'];cik=row['cik']
        if type(cik) is not str or re.fullmatch('[0-9]{10}',cik) is None or row['conditional_issuer_id']!='issuer:'+cik:raise ValueError('Explicit issuer CIK coordinate required')
        if row['september_current_issuer_observation_available'] is True:
            if row['evidence_tier']!='SEPTEMBER_18_CURRENT_SUBMISSION_OBSERVATION':raise ValueError('Original fresh tier differs')
            fresh.append(ticker)
        elif row['september_current_issuer_observation_available'] is False:
            if row['evidence_tier']!='JULY_DATED_SEC_CROSSWALK_OBSERVATIONS_ONLY':raise ValueError('Original dated tier differs')
            refresh[ticker]=cik
        else:raise ValueError('Explicit boolean observation tier required')
    queue=issuer_map['latest_sec_refresh_candidate_tickers']
    if len(refresh)!=92 or len(fresh)!=9 or len(set(refresh.values()))!=91 or type(queue) is not list or queue!=list(refresh):raise ValueError('Exact 92 ticker / 91 CIK refresh required')
    return refresh


def refresh_identity_rows(issuer_map,decoded_by_cik):
    """Decoded SEC response bytes only; caller must verify request/receipt lineage."""
    expected=expected_refresh(issuer_map)
    if set(decoded_by_cik)!=set(expected.values()):raise ValueError('Complete exact 91 response CIK set required')
    facts={cik:prior.parse_identity(raw,cik) for cik,raw in decoded_by_cik.items()}
    rows=[]
    for ticker,cik in expected.items():
        fact=facts[cik]
        positions=[i for i,t in enumerate(fact['reported_tickers']) if t==ticker]
        if len(positions)!=1 or fact['reported_exchanges'][positions[0]]!='Nasdaq':raise ValueError('Exact current same-position ticker/Nasdaq unavailable: '+ticker)
        rows.append(dict(ticker=ticker,current_reported_cik=cik,conditional_issuer_id='issuer:'+cik,reported_ticker_exchange_position=positions[0],reported_exchange='Nasdaq',current_reported_name=fact['reported_name'],
            matched_candidate=fact,current_issuer_ticker_exchange_observed=True,name_used_as_ticker_binding=False,historical_cusip_verified=False,historical_alias_join_allowed=False,provider_price_identity_bound=False,point_in_time_verified=False,promotion_allowed=False))
    return dict(schema='CURRENT92_REFRESHED_SEC_ISSUER_OBSERVATIONS_PURE_V1',rows=rows,candidate_facts=facts,ticker_count=92,queried_cik_count=91,
        inherited_current_nine_not_refetched=True,input_artifact_binding_verified=False,source_is_sec_submissions_http_verified=False,
        historical_cusip_verified=False,historical_alias_join_allowed=False,provider_price_identity_bound=False,point_in_time_verified=False,promotion_allowed=False)
