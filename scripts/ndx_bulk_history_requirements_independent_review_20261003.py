"""Independent saved long-history metadata requirements audit. No production imports or raw IO."""
from collections import Counter
from datetime import date
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];DIRECTORY=ROOT/'data/cache/research/bulk_history_requirements_20261003_v1'
SHA='f3a317fd00800fe025003479358a6798cd893d4305511bcb1c39eb73ae94e2f5';PUB='171f4218d2ec3997b53d21d9e0e4c6081425ae963f79e7b7d0b3c5fa2ea5d13d'
PINS={
 'panel':('data/cache/research/bulk_conditional_panel_20261003_v1/panel.json','f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71'),
 'panel_publication':('data/cache/research/bulk_conditional_panel_20261003_v1/publication.json','895b1d0f71fb3f4b1175845c3390f3d286c672519fa4aa2c0a13bb930f6a2a9d'),
 'readback':('data/cache/research/new_cutoff_raw_readback_20260923_v1/completed102.json','7c03247919319c8e1a1a12be2fd8ccdba59aec20e0d9ee6634e69cc85fd0d53b'),
 'bridge':('data/cache/research/new_cutoff_event_policy_20260923_v1/bridge.json','d2f7824197cb30c119eb8297d6dda784e33ff2589010e36f63d4e9850267d7bd'),
 'panel_audit_report':('DYNAMIC_BULK_CONDITIONAL_PANEL_INDEPENDENT_READBACK_20261003.md','8a432b70dfc3393850242873b700eb54097bec9981c8f488cc88bd578295c879'),
 'panel_audit_reader':('scripts/ndx_bulk_conditional_panel_independent_review_20261003.py','5a3d35ba39e6a719dfafaa3e4e348f065c5cd297c403a08e087c78f02c5c1b0b')}
CODES={'scripts/ndx_bulk_history_requirements_20261003.py':'f2f838568da833353b01c129a0199f3de01b07428a290c7288ec2e320f97f7ab','backtest/ndx_bulk_history_requirements_research.py':'fa4d19ed2cdae45615023f1921b6ff80be74cc6c61ee3e8f261e4fa1b4336a71'}
SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
OUTER_FALSE=('http_performed','raw_decoding_reperformed','raw_quote_numerics_reaudited','old_audit_repeated','prices_reconstructed','returns_computed','fit_performed','execution_authorized','promotion_allowed','point_in_time_verified','legal_training_input_admitted','identity_interval_extended','complete_corporate_actions_verified','volume_unit_verified','provider_binding_verified','exchange_calendar_certified','future_oos_evaluation_performed','full_transitive_source_closure_reverified','formal_input_ready')
INNER_FALSE=('source_bytes_authenticated','reference_calendar_exchange_certified','prices_computed','returns_computed','fit_performed','saved_final_cutoff_weights_reused_for_earlier_freeze','identity_interval_verified','risk_interval_verified','complete_corporate_actions_verified','provider_binding_verified','volume_unit_verified','point_in_time_verified','timely_availability_verified','legal_training_input_admitted','historical_six_input_training_ready','formal_dual_benchmark_ready','promotion_allowed','execution_authorized','future_independent_oos_recovered','benchmark_qualified','evaluation_executed')
WINDOW={'first':'2026-03-20','last':'2026-09-21'}
CONTRACT={'decision_cutoff':'2026-09-21','fit_return_rows':126,'evaluation_return_rows':126,'rolling_step_rows':21,'price_window_lengths':[253,505]}
def check(v,message):
 if not v:raise ValueError(message)
def encode(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(encode(v)).hexdigest()
def exact(a,b,message):check(encode(a)==encode(b),message)
def blob(ref):
 raw=Path(ref['path']).read_bytes();check(hashlib.sha256(raw).hexdigest()==ref['sha256'],'SHA '+ref['path']);return raw
def read(ref):return json.loads(blob(ref))
def pairs(days):return [{'previous_session':days[i-1],'session':days[i]} for i in range(1,len(days))]
def window_oracle(calendar,start,ordinal):
 training=[calendar[start+j] for j in range(127)];evaluation=[calendar[start+126+j] for j in range(127)]
 return dict(window_index=ordinal,start_price_index=start,required_price_dates=training+evaluation[1:],training_price_dates=training,training_return_end_dates=training[1:],training_freeze_close_date=training[-1],evaluation_initial_close_date=evaluation[0],evaluation_price_dates=evaluation,evaluation_return_end_dates=evaluation[1:],training_return_predecessors=pairs(training),evaluation_return_predecessors=pairs(evaluation),fit_return_count=126,evaluation_return_count=126,final_cutoff_fitted_targets_may_be_reused=False,historical_retrospective_only=True)
def requirement_oracle(metadata,w):
 lookup={r['session']:r for r in metadata['observation_rows']};needed=w['required_price_dates'];floor=metadata['event_policy_bridge']['regular_floor'];absent=[d for d in needed if d not in lookup]
 field_gaps=[{'session':d,'missing_fields':lookup[d]['missing_fields']} for d in needed if d in lookup and lookup[d]['missing_fields']]
 floor_gaps=[d for d in needed if floor is not None and d<floor];identity_gaps=[d for d in needed if d<WINDOW['first'] or d>WINDOW['last']]
 badclose=set(absent)|{r['session'] for r in field_gaps if 'close' in r['missing_fields']};affected={}
 for role in ('training','evaluation'):
  edges=pairs(w[role+'_price_dates'])
  affected[role+'_return_pairs_with_missing_close']=[edge for edge in edges if badclose.intersection(edge.values())]
  affected[role+'_return_pairs_crossing_or_before_partition']=[edge for edge in edges if floor is not None and min(edge.values())<floor]
 return dict(window_index=w['window_index'],required_price_date_count=len(needed),missing_price_dates=absent,saved_missing_field_rows=field_gaps,regular_floor=floor,forbidden_pre_partition_price_dates=floor_gaps,identity_assumption_uncovered_price_dates=identity_gaps,risk_assumption_extension_required=bool(identity_gaps),identity_assumption_extension_required=bool(identity_gaps),saved_date_and_field_metadata_complete=not absent and not field_gaps,saved_close_metadata_complete=not badclose,partition_scope_complete=not floor_gaps,status='REQUIREMENT_GAPS_REMAIN' if absent or field_gaps or floor_gaps or identity_gaps else 'METADATA_PRESENT_SEMANTICS_STILL_UNVERIFIED',action_policy_revalidation_for_window_required=True,dividend_and_cashflow_contract_required=True,same_window_incumbent_and_nav_bindings_required=True,historical_retrospective_only=True,**affected,**dict.fromkeys(INNER_FALSE,False))
def verify():
 ref={'path':str(DIRECTORY/'requirements.json'),'sha256':SHA};document=read(ref);publication=read({'path':str(DIRECTORY/'publication.json'),'sha256':PUB});started=json.loads((DIRECTORY/'started.json').read_bytes())
 refs={k:{'path':str(ROOT/p),'sha256':h} for k,(p,h) in PINS.items()};sources={r['path']:r['sha256'] for r in refs.values()};sources.update({str(ROOT/p):h for p,h in CODES.items()});exact(document['source_hashes'],sources,'Exact8 sources')
 docs={}
 for role,r in refs.items():
  raw=blob(r)
  if role not in ('panel_audit_report','panel_audit_reader'):docs[role]=json.loads(raw)
 for path,sha in CODES.items():blob({'path':str(ROOT/path),'sha256':sha})
 check({p.name for p in DIRECTORY.iterdir()}=={'started.json','requirements.json','publication.json'},'Namespace success')
 exact(publication,dict(schema='BULK_HISTORY_REQUIREMENTS_PUBLICATION_V1',status='PUBLISHED_REQUIREMENTS_ONLY',requirements_reference=ref,source_hashes=sources,**dict.fromkeys(OUTER_FALSE,False)),'Publication envelope')
 exact(started,dict(source_hashes=sources,retry_allowed=False,**dict.fromkeys(OUTER_FALSE,False)),'Started envelope')
 pdoc=docs['panel'];panel=pdoc['panel'];readback=docs['readback'];bridge=docs['bridge'];receipt=docs['panel_publication']
 check(receipt['panel_reference']==refs['panel'] and receipt['status']=='PUBLISHED_CONDITIONAL_PANEL_ONLY','Panel publication');exact(receipt['source_hashes'],pdoc['source_hashes'],'Panel publication sources')
 universe=[dict(zip(panel['universe']['columns'],r)) for r in panel['universe']['data']];gaps=panel['observed_provenance_and_missing'];gap_by={r['ticker']:r for r in gaps};channels={r['ticker']:(i,r) for i,r in enumerate(readback['rows'])};policies={r['ticker']:(i,r) for i,r in enumerate(bridge['rows'])}
 check(len(universe)==len({r['security_id'] for r in universe})==len({r['ticker'] for r in universe})==77 and len({r['issuer_id'] for r in universe})==76,'77/76 coordinates');check(len(gaps)==len(gap_by)==101 and len(channels)==102 and readback['queue_count']==104,'Full denominators')
 observations={};original_counts={};excluded_count=0;split_channels=0
 for security in universe:
  ticker=security['ticker'];ci,channel=channels[ticker];bi,policy=policies[ticker];o=channel['observation'];gap=gap_by[ticker]
  check(channel['http_status']==200 and channel['readback_status']=='RAW_CHANNEL_READBACK_ONLY' and o['ticker']==o['raw_provider_meta']['symbol']==ticker,'Saved channel metadata')
  check(gap['included_in_conditional_panel'] is True and gap['coordinate_assumption']['security_id']==security['security_id'] and gap['coordinate_assumption']['issuer_id']==security['issuer_id'] and gap['risk_assumption']['risk_chain']==security['risk_chain'],'Original coordinate/risk linkage');exact(gap['coordinate_assumption']['assumed_window'],WINDOW,'Original identity interval')
  rawref=policy['new_raw_reference'];receiptreference=policy['new_receipt_reference'];check(channel['receipt_sha256']==receiptreference['sha256'] and policy['new_decoded_sha256']==o['decoded_sha256'],'Receipt/decoded hashes')
  for reference in (rawref,receiptreference):check(readback['source_hashes'][reference['path']]==reference['sha256']==bridge['source_hashes'][reference['path']],'Saved raw/receipt cross-source assertions')
  exact(policy['new_returned_splits'],o['raw_returned_events'].get('splits',{}),'All returned split payload');split_channels+=bool(policy['new_returned_splits'])
  rows=[];excluded=[];all_dates=[]
  for ri,row in enumerate(o['rows']):
   d=row['new_york_date'];check(date.fromisoformat(d).isoformat()==d,'Canonical observation date');all_dates.append(d)
   check(type(row['excluded_receipt_day_or_later']) is bool and row['excluded_receipt_day_or_later']==(d>=channel['receipt_new_york_day']),'Receipt exclusion')
   value=dict(session=d,missing_fields=row['missing_fields'],source_json_pointer=f'/rows/{ci}/observation/rows/{ri}')
   (excluded if d>CONTRACT['decision_cutoff'] or d>=channel['receipt_new_york_day'] else rows).append(value)
  check(all_dates==sorted(set(all_dates)),'Complete unsorted/duplicate-free source dates');original_counts[ticker]=len(all_dates);excluded_count+=len(excluded)
  observations[ticker]=dict(observation_rows=rows,raw_reference=rawref,receipt_reference=receiptreference,decoded_sha256=o['decoded_sha256'],bridge_reference=dict(refs['bridge'],json_pointer=f'/rows/{bi}'),event_policy_bridge=policy['event_policy_bridge'],identity_assumed_window=WINDOW,complete_bridge_row=policy,complete_coordinate_assumption=gap['coordinate_assumption'],complete_risk_assumption=gap['risk_assumption'],returned_events=o['raw_returned_events'],original_observation_reference=dict(refs['readback'],json_pointer=f'/rows/{ci}'),excluded_after_cutoff_or_receipt_day=excluded,receipt_new_york_day=channel['receipt_new_york_day'],quote_price_unit=o['quote_price_unit'],volume_unit=o['volume_unit'],all_original_observation_row_count=len(all_dates),historical_raw_source_bytes_reverified=False,raw_quote_values_projected=False)
 calendar=[r['session'] for r in observations['AAPL']['observation_rows']];check(calendar[-1]=='2026-09-21' and all(date.fromisoformat(d).weekday()<5 for d in calendar),'Provider reference dates');reference_calendar=dict(ticker='AAPL',dates=calendar,source_reference=dict(refs['readback'],json_pointer=f"/rows/{channels['AAPL'][0]}/observation/rows"))
 evidence=dict(input_references=refs,complete_panel_sidecars={k:pdoc[k] for k in SIDECARS},sidecar_references={k:dict(refs['panel'],json_pointer='/'+k) for k in SIDECARS},observed_security_denominator=101,typed_security_count=77,typed_issuer_count=76,raw_attempted_channel_count=102,capture_queue_count=104,reference_calendar_basis='SEALED_AAPL_PROVIDER_OBSERVATIONS_NOT_EXCHANGE_CALENDAR',original_identity_assumed_window=WINDOW,source_assertions_reused_without_transitive_raw_reaudit=True)
 exact(document['projection_evidence'],evidence,'All projection provenance/seven sidecars')
 scenarios=[];counts={};total_security_windows=0;pair_checks=0
 for length,expected_count in ((253,1),(505,13)):
  dates=calendar[-length:];check(len(dates)==length,'Complete proposed provider window');starts=[n*21 for n in range(expected_count)];windows=[window_oracle(dates,start,n) for n,start in enumerate(starts)]
  check(starts[-1]+252==length-1,'Exact last evaluation endpoint')
  rows=[];floors=Counter();missing_days=missing_fields=identity=0
  for security in universe:
   requirements=[]
   for w in windows:
    entry=requirement_oracle(observations[security['ticker']],w);requirements.append(entry);total_security_windows+=1;pair_checks+=252
    missing_days+=bool(entry['missing_price_dates']);missing_fields+=bool(entry['saved_missing_field_rows']);identity+=entry['identity_assumption_extension_required']
    if not entry['partition_scope_complete']:floors[security['ticker']]+=1
   rows.append(dict(coordinate=security,requirements=requirements,status='WINDOW_REQUIREMENTS_RECORDED',reference_price_date_deficit=0))
  scenarios.append(dict(price_window_length=length,expected_adjacent_return_count=length-1,reference_calendar_complete=True,required_reference_price_dates=dates,expected_rolling_window_count=expected_count,constructed_window_count=expected_count,rolling_step_return_rows=21,windows=windows,security_rows=rows,security_denominator=77,all_security_windows_retained=True,dates_intersected_or_compressed=False,desired_505_is_hard_admission_threshold=False,metadata_only=True,historical_retrospective_only=True,**dict.fromkeys(INNER_FALSE,False)))
  counts[str(length)]=dict(price_first=dates[0],price_last=dates[-1],windows=len(windows),security_windows=77*len(windows),missing_date_security_windows=missing_days,missing_field_security_windows=missing_fields,partition_blocked_windows_by_ticker=dict(floors),identity_extension_security_windows=identity)
 requirements=dict(schema='BULK_CONDITIONAL_HISTORY_REQUIREMENTS_V1',status='HISTORICAL_REQUIREMENTS_ONLY_NOT_TRAINING_ADMISSION',window_contract=CONTRACT,original_identity_assumed_window=WINDOW,universe=universe,observed_provenance_and_missing=gaps,reference_calendar=reference_calendar,ticker_observations_preserved=observations,scenarios=scenarios,security_denominator=77,issuer_denominator=76,observed_provenance_denominator=101,historical_retrospective_only=True,independent_future_oos=False,missing_timestamps_are_unknown_not_automatically_late=True,benchmark_objective_semantics='ORIGINAL_COMPONENTWISE_ABSOLUTE_DISTANCE_CONTRACT_NOT_REPLACED_BY_ONE_SIDED_GATE',benchmark_gaps=['NAV_AVAILABILITY_TIMESTAMPS','CURRENCY_AND_FX','SAME_CASHFLOW','EXECUTION_RULES','COMMON_OBSERVATION_CALENDAR'],source_metadata_are_caller_supplied_not_reauthenticated=True,next_required_contracts=['EXPLICIT_HISTORICAL_IDENTITY_AND_RISK_SCOPE','WINDOW_SPECIFIC_ACTION_AND_PRICE_UNITS','INDEPENDENT_LONG_WINDOW_ARITHMETIC_READBACK','SAME_WINDOW_INCUMBENT_NAV_FLOWS_FEES_AND_AVAILABILITY'],**dict.fromkeys(INNER_FALSE,False));requirements['content_sha256']=digest(requirements)
 exact(document,dict(schema='BULK_HISTORY_REQUIREMENTS_DOCUMENT_V1',requirements=requirements,projection_evidence=evidence,source_hashes=sources,**dict.fromkeys(OUTER_FALSE,False)),'Complete independent expected requirements document')
 return dict(status='PASS',requirements_sha256=SHA,publication_sha256=PUB,reader_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),direct_source_count=len(sources),security_count=77,issuer_count=76,provenance_count=101,sidecars=7,provider_calendar_dates=len(calendar),original_saved_metadata_row_count=sum(original_counts.values()),excluded_after_cutoff_or_receipt_rows=excluded_count,channels_with_returned_splits=split_channels,window_count=14,security_window_count=total_security_windows,independent_return_pair_checks=pair_checks,scenarios=counts,raw_decoding_or_old_audit_called=False,fit_performed=False,point_in_time_verified=False,formal_input_ready=False)
if __name__=='__main__':print(json.dumps(verify(),indent=2))
