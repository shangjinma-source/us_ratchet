"""Independent saved classification projection audit. No producer/core calls."""
import argparse,hashlib,json,os
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/saved_classification_coverage_20261003_v1'
OUTPUT=ROOT/'data/cache/research/saved_classification_coverage_independent_readback_20261003_v1'
COVERAGE_SHA='a9c26a95e01846cb20993d435ee2a7f690d111729f825d7551bde1ed404f555f'
PUBLICATION_SHA='ac87e53e42ed5c018ad64f26fc44a743deef0c25b37dd1f80c2a1e98dd897607'
PRODUCER=ROOT/'scripts/ndx_saved_classification_coverage_20261003.py'
PRODUCER_SHA='1a2ae65457e4f03f4e6e94bac66ecbb7b0ea04d033d6b07f5de0fe3486c5459d'
BOUND={'wiring': ('data/cache/research/bulk_conditional_wiring_20261003_v1/wiring.json', 'e4f4328043254667ff334ebc7aaf0fe530d451339f5b9d4b1ba0a20c37b9b8a5'), 'wiring_publication': ('data/cache/research/bulk_conditional_wiring_20261003_v1/publication.json', '7f9ba6d89271fded96727e4dbfdd08ccc58ff249d352fddf5f97a8366f345e12'), 'wiring_review_report': ('DYNAMIC_BULK_CONDITIONAL_WIRING_INDEPENDENT_READBACK_20261003.md', '3600f8f179331c5cd864669a5f278f2c12fa36db39e1c836e9bae206efb494bc'), 'wiring_reader': ('scripts/ndx_bulk_conditional_wiring_independent_review_20261003.py', 'c5ed4f3468001292c13452ec64889ed25f3309032444b9014d4a23079267a901'), 'training_panel': ('data/cache/research/dated_training_panel_20261003_v1/panel.json', '895f31e30647e1422bcd2feab3025f8e9103c745f9d176549d59a069a30b9d96'), 'training_publication': ('data/cache/research/dated_training_panel_20261003_v1/publication.json', '2b64693fd54c1358429ca9df8ac5c9b685882d419a275a7b4384e878c5c1a2a5'), 'training_audit': ('DYNAMIC_DATED_TRAINING_PANEL_INDEPENDENT_READBACK_20261003.json', '38b5a61dbfae53264c8691e421d1bbb00140f567d437b5692543c9313a0d95bd'), 'training_reader': ('scripts/ndx_dated_training_panel_independent_review_20261003.py', '7a7cd393f3d02e11b96facbad3b259dee6337cb3f69bbc21dbc94556f4f66309'), 'core': ('backtest/ndx_saved_risk_classification_coverage_research.py', '116b6eaff2621216490ab77cdc96d0b7af6b5d38a70345e42197f7c61f79486e')}
FLAGS=('point_in_time_verified','promotion_allowed','execution_authorized','fit_performed','risk_reclassified','old_audits_reexecuted','future_independent_oos','full_transitive_source_closure_reverified','official_classification_conflict_audited')
PURE_FALSE=('point_in_time_verified','source_bytes_authenticated','formal_classification_verified','historical_pool_eligibility_verified','legal_training_input_admitted','execution_authorized','promotion_allowed','fit_performed','risk_reclassified','historical_identity_window_extended','future_independent_oos','classification_dates_inferred')
def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def ref(p,h):return dict(path=str(p),sha256=h)
def pointer(r,p):return dict(r,json_pointer=p)
def flags(d,keys):
    for k in keys:require(d[k] is False,'False evidence boundary '+k)
def integer(v,n):require(type(v) is int and v==n,'Exact nonboolean count')
def loads(b):
    def pairs(xs):
        d={}
        for k,v in xs:require(k not in d,'Duplicate key');d[k]=v
        return d
    def bad(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=bad)
def resolve(d,p):
    require(type(p) is str and p.startswith('/'),'Local absolute pointer')
    for token in p.split('/')[1:]:
        token=token.replace('~1','/').replace('~0','~');d=d[int(token)] if type(d) is list else d[token]
    return d

def inspect(coverage,wiring,training,refs):
    require(coverage['schema']=='SAVED_CONDITIONAL_CLASSIFICATION_COVERAGE_V1' and coverage['status']=='CONDITIONALLY_EVALUATED_SUPPLIED_EVIDENCE','Coverage schema/status')
    require(wiring['schema']=='BULK_CONDITIONAL_IDENTITY_RISK_WIRING_V1' and training['schema']=='DATED_CONDITIONAL_TRAINING_PANEL_DOCUMENT_V1','Saved source schemas')
    panel=training['panel'];require(panel['schema']=='DATED_CONDITIONAL_TRAINING_PANEL_V1','Inner training scope')
    for d in (wiring,training,panel):flags(d,('point_in_time_verified','legal_training_input_admitted','execution_authorized','fit_performed','promotion_allowed'))
    flags(coverage,PURE_FALSE);require(coverage['source_authentication_scope']=='CALLER_SUPPLIED_VALUES_ONLY_NO_SOURCE_AUTHENTICATION','Pure module not authentication')
    exact(coverage['input_references'],dict(wiring=pointer(refs['wiring'],''),training_panel=pointer(refs['training_panel'],'')),'Actual input source pointers')
    rows=wiring['rows'];gaps=panel['original_provenance_and_missing'];selected=panel['fit_payload']['selected_by_security']
    require(len(rows)==len(gaps)==len(coverage['rows'])==101 and type(selected) is dict,'Complete101 denominator')
    gap_by={g['ticker']:(i,g) for i,g in enumerate(gaps)};require(len(gap_by)==101,'Unique gap tickers')
    tickers=set();sids=set();issuers=set();labeled=set();labeled_issuers=set();selected_seen=set();labels=Counter();issuer_labels={}
    for i,(old,out) in enumerate(zip(rows,coverage['rows'])):
        ticker=old['ticker'];require(type(ticker) is str and ticker and ticker not in tickers and ticker in gap_by,'All original unique tickers');tickers.add(ticker)
        coordinate=old['coordinate'];label=old['risk_chain'];require(label is None or type(label) is str and bool(label.strip()),'Original label literal')
        sid=issuer=None
        if coordinate is not None:
            require(type(coordinate) is dict and coordinate['ticker']==ticker,'Coordinate ticker')
            sid=coordinate['security_id'];issuer=coordinate['issuer_id'];require(type(sid) is str and sid and sid not in sids and type(issuer) is str and issuer,'Unique SID/nonempty issuer');sids.add(sid);issuers.add(issuer)
        known=label is not None and label!='unclassified'
        if known:
            require(sid is not None,'Saved known label needs coordinate');labeled.add(sid);labeled_issuers.add(issuer);labels[label]+=1
            issuer_labels.setdefault(issuer,{}).setdefault(label,[]).append(sid)
        gi,gap=gap_by[ticker];chosen=selected.get(sid) if sid is not None else None
        require(type(gap['included_in_conditional_panel']) is bool and gap['included_in_conditional_panel'] is (chosen is not None) and type(gap['blocking_reasons']) is list,'Original inclusion versus exact selected map')
        if chosen is not None:
            exact(chosen,dict(ticker=ticker,issuer_id=issuer,risk_chain=label),'Training actual coordinate/classification');require(known,'Known selected label');selected_seen.add(sid)
        evidence={}
        for k,v in old.items():
            if k.endswith('_reference') and type(v) is dict and set(v)=={'json_pointer'}:
                p=v['json_pointer'];evidence[k]=dict(reference=pointer(refs['wiring'],p),saved_evidence=resolve(wiring,p))
        expected=dict(ticker=ticker,security_id=sid,issuer_id=issuer,saved_risk_chain=label,conditional_label_present=known,classification_status='SAVED_CONDITIONAL_LABEL' if known else 'UNKNOWN_SAVED_LABEL',formally_verified=False,original_wiring_row=old,wiring_row_reference=pointer(refs['wiring'],f'/rows/{i}'),local_evidence=evidence,training_selected=chosen is not None,training_selected_mapping=chosen,training_provenance=gap,training_provenance_reference=pointer(refs['training_panel'],f'/panel/original_provenance_and_missing/{gi}'),nonselection_evidence=None if chosen is not None else gap['blocking_reasons'],nonselection_reason_inferred=False)
        exact(out,expected,'Full original row, references and missing evidence')
    require(selected_seen==set(selected),'All selected77 identities consumed')
    training_issuers={r['issuer_id'] for r in selected.values()}
    counts=dict(observed_security_rows=101,coordinate_security_count=len(sids),coordinate_issuer_count=len(issuers),conditional_labeled_security_count=len(labeled),conditional_labeled_issuer_count=len(labeled_issuers),unknown_label_rows=101-len(labeled),training_selected_security_count=len(selected),training_selected_issuer_count=len(training_issuers),training_not_selected_rows=101-len(selected),formally_verified_rows=0)
    exact(coverage['counts'],counts,'Independent complete count partition')
    for k,n in dict(observed_member_count=101,candidate_security_count=len(sids),candidate_issuer_count=len(issuers)).items():integer(wiring[k],n)
    for k,n in dict(observed_security_count=101,security_count=len(selected),issuer_count=len(training_issuers)).items():integer(panel[k],n)
    # Fixed saved pool scope; conditional identity78 is not training77.
    for k,n in dict(coordinate_security_count=78,coordinate_issuer_count=77,conditional_labeled_security_count=78,conditional_labeled_issuer_count=77,unknown_label_rows=23,training_selected_security_count=77,training_selected_issuer_count=76,training_not_selected_rows=24).items():integer(counts[k],n)
    exact(coverage['saved_label_counts'],dict(labels),'Saved label histogram')
    reviews=[dict(issuer_id=issuer,saved_labels_and_security_ids=groups,status='REVIEW_REQUIRED',certified_classification_conflict=False) for issuer,groups in sorted(issuer_labels.items()) if len(groups)>1]
    exact(coverage['issuer_label_reviews'],reviews,'Shared issuer differing labels only review, not certified conflict')
    exact(coverage['saved_wiring_scope'],{k:wiring[k] for k in ('schema','calendar','candidate_cutoff','late_review_count','late_annual_tickers','historical_denominators_preserved')},'Full wiring dates and historical denominator')
    require(len(wiring['historical_denominators_preserved'])==15,'All15 historical rows')
    exact(coverage['saved_training_scope'],{k:panel[k] for k in ('pool_scope','original_identity_assumed_window','evaluation_prior_fit_overlap_evidence','preserved_sidecar_references')},'Training boundary and complete sidecars')
    return dict(counts=counts,issuer_label_review_count=len(reviews),historical_denominator_rows=15,full_original_rows_verified=101,sidecars_preserved=True,classification_reperformed=False)

def expected_sources(refs):
    source={str(PRODUCER):PRODUCER_SHA}
    for r in refs.values():require(r['path'] not in source or source[r['path']]==r['sha256'],'Source conflict');source[r['path']]=r['sha256']
    require(len(refs)==9 and len(source)==10,'Nine sources plus producer')
    return source

def validate_evidence(d,b,refs):
    for name,role,schema,status,field in [('wiring_publication','wiring','BULK_CONDITIONAL_WIRING_PUBLICATION_V1','PUBLISHED_CONDITIONAL_METADATA_ONLY','wiring_reference'),('training_publication','training_panel','DATED_CONDITIONAL_TRAINING_PANEL_PUBLICATION_V1','PUBLISHED_TRAINING_PAYLOAD_NOT_FITTED','panel_reference')]:
        pub=d[name];require(pub['schema']==schema and pub['status']==status,'Successful parent receipt');exact(pub[field],refs[role],'Parent immutable bytes');exact(pub['source_hashes'],d[role]['source_hashes'],'Original parent source claims')
        for obj in (pub,d[role]):flags(obj,('point_in_time_verified','promotion_allowed','execution_authorized','fit_performed'))
    a=d['training_audit'];require(a['schema']=='DATED_TRAINING_PANEL_INDEPENDENT_READBACK_V1' and a['status']=='PASS','External training audit')
    for k,r in [('panel_sha256','training_panel'),('publication_sha256','training_publication'),('reader_sha256','training_reader')]:exact(a[k],refs[r]['sha256'],'External audit hash')
    for k,n in dict(security_count=77,issuer_count=76,observed_security_count=101,training_return_rows=126,training_numeric_cells=9702,preserved_sidecar_count=7,evaluation_numeric_fields_in_fit_payload=0).items():integer(a[k],n)
    flags(a,('fit_performed','raw_redecoded','old_audit_repeated','point_in_time_verified','legal_training_input_admitted','liquidity_qualification_at_training_cutoff_verified'))
    report=b['wiring_review_report'].decode('utf-8');require('PASS' in report,'Existing MD report evidence')
    for r in ('wiring','wiring_publication','wiring_reader'):require(refs[r]['sha256'] in report,'MD exact original hashes')

def guard(s):
    require(sha(SOURCE.read_bytes())==LOADED,'Reader source drift')
    for p,h in s.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)
def read(r,s):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['sha256']) is str and len(r['sha256'])==64,'Reference hash')
    require(r['path'] not in s or s[r['path']]==r['sha256'],'Source collision');b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed source bytes');s[r['path']]=r['sha256'];return b

def readback(*,execute=False):
    require(execute is True and not OUTPUT.exists(),'Explicit create-only readback')
    require(all(type(h) is str and len(h)==64 and set(h)<=set('0123456789abcdef') for h in (COVERAGE_SHA,PUBLICATION_SHA)),'Pending actual result anchors')
    refs={k:ref(ROOT/p,h) for k,(p,h) in BOUND.items()};base=expected_sources(refs);sources={str(SOURCE):LOADED,**base};guard(sources)
    require({p.name for p in PARENT.iterdir()}=={'started.json','coverage.json','publication.json'},'Exact successful producer directory')
    coverage_ref=ref(PARENT/'coverage.json',COVERAGE_SHA);pubref=ref(PARENT/'publication.json',PUBLICATION_SHA)
    out=loads(read(coverage_ref,sources));pub=loads(read(pubref,sources));sb=(PARENT/'started.json').read_bytes();sources[str(PARENT/'started.json')]=sha(sb);start=loads(sb)
    require(start['schema']=='SAVED_CLASSIFICATION_COVERAGE_STARTED_V1' and start['retry_allowed'] is False,'Producer started contract');flags(start,FLAGS);exact(start['input_references'],refs,'Started fixed source roles');exact(start['source_hashes'],base,'Started independently reconstructed closure')
    require(out['schema']=='SOURCE_BOUND_SAVED_CLASSIFICATION_COVERAGE_V1' and pub['schema']=='SAVED_CLASSIFICATION_COVERAGE_PUBLICATION_V1' and pub['status']=='PUBLISHED_CONDITIONAL_SAVED_LABEL_COVERAGE','Published coverage schema')
    flags(out,FLAGS);flags(pub,FLAGS);exact(out['source_hashes'],base,'Exact output closure');exact(pub['source_hashes'],base,'Exact publication closure');exact(out['input_references'],refs,'Fixed output refs');exact(pub['coverage_reference'],coverage_ref,'Publication actual bytes')
    blobs={k:read(r,sources) for k,r in refs.items()};docs={k:loads(blobs[k]) for k in ('wiring','wiring_publication','training_panel','training_publication','training_audit')};validate_evidence(docs,blobs,refs)
    exact(out['parent_source_hashes_preserved'],{k:docs[k]['source_hashes'] for k in ('wiring','training_panel')},'Unexpanded original source claims')
    require(out['wiring_audit_evidence_type']=='SAVED_REPORT_AND_READER_NOT_NEW_MACHINE_ATTESTATION' and out['direct_source_bytes_authenticated'] is True,'Saved source evidence type')
    detail=inspect(out['coverage'],docs['wiring'],docs['training_panel'],refs);guard(sources)
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        report=dict(schema='SAVED_CLASSIFICATION_COVERAGE_INDEPENDENT_READBACK_V1',status='PASS',coverage_reference=coverage_ref,publication_reference=pubref,reader_sha256=LOADED,source_hashes=sources,detail=detail,started_reference_externally_anchored=False,producer_called=False,core_called=False,**dict.fromkeys(FLAGS,False))
        b=enc(report);p=OUTPUT/'independent_readback.json'
        with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
        guard(sources);require(p.read_bytes()==b and {x.name for x in OUTPUT.iterdir()}=={'independent_readback.json'},'Final exact audit bytes/namespace');return ref(p,sha(b))
    except Exception as error:
        with (OUTPUT/'failure.json').open('xb') as f:f.write(enc(dict(status='FAILED_DO_NOT_CONSUME',error=str(error),retry_allowed=False)));f.flush();os.fsync(f.fileno())
        raise
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');a=p.parse_args();print(json.dumps(readback(execute=a.execute)))
