"""Independent saved metadata/reference oracle; no producer or raw decoding."""
import csv
from datetime import date
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/bulk_long_window_benchmark_requirements_20261003_v1'
SHA='95461ba7b298347d969fe65cb3b93aa5632fecfdf331f1ba7a42af6abdee1c47'
PUB='bf9290f263f92523d7bd2001d138321ef429705aa96ec494e665ec15dead8766'
TICKERS=['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']
OUTER=('http_performed','prices_reconstructed','raw_decoding_reperformed','old_audit_repeated','returns_computed','account_simulation_performed','fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted','benchmark_qualified','evaluation_executed','historical_identity_verified','historical_currency_verified','fx_equivalence_verified','nav_publication_verified','full_transitive_source_closure_reverified')
INNER=('source_bytes_authenticated','historical_identity_verified','provider_binding_verified','historical_currency_interval_verified','nav_publication_time_verified','fx_alignment_verified','historical_risk_interval_verified','point_in_time_verified','benchmark_qualified','evaluation_executed','prices_computed','returns_computed','account_executed','fx_computed','fit_performed','weights_reoptimized','weights_normalized','holdings_converted','promotion_allowed','execution_authorized','legal_training_input_admitted','future_independent_oos_recovered','same_cashflow_verified','execution_rules_equivalent','fee_equivalence_verified','complete_corporate_actions_verified')
def check(v,m):
 if not v:raise ValueError(m)
def encoded(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def exact(a,b,m):check(encoded(a)==encoded(b),m)
def blob(path,digest):
 raw=Path(path).read_bytes();check(sha(raw)==digest,'Source SHA '+str(path));return raw
def ref(r,pointer=None):return dict(r,**({} if pointer is None else {'json_pointer':pointer}))
def verify():
 d=json.loads(blob(BASE/'requirements.json',SHA));pub=json.loads(blob(BASE/'publication.json',PUB));started=json.loads((BASE/'started.json').read_bytes())
 check({p.name for p in BASE.iterdir()}=={'started.json','requirements.json','publication.json'},'Successful exact namespace')
 refs=d['input_references'];sources=d['source_hashes'];check(len(refs)==22 and len(sources)==24,'Source denominator')
 expected_sources={r['path']:r['sha256'] for r in refs.values()}
 expected_sources.update({str(ROOT/'backtest/ndx_long_window_benchmark_requirements_research.py'):'eef682a2570860dc6eaf42e4beb9b871c98d53b09eb1090a3fda3b78e0b7be49',str(ROOT/'scripts/ndx_bulk_long_window_benchmark_requirements_20261003.py'):'bc455d71a0c2f08d1c38d843d86862d4d19a7bdde752ff1f53db027cc136042b'})
 exact(sources,expected_sources,'Full direct source map');raw={p:blob(p,h) for p,h in sources.items()}
 exact(pub,dict(schema='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_PUBLICATION_V1',status='PUBLISHED_REQUIREMENTS_ONLY',requirements_reference=dict(path=str(BASE/'requirements.json'),sha256=SHA),source_hashes=sources,**dict.fromkeys(OUTER,False)),'Publication')
 exact(started,dict(source_hashes=sources,retry_allowed=False,**dict.fromkeys(OUTER,False)),'Started')
 docs={k:json.loads(raw[r['path']]) for k,r in refs.items() if k not in ('nav_csv','source_contract','currency_listing')}
 csvreader=csv.DictReader(io.StringIO(raw[refs['nav_csv']['path']].decode('utf-8-sig')))
 check(csvreader.fieldnames==['Date','UnitNav','AccumNav','DailyPct','Close'],'Original NAV columns');navcsv=list(csvreader)
 control=docs['control'];securities=control['definition']['securities'];check([r['ticker'] for r in securities]==TICKERS,'Original order')
 readback=docs['readback'];channels={r['ticker']:(i,r) for i,r in enumerate(readback['rows'])};check(len(channels)==102,'102 source records')
 ai,aapl=channels['AAPL'];calendar=[r['new_york_date'] for r in aapl['observation']['rows'] if r['new_york_date']<='2026-09-21' and r['excluded_receipt_day_or_later'] is False][-253:]
 check(len(calendar)==253 and calendar==sorted(set(calendar)) and calendar[0]=='2025-09-18' and calendar[-1]=='2026-09-21','Uncompressed reference dates')
 entries={r['ticker']:(i,r) for i,r in enumerate(docs['index']['entries'])};wiring={r['ticker']:(i,r) for i,r in enumerate(docs['wiring']['rows'])}
 exact(readback['index_path'],refs['index']['path'],'Index path');exact(readback['index_sha256'],refs['index']['sha256'],'Index hash')
 stocks={};requirements=[];missingdates=0;missingfields=0;saved_rows=0
 for i,security in enumerate(securities):
  ticker=security['ticker'];oi,ch=channels[ticker];obs=ch['observation'];receipt=docs['receipt_'+ticker];entry=entries[ticker][1];rr=refs['receipt_'+ticker];rawref=dict(path=receipt['raw_path'],sha256=receipt['raw_sha256'])
  check(receipt['ticker']==obs['ticker']==obs['raw_provider_meta']['symbol']==ticker,'Ticker linkage')
  check(ch['receipt_sha256']==entry['receipt_sha256']==rr['sha256'] and entry['receipt_path']==rr['path'],'Receipt linkage')
  check(readback['source_hashes'][rawref['path']]==rawref['sha256'],'Saved raw hash assertion only')
  observations=[]
  for j,row in enumerate(obs['rows']):
   day=row['new_york_date'];check(type(row['excluded_receipt_day_or_later']) is bool and row['excluded_receipt_day_or_later']==(day>=ch['receipt_new_york_day']),'Receipt exclusion')
   if day<='2026-09-21' and not row['excluded_receipt_day_or_later']:observations.append(dict(session=day,missing_fields=row['missing_fields'],source_json_pointer=f'/rows/{oi}/observation/rows/{j}'))
  check([r['session'] for r in observations]==sorted({r['session'] for r in observations}),'Original metadata order');saved_rows+=len(observations)
  identity=[];extras={}
  if ticker!='TSM':
   wi,wr=wiring[ticker];check(wr['coordinate']['security_id']==security['security_id'] and wr['coordinate']['issuer_id']==security['issuer_id'],'Original conditional coordinates')
   identity.append(ref(refs['wiring'],f'/rows/{wi}'));extras['complete_conditional_wiring_row']=wr
  if ticker in ('TSM','ASML'):
   role=ticker.lower();side=docs[role];publication=docs[role+'_publication']
   exact(publication['identity_reference'],refs[role],'Sidecar publication reference');exact(publication['source_hashes'],side['source_hashes'],'Sidecar source claims')
   check(publication['status']=='PUBLISHED_CONDITIONAL_SID_SIDECAR_ONLY' and side['security_id']==security['security_id'] and side['issuer_id']==security['issuer_id'],'Sidecar identity')
   check(side['point_in_time_verified'] is False and side['promotion_allowed'] is False,'Sidecar permissions')
   identity.append(refs[role]);extras.update(complete_identity_sidecar=side,sidecar_publication_reference=refs[role+'_publication'])
  stocks[ticker]=dict(security_id=security['security_id'],raw_reference=rawref,receipt_reference=rr,receipt_binding=dict(ticker=ticker,raw_reference=rawref),observation_reference=ref(refs['readback'],f'/rows/{oi}'),observation_rows=observations,identity_evidence=identity,risk_evidence=[ref(refs['control'],f'/definition/securities/{i}')],complete_original_control_security=security,original_receipt=receipt,original_capture_index_entry=entry,decoded_sha256=obs['decoded_sha256'],returned_events=obs['raw_returned_events'],quote_price_unit=obs['quote_price_unit'],volume_unit=obs['volume_unit'],observed_provider_currency=obs['raw_provider_meta'].get('currency'),provider_currency_historical_continuity_verified=False,control_only_overlay=ticker=='TSM',shares_or_prices_converted=False,**extras)
  by={row['session']:(j,row) for j,row in enumerate(observations)};needed=[]
  for day in calendar:
   found=by.get(day);needed.append(dict(session=day,observation_metadata_row_index=None if found is None else found[0],observation_reference=stocks[ticker]['observation_reference'],observation_present=found is not None,saved_missing_fields=None if found is None else found[1]['missing_fields'],raw_reference=rawref,receipt_reference=rr,nominal_open_close_projection_required=True,nominal_prices_verified=False))
  absent=[r['session'] for r in needed if not r['observation_present']];fields=[r['session'] for r in needed if r['saved_missing_fields']];missingdates+=len(absent);missingfields+=len(fields)
  requirements.append(dict(original_index=i,original_security=security,control_only=ticker=='TSM',tsm_not_added_to_candidate_pool=ticker=='TSM',all253_dates_retained=True,requirements=needed,missing_observation_dates=absent,saved_missing_field_dates=fields,missing_identity_evidence=not identity,missing_risk_evidence=False,identity_and_risk_window_extension_not_automatic=True,**dict.fromkeys(INNER,False)))
 snap=docs['nav_snapshot'];manifest=docs['nav_manifest'];cm=docs['currency_manifest']
 exact(snap['immutable_copies']['nav.csv'],refs['nav_csv'],'NAV copy');exact(snap['immutable_copies']['original_manifest.json'],refs['nav_manifest'],'NAV manifest copy')
 check(manifest['content_sha256']==refs['nav_csv']['sha256'] and manifest['row_count']==len(navcsv) and manifest['publication_time_known'] is False,'Full NAV metadata')
 exact(cm['source_reference'],refs['currency_listing'],'Currency listing reference')
 navrows=[dict(date=r['Date'],row_index=i,source_reference=refs['nav_csv']) for i,r in enumerate(navcsv)]
 dates=[r['date'] for r in navrows];check(dates==sorted(set(dates)),'NAV dates')
 mappings=[]
 for day in calendar:
  eligible=[r for r in navrows if r['date']<=day];match=eligible[-1] if eligible else None;navday=None if match is None else match['date']
  mappings.append(dict(session=day,status='NO_PRIOR_NAV_OBSERVATION' if match is None else 'SAVED_OBSERVATION_DATE_MAPPING_ONLY',nav_date=navday,mapped_row_reference=None if match is None else dict(refs['nav_csv'],row_index=match['row_index'],column='Close'),same_date=navday==day,lag_calendar_days=None if match is None else (date.fromisoformat(day)-date.fromisoformat(navday)).days,available_at=None,publication_time_known=False,future_observation_used=False))
 args=dict(reference_calendar=dict(ticker='AAPL',dates=calendar,source_reference=ref(refs['readback'],f'/rows/{ai}/observation/rows')),original_control=dict(source_reference=refs['control'],securities=securities,complete_original_definition=control['definition'],complete_original_manifest=control,new_execution_contract_frozen=False),stock_metadata=stocks,nav_metadata=dict(source_reference=refs['nav_csv'],manifest_reference=refs['nav_manifest'],snapshot_reference=refs['nav_snapshot'],rows=navrows,publication_time_known=False,selected_value_column='Close',selected_value_semantics='SAVED_UNIT_NAV_NOT_ACCUMULATED_NAV',complete_saved_manifest=manifest,complete_saved_snapshot=snap,current_currency_listing_reference=refs['currency_listing'],complete_currency_listing_manifest=cm,currency_manifest_reference=refs['currency_manifest']),fx_metadata=dict(bound=False,source_reference=None,scope='NO_BOUND_HISTORICAL_USD_CNY_SEQUENCE_IN_THIS_REQUIREMENTS_DOCUMENT_NOT_REPOSITORY_ABSENCE_CLAIM',rates_computed=False,conversion_performed=False))
 claims={}
 def claim(r):
  check(r['path'] not in claims or claims[r['path']]==r['sha256'],'Reference conflict');claims[r['path']]=r['sha256']
 claim(args['reference_calendar']['source_reference']);claim(refs['control'])
 for item in stocks.values():
  for k in ('raw_reference','receipt_reference','observation_reference'):claim(item[k])
  for r in item['identity_evidence']+item['risk_evidence']:claim(r)
 for k in ('nav_csv','nav_manifest','nav_snapshot'):claim(refs[k])
 same=sum(r['same_date'] for r in mappings)
 expected=dict(schema='LONG_WINDOW_BENCHMARK_REQUIREMENTS_V1',status='BENCHMARK_INPUT_REQUIREMENTS_ONLY_NOT_EVALUATED',historical_retrospective_only=True,reference_calendar=args['reference_calendar'],original_control_preserved=args['original_control'],stock_metadata_preserved=stocks,nav_metadata_preserved=args['nav_metadata'],fx_metadata_preserved=args['fx_metadata'],original_target_weight_sum_exact=str(sum(Fraction(str(r['target_weight'])) for r in securities)),original_control_order=TICKERS,stock_requirements=requirements,stock_denominator=8,stock_date_requirement_count=2024,nav_date_requirement_count=253,nav_date_mappings=mappings,nav_same_date_count=same,nav_missing_same_date_sessions=[r['session'] for r in mappings if not r['same_date']],nav_without_prior_observation_sessions=[r['session'] for r in mappings if r['mapped_row_reference'] is None],training_return_end_dates=calendar[1:127],training_freeze_close_date=calendar[126],evaluation_initial_close_date=calendar[126],evaluation_return_end_dates=calendar[127:],nav_alignment='BACKWARD_OBSERVATION_DATE_ONLY_NOT_PUBLICATION_OR_TRADE_AVAILABILITY',benchmark_objective_semantics='ORIGINAL_COMPONENTWISE_ABSOLUTE_DISTANCE_CONTRACT_NOT_REPLACED_BY_ONE_SIDED_GATE',outstanding_contracts=['NEW_WINDOW_NOMINAL_OHLC_PROJECTION_AND_INDEPENDENT_ARITHMETIC','HISTORICAL_IDENTITY_RISK_AND_ACTION_SCOPE','NAV_PUBLICATION_AND_SUBSCRIPTION_TIMING','HISTORICAL_CURRENCY_AND_FX_DIRECTION_TIMESTAMP_AVAILABILITY','EXPLICIT_INITIAL_CAPITAL_CASHFLOWS_EXECUTION_FEES_DIVIDENDS'],direct_reference_hash_claims=claims,direct_claims_are_not_full_transitive_source_closure=True,**dict.fromkeys(INNER,False))
 expected['content_sha256']=sha(encoded(expected))
 exact(d,dict(schema='BULK_LONG_WINDOW_BENCHMARK_REQUIREMENTS_DOCUMENT_V1',requirements=expected,input_references=refs,source_hashes=sources,raw_price_responses_reopened=False,**dict.fromkeys(OUTER,False)),'Complete independent output reconstruction')
 return dict(status='PASS',requirements_sha256=SHA,publication_sha256=PUB,reader_sha256=sha(Path(__file__).read_bytes()),direct_sources=len(sources),original_control_order=TICKERS,original_weight_sum_exact=expected['original_target_weight_sum_exact'],saved_stock_metadata_rows=saved_rows,stock_date_checks=2024,missing_stock_dates=missingdates,missing_stock_field_dates=missingfields,original_nav_rows=len(navrows),nav_date_mappings=253,nav_same_date_count=same,nav_non_same_date_count=253-same,nav_without_prior=len(expected['nav_without_prior_observation_sessions']),nav_non_same_date_rows=[r for r in mappings if not r['same_date']],training_freeze=calendar[126],first_evaluation_return_end=calendar[127],training_return_count=126,evaluation_return_count=126,fx_bound=False,raw_decoding_performed=False,old_audit_repeated=False,account_executed=False,benchmark_qualified=False,point_in_time_verified=False)
if __name__=='__main__':
 result=verify();out=ROOT/'DYNAMIC_BULK_LONG_WINDOW_BENCHMARK_INDEPENDENT_READBACK_20261003.json'
 with out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
 print(json.dumps({k:v for k,v in result.items() if k!='nav_non_same_date_rows'},indent=2))
