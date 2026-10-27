"""One isolated two-mechanism research judgment; no economic execution."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import getproxies
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.research.propose_news_actions_v1 import command,validate_trace_item

def obj(properties):return dict(type='object',additionalProperties=False,required=list(properties),properties=properties)
def schema():
    string={'type':'string'};strings=dict(type='array',items=string)
    evidence=dict(type='array',maxItems=5,items=obj(dict(source_id=string,quote=string)))
    common=dict(reason=string,counterevidence=strings,uncertainty=strings,evidence=evidence)
    return obj(dict(source_id=string,shared_facts=dict(type='array',maxItems=5,items=obj(dict(fact=string,exact_quote=string,source_id=string,uncertainty=string))),
        A_direct=obj(dict(common,action=dict(type='string',enum=['KEEP','PAUSE_BUY','REDUCE_BUY','REDUCE_HOLDING','EXIT','ABSTAIN']),buy_fraction=string,holding_fraction=string)),
        B_signal=obj(dict(common,direction=dict(type='string',enum=['NEGATIVE','NEUTRAL','POSITIVE','ABSTAIN']),materiality=dict(type='string',enum=['HIGH','MODERATE','UNCERTAIN']))),limitations=strings))
def source_records(record):
    records=record.get("sources",[record])
    if not records or len(records)>2:raise ValueError("SOURCE_COUNT_INVALID")
    if len({r["id"] for r in records})!=len(records):raise ValueError("DUPLICATE_SOURCE_ID")
    for r in records:
        if sha256(r["text"].encode()).hexdigest()!=r["text_sha256"]:raise ValueError("TEXT_HASH_MISMATCH")
    if record["id"] not in {r["id"] for r in records}:raise ValueError("CURRENT_SOURCE_MISSING")
    return {r["id"]:r for r in records}

def validate(answer,record):
    import jsonschema
    jsonschema.validate(answer,schema())
    if answer['source_id']!=record['id']:raise ValueError('SOURCE_ID_MISMATCH')
    sources=source_records(record)
    normalize=lambda value:re.sub(r'\s+',' ',value).strip()
    pairs=[(r['source_id'],r['exact_quote']) for r in answer['shared_facts']]
    for name in ('A_direct','B_signal'):
        branch=answer[name]
        if branch.get('action',branch.get('direction'))!='ABSTAIN' and not branch['evidence']:raise ValueError('EVIDENCE_REQUIRED')
        pairs.extend((r['source_id'],r['quote']) for r in branch['evidence'])
    for sid,quote in pairs:
        if sid not in sources or not normalize(quote) or normalize(quote) not in normalize(sources[sid]['text']):raise ValueError('QUOTE_NOT_IN_SOURCE')
    a=answer['A_direct'];b=Fraction(a['buy_fraction']);h=Fraction(a['holding_fraction'])
    valid={'KEEP':b==h==1,'ABSTAIN':b==h==1,'PAUSE_BUY':b==0 and h==1,'REDUCE_BUY':0<b<1 and h==1,'REDUCE_HOLDING':b==0 and 0<h<1,'EXIT':b==h==0}
    if not valid[a['action']]:raise ValueError('ACTION_FRACTIONS_MISMATCH')
    return answer

def run(input_path,prompt_path,contract_path,output):
    now=lambda:datetime.now(timezone.utc).isoformat()
    digest=lambda p:sha256(p.read_bytes()).hexdigest()
    contract=json.loads(contract_path.read_text(encoding='utf8'))
    if contract['input_sha256']!=digest(input_path) or contract['prompt_sha256']!=digest(prompt_path):raise ValueError('FROZEN_INPUT_CHANGED')
    if datetime.now(timezone.utc)>=datetime.fromisoformat(contract['no_start_after_utc'].replace('Z','+00:00')):raise ValueError('START_DEADLINE_PASSED')
    record=json.loads(input_path.read_text(encoding='utf8'))
    sources=source_records(record)
    prompt=prompt_path.read_text(encoding='utf8')+json.dumps(record,ensure_ascii=False)
    if len(prompt)>(110000 if 'sources' in record else 60000):raise ValueError('FULL_INPUT_TOO_LARGE')
    output.mkdir(parents=True,exist_ok=False)
    def save(name,value):(output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
    save('public_input.json',record);save('schema.json',schema())
    receipt=dict(status='STARTED',attempts=1,model='gpt-6.1-sol',effort='medium',started_at=now(),contract_sha256=digest(contract_path),input_sha256=digest(input_path),prompt_sha256=sha256(prompt.encode()).hexdigest(),source_text_sha256=record.get('text_sha256'),source_text_hashes={key:value['text_sha256'] for key,value in sources.items()},usage=None,production_authorized=False,semantic_review_required=True)
    save('receipt.json',receipt);start=time.monotonic()
    try:
        executable=shutil.which('codex')
        if not executable:raise ValueError('CLI_UNAVAILABLE')
        environment=os.environ.copy()
        for scheme,address in getproxies().items():
            if scheme in ('http','https'):environment.setdefault(scheme.upper()+'_PROXY',address)
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        with tempfile.TemporaryDirectory(prefix='news-two-mechanisms-') as directory:
            workspace=Path(directory);answer_path=workspace/'answer.json'
            args=command(executable,workspace,(output/'schema.json').resolve(),answer_path)
            if args[args.index('--model')+1]!=receipt['model']:raise ValueError('MODEL_MISMATCH')
            process=subprocess.Popen(args,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',errors='replace',creationflags=flags)
            timedout=False
            try:stdout,stderr=process.communicate(prompt,timeout=180)
            except subprocess.TimeoutExpired:
                timedout=True
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10,creationflags=flags)
                else:process.kill()
                stdout,stderr=process.communicate(timeout=10)
            (output/'trace.jsonl').write_text(stdout,encoding='utf8');(output/'stderr.txt').write_text(stderr,encoding='utf8')
            events=[json.loads(line) for line in stdout.splitlines()]
            complete=[e for e in events if e.get('type')=='turn.completed']
            if complete:receipt['usage']=complete[-1].get('usage')
            if answer_path.exists():
                (output/'raw_answer.txt').write_bytes(answer_path.read_bytes())
            for event in events:validate_trace_item(event.get('item',{}))
            if timedout:raise ValueError('MODEL_TIMEOUT')
            if process.returncode or len(complete)!=1 or not answer_path.exists():raise ValueError('MODEL_RESPONSE_INCOMPLETE')
            answer=json.loads(answer_path.read_text(encoding='utf8'));save('raw_answer.json',answer)
            validate(answer,record);save('answer.json',answer)
            receipt.update(status='PENDING_INDEPENDENT_SEMANTIC_REVIEW',answer_sha256=digest(output/'answer.json'))
    except Exception as error:receipt.update(status='FAILED',error=str(error))
    finally:
        receipt.update(finished_at=now(),elapsed_seconds=round(time.monotonic()-start,3));save('receipt.json',receipt)
    return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True);parser.add_argument('--prompt',type=Path,required=True);parser.add_argument('--contract',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(run(args.input,args.prompt,args.contract,args.output)))
