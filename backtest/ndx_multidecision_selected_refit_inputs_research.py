"""Pure latest126 outer-refit preparation; later prior evidence is explicitly unresolved."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib,json,math,re
CUTOFFS=('2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31')
MODES=('STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX')
LANES=('RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE')
SPECS=('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor')
PARAMETERS=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
FITTER_CODES={'ndx_dynamic_cutoff_refit_v2_research.py':'4bb005b7f88a1e806fc25dede38b0f15c42187c2aa6024d3eb32155d64abab75','ndx_dynamic_cutoff_refit_research.py':'33e0f20d1541bc42344f84dd3eae4bc6d61bfaf703ecef07c5e78a5dd547e0bd','ndx_joint_weight_evaluation_v3.py':'20b81a22626dfdf17fa465cc6cc63f3a16a9b6665b6567cf8d7467c727c2f2bb'}
FLAGS=dict.fromkeys(('source_bytes_authenticated','complete_fitter_source_closure_authenticated','point_in_time_verified','complete_ndx_universe_verified','fit_performed','score_computed','selector_called','dispatch_authorized','execution_authorized','account_executed','promotion_allowed','prior_attempt_inventory_authenticated','scoring_window_weights_reused'),False)

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(enc(v)).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def ref(r):require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'] and r['path']==r['path'].strip() and type(r['sha256']) is str and re.fullmatch('[a-f0-9]{64}',r['sha256']) is not None,'Exact source reference')
def merge(s,r):
    ref(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def dates(v,n):
    require(type(v) is list and len(v)==n and v==sorted(set(v)),'Complete ordered dates')
    for x in v:require(type(x) is str and date.fromisoformat(x).isoformat()==x and date.fromisoformat(x).weekday()<5,'Canonical weekday')
def count(d,k,n):require(type(d[k]) is int and d[k]==n,'Exact count '+k)
def flags(d,ks):
    for k in ks:require(d[k] is False,'No authority '+k)

def validate_sources(selection,history,fitter):
    sources={}
    for package in (selection,history):
        for key in ('reference','readback_reference','reader_reference'):merge(sources,package[key])
        audit=package['readback'];require(audit['status']=='PASS' and audit['reader_sha256']==package['reader_reference']['sha256'],'Explicit independently read source')
        for key in ('reference','reader_reference'):
            r=package[key];require(audit['source_hashes'][r['path']]==r['sha256'],'Audit source role bound')
        for p,h in audit['source_hashes'].items():merge(sources,dict(path=p,sha256=h))
    saved=selection['document'];audit=selection['readback']
    require(saved['schema']=='FULL_NDX_MULTIDECISION_FOUR_LANE_SELECTION_V1' and audit['schema']=='REGISTERED_SCORING_SELECTION_INDEPENDENT_READBACK_V1','Actual selection/reader schemas')
    exact(audit['raw_selection_reference'],selection['reference'],'Audited original selection raw reference')
    require(saved['content_sha256']==digest({k:v for k,v in saved.items() if k!='content_sha256'}),'Selection full digest')
    require(audit['ranking_inspection']['status']=='PASS' and audit['ranking_inspection']['coordinate_count']==12 and type(audit['ranking_inspection']['coordinate_count']) is int,'Full ranked coordinates')
    flags(saved,('source_bytes_authenticated','point_in_time_verified','complete_ndx_universe_verified','full_universe_search_verified','saved_weights_are_execution_targets','prior_resolved','fit_performed','account_executed','promotion_allowed','execution_authorized'))
    index=history['document'];ha=history['readback']
    require(index['schema']=='MULTIDECISION_SCORING_HISTORY_AGGREGATE_V1' and ha['schema']=='MULTIDECISION_SCORING_HISTORY_INDEPENDENT_READBACK_V2','Actual history source roles')
    exact(ha['index_reference'],history['reference'],'History audit index binding')
    for d in (index,ha):
        for k,n in (('security_count',77),('issuer_count',76),('observed_security_count',101),('preserved_sidecar_count',7)):count(d,k,n)
    require(len(index['rows'])==len(ha['rows'])==77 and len(index['original_provenance_and_missing'])==101 and len(index['preserved_evidence_sidecars'])==7,'Complete original inventory/evidence')
    for i,(row,a) in enumerate(zip(index['rows'],ha['rows'])):
        count(row,'index',i);count(a,'index',i);exact(row['coordinate'],a['coordinate'],'History audit full coordinate');exact(row['channel_reference'],a['channel_reference'],'History audit exact channel');require(a['inspection']['status']=='PASS','Original channel numeric audit')
        merge(sources,row['channel_reference']);require(ha['source_hashes'][row['channel_reference']['path']]==row['channel_reference']['sha256'],'Audited channel bytes declaration')
    require(fitter['schema']=='OUTER_CUTOFF_REFIT_SOURCE_CONTRACT_V1' and fitter['entrypoint_function']=='refit_dynamic_cutoff_weights','Explicit new outer role, not inner rolling')
    exact(fitter['parameters'],PARAMETERS,'Frozen outer refit eight parameters')
    flags(fitter,('source_bytes_authenticated','fit_performed','execution_authorized','promotion_allowed'));merge(sources,fitter['reference'])
    sf=fitter['source_hashes'];require(type(sf) is dict and sf and fitter['fitter_source_fingerprint']==digest(sf),'Whole supplied source fingerprint')
    for p,h in sf.items():merge(sources,dict(path=p,sha256=h))
    for name,h in FITTER_CODES.items():
        matches=[p for p in sf if p.replace('\\','/').split('/')[-1]==name];require(len(matches)==1 and sf[matches[0]]==h,'Frozen outer fitter code role '+name)
    e=fitter['entrypoint_reference'];ref(e);require(e['path'] in sf and sf[e['path']]==e['sha256']==FITTER_CODES['ndx_dynamic_cutoff_refit_v2_research.py'] and e['path'].replace('\\','/').endswith('/ndx_dynamic_cutoff_refit_v2_research.py'),'Exact outer entrypoint')
    return sources


def prepare_selected_cutoff_refit_inputs(*,selection,history,channel_bindings,fitter_contract,previous_refit_evidence):
    require(previous_refit_evidence is None,'Prior evidence schema not implemented: no caller weights or invented PASS receipt accepted')
    sources=validate_sources(selection,history,fitter_contract);saved=selection['document'];index=history['document'];rows=saved['rows'];require(len(rows)==12 and saved['global_input_errors']==[],'All six decisions/two FX')
    universe=[r['coordinate'] for r in index['rows']];exact(saved['registration_preserved']['universe'],universe,'Original complete selected universe')
    by={r['security_id']:r for r in universe};require(len(by)==77 and len({r['issuer_id'] for r in universe})==76,'Unique full77/76')
    require(type(channel_bindings) is list,'Explicit supplied channel bindings');channels={}
    indexby={r['coordinate']['security_id']:r for r in index['rows']}
    for b in channel_bindings:
        sid=b['coordinate']['security_id'];require(sid in by and sid not in channels,'Unique known supplied channel');exact(b['coordinate'],by[sid],'Full original channel coordinate');exact(b['reference'],indexby[sid]['channel_reference'],'Original source row reference')
        channel=b['channel'];require(channel['schema']=='MULTIDECISION_SCORING_HISTORY_CHANNEL_V1' and channel['ticker']==by[sid]['ticker'],'Original candidate channel, not control overlay')
        flags(channel,('point_in_time_verified','fit_performed','score_computed','missing_or_blocked_slots_dropped','unequal_window_pooling_allowed'));require(len(channel['decisions'])==6,'All original source decisions');channels[sid]=b
    prepared=[]
    for ci,row in enumerate(rows):
        j,mi=divmod(ci,2);coordinate=row['coordinate_preserved'];cutoff=CUTOFFS[j];mode=MODES[mi]
        require(coordinate['cutoff']==coordinate['decision_date']==cutoff and coordinate['fx_mode']==mode,'Original registered cutoff/mode')
        require(row['input_errors']==[] and len(row['choices'])==4 and [c['lane'] for c in row['choices']]==list(LANES),'Complete four lanes without input errors')
        price_dates=coordinate['scoring_price_dates'];dates(price_dates,505);require(price_dates[-1]==cutoff,'Complete cutoff505')
        for li,choice in enumerate(row['choices']):
            lane=LANES[li];choice_ref=dict(selection['reference'],json_pointer=f'/result/rows/{ci}/choices/{li}')
            item=dict(cutoff=cutoff,decision_index=j,fx_mode=mode,lane=lane,choice_reference=choice_ref,original_choice_preserved=deepcopy(choice),selection_status=choice['status'],selected=None,fit_matrix=None,fit_data_sha256=None,parameters=deepcopy(PARAMETERS),source_slot_evidence=[],missing_latest_return_slots=[],requested_previous_target_weights=None,prior_value_resolved=False,prior_resolution='NOT_APPLICABLE',prior_reference=None,numerical_identity=None,numerical_task_id=None,location_identity=None,location_id=None,**FLAGS)
            if choice['status'] in ('SOURCE_BLOCKED','NO_ELIGIBLE_CANDIDATE','NO_REGISTERED_CANDIDATES'):
                require(choice['selected'] is None,'No fabricated no-candidate target');require(coordinate['source_status']==('SOURCE_BLOCKED' if choice['status']=='SOURCE_BLOCKED' else 'READY_FOR_SCORING'),'Original source block/no-candidate distinction');item['status']=choice['status'];prepared.append(item);continue
            require(choice['status']=='SELECTED_REQUIRES_NEW_CUTOFF_REFIT' and type(choice['selected']) is dict,'Only independently selected target composition')
            chosen=choice['selected'];rec=chosen['record_preserved'];task=rec['task'];rid=chosen['record_index']
            require(type(rid) is int and 0<=rid<len(saved['records_preserved']),'Original selected record index');exact(rec,saved['records_preserved'][rid],'Entire selected scoring evidence');require(rec['status']=='EVALUATED' and chosen['job_id']==task['job_id'] and task['cutoff']==cutoff and task['fx_mode']==mode,'Selected source coordinate')
            sids=task['security_ids'];require(type(sids) is list and sids==sorted(set(sids)) and sids and all(s in by for s in sids),'Old fitter sorted SID order')
            require(len({by[s]['issuer_id'] for s in sids})==len(sids) and len({by[s]['ticker'] for s in sids})==len(sids),'One SID per issuer/ticker');count(task,'holding_count',len(sids));require(task['weight_spec'] in SPECS,'Original chosen weight specification')
            require(coordinate['source_status']=='READY_FOR_SCORING' and all(rec['eligibility'][k] is True for k in ('fractional_risk_passed','liquidity_passed','conditional_member_scope_passed')),'Original chosen research gates')
            selected={s:{k:by[s][k] for k in ('ticker','issuer_id','risk_chain')} for s in sids};columns=[]
            for sid in sids:
                require(sid in channels,'Selected saved channel unavailable');binding=channels[sid];ch=binding['channel'];d=ch['decisions'][j]
                require(d['cutoff']==cutoff,'Channel decision clock');exact(d['required_price_dates'],price_dates,'Original505 dates same selected registration')
                off=d['price_index_start'];require(type(off) is int and off>=0 and type(d['price_index_stop']) is int and d['price_index_stop']==off+505,'Original full source offsets');require(len(ch['return_rows'])>=off+504,'Complete source return slots')
                begin=off+378;end=off+504;values=[];exactvalues=[]
                for n,r in enumerate(ch['return_rows'][begin:end]):
                    require(r['previous_session']==price_dates[378+n] and r['session']==price_dates[379+n] and r['dividends_included'] is False,'Latest126 adjacent causal source dates')
                    if r['status']!='CONDITIONAL_NUMERIC_SLOT':
                        require(r['split_only_return_float'] is None and r['split_only_return_exact'] is None,'Unknown slots not invented');values.append(None);exactvalues.append(None);item['missing_latest_return_slots'].append(dict(security_id=sid,return_index=begin+n,session=r['session'],original_slot=deepcopy(r)));continue
                    value=r['split_only_return_float'];raw=r['split_only_return_exact'];require(type(value) in (int,float) and math.isfinite(value) and value>-1 and type(raw) is str and Fraction(raw)>-1 and float(Fraction(raw)).hex()==float(value).hex(),'Saved exact-to-binary64 return correspondence')
                    values.append(float(value));exactvalues.append(raw)
                require(len(values)==126,'No slot compression');columns.append(values)
                item['source_slot_evidence'].append(dict(security_id=sid,channel_reference=deepcopy(binding['reference']),decision_reference=dict(binding['reference'],json_pointer=f'/decisions/{j}'),return_index_start=begin,return_index_stop=end,exact_return_values=exactvalues,original_decision_metadata=deepcopy(d)))
            matrix=dict(dates=deepcopy(price_dates[-126:]),tickers=[selected[s]['ticker'] for s in sids],returns=[list(r) for r in zip(*columns)])
            item.update(selected=selected,prior_value_resolved=j==0,weight_spec=task['weight_spec'],selected_scoring_job_id=task['job_id'],fit_matrix=matrix,fit_predecessor_close=price_dates[-127],fit_data_sha256=digest(matrix),prior_resolution='INITIAL_EXPLICIT_NONE' if j==0 else 'UNRESOLVED_PREVIOUS_ADJACENT_AUDITED_REFIT',prior_requirement=None if j==0 else dict(previous_cutoff=CUTOFFS[j-1],fx_mode=mode,lane=lane,required_evidence='COMPLETE_NEW_OUTER_REQUEST_RAW_POSTCHECK_INDEPENDENT_AUDIT',caller_weights_accepted=False),initial_effective_anchor_strength=0.0 if j==0 else None)
            if item['missing_latest_return_slots']:item['status']='BLOCKED_LATEST126_SOURCE_SLOTS'
            elif j>0:item['status']='INPUTS_PREPARED_PRIOR_UNRESOLVED'
            else:
                identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff=cutoff,holding_count=len(sids),selected=deepcopy(selected),weight_spec=task['weight_spec'],parameters=deepcopy(PARAMETERS),requested_previous_target_weights=None,fit_data_sha256=item['fit_data_sha256'],fitter_source_fingerprint=fitter_contract['fitter_source_fingerprint'])
                location=dict(schema='MULTIDECISION_OUTER_REFIT_LOCATION_IDENTITY_V1',cutoff=cutoff,fx_mode=mode,lane=lane,selection_reference=choice_ref,selected_scoring_job_id=task['job_id'],history_reference=history['reference'])
                item.update(status='INITIAL_REFIT_INPUTS_MATERIALIZED_NOT_DISPATCHED',numerical_identity=identity,numerical_task_id=digest(identity),location_identity=location,location_id=digest(location))
            prepared.append(item)
    require(len(prepared)==48,'Whole48 coordinate domain')
    counts={}
    for r in prepared:counts[r['status']]=counts.get(r['status'],0)+1
    result=dict(schema='MULTIDECISION_SELECTED_LATEST126_REFIT_INPUTS_V1',rows=prepared,coordinate_count=48,status_counts=counts,full_universe_preserved=deepcopy(universe),original_provenance_and_missing=deepcopy(index['original_provenance_and_missing']),preserved_evidence_sidecars=deepcopy(index['preserved_evidence_sidecars']),selection_reference=deepcopy(selection['reference']),selection_readback_reference=deepcopy(selection['readback_reference']),history_reference=deepcopy(history['reference']),history_readback_reference=deepcopy(history['readback_reference']),fitter_contract_preserved=deepcopy(fitter_contract),source_hashes=sources,prior_evidence_interface='NO_EXTERNAL_PRIOR_RECEIPT_ACCEPTED_IN_THIS_VERSION',later_matrix_prepared_without_final_task_identity=True,numerical_identity_generated_only_for_initial_complete_inputs=True,**FLAGS)
    result['content_sha256']=digest(result);return deepcopy(result)
