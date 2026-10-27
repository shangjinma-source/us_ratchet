"""Offline source-reviewed AI fact bridge. No model calls or production wiring.

Independent source_review is trusted semantic annotation, not model approval.
Positive admission additionally requires a source-bound numerical comparison;
AI classification or a review boolean alone cannot create CUT.
"""
import argparse
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.research.extract_news_risk_facts_v1 import validate_input,validate_output
from scripts.research.guidance_numeric_comparator_v1 import compare_guidance


def bridge(root, run_directory, review_path):
    root=Path(root).resolve();run_directory=Path(run_directory);review_path=Path(review_path)
    provenance={}
    def read(path):
        raw=path.read_bytes();provenance[str(path)]=sha256(raw).hexdigest();return json.loads(raw)
    review=read(review_path)
    run={name:read(run_directory/name) for name in ('input.json','answer.json','receipt.json')}
    for name in run:
        if review.get(name.removesuffix('.json')+'_sha256')!=provenance[str(run_directory/name)]:raise ValueError('REVIEW_RUN_HASH_MISMATCH')
    for relative,expected in review.get('source_hashes',{}).items():
        path=(root/relative).resolve()
        if not path.is_relative_to(root):raise ValueError('SOURCE_OUTSIDE_WORKSPACE')
        actual=sha256(path.read_bytes()).hexdigest()
        if actual!=expected:raise ValueError('SOURCE_REVIEW_DEPENDENCY_HASH_MISMATCH')
        provenance[str(path)]=actual
    receipt=run['receipt.json']
    if (receipt.get('status')!='FACT_EXTRACTION_QUOTE_BOUND_SEMANTIC_REVIEW_REQUIRED'
            or receipt.get('source_input_sha256')!=provenance[str(run_directory/'input.json')]
            or receipt.get('rule_admitted') is not False or receipt.get('semantic_review_required') is not True):
        raise ValueError('EXTRACTION_RECEIPT_NOT_BOUND')
    public=validate_input(run['input.json'])
    answer=validate_output(deepcopy(run['answer.json']),public)
    input_rows={r['id']:r for r in run['input.json']['records']}
    reviewed={r['id']:r for r in review['records']}
    if len(reviewed)!=len(review['records']) or set(reviewed)!=set(input_rows):raise ValueError('REVIEW_IDS_MISMATCH')
    events=[];decisions=[];input_errors=[]
    for model in answer['records']:
        identifier=model['id'];record=reviewed[identifier];original=input_rows[identifier]
        decision=dict(id=identifier,model_classification=model['classification'],admitted=False)
        try:
            path=(root/record['source_path']).resolve()
            if not path.is_relative_to(root):raise ValueError('SOURCE_OUTSIDE_WORKSPACE')
            digest=sha256(path.read_bytes()).hexdigest();provenance[str(path)]=digest
            if digest!=record['source_original_sha256'] or digest!=original['original_sha256']:raise ValueError('ORIGINAL_SOURCE_HASH_MISMATCH')
            if record.get('source_url')!=original['url']:raise ValueError('SOURCE_URL_MISMATCH')
            if record['source_text_sha256']!=original['text_sha256'] or record['evidence_quote']!=model['evidence_quote']:raise ValueError('REVIEW_TEXT_OR_QUOTE_MISMATCH')
            if record['reviewed_classification']!=model['classification']:raise ValueError('SEMANTIC_CLASSIFICATION_NOT_CONFIRMED')
            if model['classification']!='TEMPORARY_DELIVERY_CONSTRAINT':
                decision['reason']='OTHER_OR_UNKNOWN_NOT_REPAIR' if model['classification'] in ('OTHER','UNKNOWN') else 'REPAIR_ADMISSION_NOT_IMPLEMENTED'
                decisions.append(decision);continue
            comparison=record.get('comparative',{})
            decision['comparative_review_reason']=comparison.get('reason')
            decision['qualitative_delivery_reduction_supported']=comparison.get('qualitative_delivery_reduction_supported',False)
            decision['temporary_constraint_supported']=comparison.get('temporary_constraint_supported',False)
            if comparison.get('status')!='VERIFIED_SAME_SCOPE_STRICT_LOWER':raise ValueError('COMPARABLE_LOWER_EVIDENCE_NOT_VERIFIED')
            scope=record['scope']
            for field in ('issuer_cik','security_id','year','product','dose','metric','period_end'):
                if not isinstance(scope.get(field),str) or not scope[field].strip():raise ValueError('REVIEWED_SCOPE_REQUIRED')
            if any(scope[k]!=model[k] for k in ('year','product','dose')):raise ValueError('MODEL_SCOPE_NOT_REVIEW_BOUND')
            numeric=comparison.get('numeric_comparison')
            if not isinstance(numeric,dict):raise ValueError('SOURCE_BOUND_NUMERIC_COMPARISON_REQUIRED')
            previous,current=numeric['previous'],numeric['current']
            if (current['source_sha256']!=record['source_text_sha256'] or current['issuer_cik'].zfill(10)!=scope['issuer_cik'].zfill(10)
                    or current['metric']!=scope['metric'] or current['fiscal_period_end']!=scope['period_end']):
                raise ValueError('COMPARISON_SCOPE_NOT_BOUND')
            # Prior/current evidence must also have independent file-backed hashes.
            for source_hash, source in numeric['verified_sources'].items():
                rawpath=(root/source['text_path']).resolve()
                if not rawpath.is_relative_to(root):raise ValueError('SOURCE_OUTSIDE_WORKSPACE')
                text=rawpath.read_text(encoding='utf-8')
                if text!=source['text'] or sha256(text.encode()).hexdigest()!=source_hash:raise ValueError('COMPARATIVE_SOURCE_TEXT_MISMATCH')
                provenance[str(rawpath)]=sha256(rawpath.read_bytes()).hexdigest()
            if compare_guidance(previous,current,numeric['verified_sources'])['status']!='NUMERIC_GUIDANCE_CUT_CANDIDATE':
                raise ValueError('COMPARISON_NOT_STRICT_CUT')
            available=datetime.fromisoformat(record['available_at'].replace('Z','+00:00'))
            if available.utcoffset() is None or available<datetime.fromisoformat(current['publication_datetime'].replace('Z','+00:00')):
                raise ValueError('REVIEWED_AVAILABILITY_REQUIRED')
            if (scope['issuer_cik'].zfill(10)!='0001682852' or scope['security_id']!='research:security:mrna'
                    or scope['year']!='FY2021' or scope['period_end']!='2021-12-31'
                    or scope['dose'] not in ('100 µg','100ug','100 μg') or scope.get('geography')!='GLOBAL'
                    or scope['metric']!='Vaccine Dose Deliveries' or scope['product']!='Moderna COVID-19 vaccine'):
                raise ValueError('TRACKED_RISK_SCOPE_MISMATCH')
            key='MRNA_FY2021_100UG_GLOBAL_DELIVERY_DELAY'
            events.append(dict(id=identifier,classification='CUT',security_id=scope['security_id'],comparison_key=key,
                period_end=scope['period_end'],available_at=available.isoformat(),source_hashes=[digest,record['source_text_sha256']],
                review_reference=str(review_path),source_path=record['source_path'],interpretation='CONDITIONAL_RESEARCH_ONLY_AI_PLUS_INDEPENDENT_COMPARISON'))
            decision.update(admitted=True,reason='TEMPORARY_AND_SOURCE_BOUND_COMPARABLE_LOWER')
        except (KeyError,ValueError,TypeError,OSError) as error:
            decision['reason']=str(error)
            if not isinstance(error,ValueError) or str(error) not in {
                'COMPARABLE_LOWER_EVIDENCE_NOT_VERIFIED', 'SOURCE_BOUND_NUMERIC_COMPARISON_REQUIRED',
                'COMPARISON_NOT_STRICT_CUT', 'REVIEWED_SCOPE_REQUIRED',
                'MODEL_SCOPE_NOT_REVIEW_BOUND', 'TRACKED_RISK_SCOPE_MISMATCH'}:
                input_errors.append(dict(id=identifier,error_type=type(error).__name__,reason=str(error)))
        decisions.append(decision)
    if input_errors:events=[]
    return dict(schema='NEWS_FACT_RULE_BRIDGE_V1',status='INVALID_INPUT' if input_errors else 'ADMITTED_CONDITIONAL_RESEARCH' if events else 'NOT_ADMITTED',
        validation_complete=not input_errors,input_errors=input_errors,
        rule_version='STRICT_COMPARABLE_NUMERIC_REDUCTION_AND_DELAY_V1',
        rule_admitted=bool(events),events=events,action_policy='BLOCK_NEW_BUYS',release_policy='EXPLICIT_REPAIR',
        decisions=decisions,provenance=provenance,scope='THREE_MODEL_RECORDS_NOT_COMPLETE_UPDATE_CHAIN',
        semantic_review_required=True,production_authorized=False,
        limitations=['Numeric comparison is a condition of this research version, not a universal requirement for news-based rules.',
                    'Numeric rejection does not negate separately evidenced qualitative fewer deliveries or temporary delay.'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.');p.add_argument('--run',required=True);p.add_argument('--source-review',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();root=Path(a.root).resolve();result=bridge(root,root/a.run,root/a.source_review)
    output=root/a.output;output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(result['status'])
