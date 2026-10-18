"""Synchronous, explicit monthly full-account research registration.

No production instance. Server admission asserts training/domain provenance;
byte checks do not establish historical PIT or corporate-action completeness.
A crashed ATTEMPT_STARTED is intentionally not automatically retried.
"""
import base64
import gzip
from contextlib import closing
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from zoneinfo import ZoneInfo
from data.current_quantity_portfolio_research_v2 import WORKER,WORKER_SHA256,WORKER_DEPENDENCIES
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require,stamp,number
from data.current_quantity_v2_difference_service import document,CurrentQuantityV2DifferenceService
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_paper_chain import review_chain
from data.current_quantity_v2_monthly_retarget import active_proposal
from data.current_quantity_projection_v2 import project_capital_decision_v2
from data.current_research_capital_decision_v2 import VERSION
from data.current_research_ohlc_panel import parse_provider_ohlc
from data.current_research_intraday_journal import _publish


def _hash(value):return sha256(canonical(value)).hexdigest()


class QuantityV2MonthlyDecisionRegistry:
    def __init__(self,*,storage_root,clock=lambda:datetime.now(timezone.utc)):
        self.root=Path(storage_root);self.clock=clock

    def _prepare(self,state,package):
        state=review_chain(state);ledger=state['ledger'];old=active_proposal(ledger)
        identity=CurrentQuantityV2DifferenceService._package_identity(package)
        files=package['files'];pins=package['source_hashes'];docs=package['documents']
        for p in pins:CurrentQuantityV2CurrentCashSources._path(p)
        require(set(docs)=={'training','admission','calendar','identities'},'MONTHLY_TRAINING_DOCUMENTS')
        data,admission,calendar,identities=(document(files[docs[k]]) for k in ('training','admission','calendar','identities'))
        args=data['search_arguments'];day=args['decision_date'];now=stamp(self.clock())
        require(all(o['closed'] for o in ledger['orders'].values()) and number(ledger['reserved_cash'])==0 and not any(ledger['reserved_shares'].values()),'PRIOR_ORDERS_OPEN')
        require(admission['status']=='ADMITTED_MONTHLY_FULL_ACCOUNT_V2' and admission['method']==VERSION
            and admission['account_id']==ledger['account_id'] and admission['state_revision']==ledger['revision']
            and admission['input_path']==docs['training'] and admission['input_sha256']==pins[docs['training']]
            and admission['complete_candidate_domain'] is True and admission['mature_training_reviewed'] is True
            and admission['pending_rights']==[],'MONTHLY_ADMISSION_MISMATCH')
        require(calendar['decision_date']==day and calendar['target_month']==admission['target_month']
            and calendar['source_references'] and all(p in pins for p in calendar['source_references'])
            and calendar['active_date'][:7]==calendar['target_month']
            and calendar['target_month']> (old.get('target_month') or old['causal_inputs']['target_mandate']['target_month'])
            and old['causal_inputs']['capital_decision']['decision_date']<day<=calendar['active_date']
            and calendar['target_month']==now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
            and stamp(calendar['decision_close_at'])<=stamp(calendar['active_open_at'])<=now
            and stamp(calendar['decision_close_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()==day
            and stamp(calendar['active_open_at']).astimezone(ZoneInfo('America/New_York')).date().isoformat()==calendar['active_date'], 'MONTHLY_CALENDAR_MISMATCH')
        require(max(stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at']))<=stamp(calendar['decision_close_at']), 'VALUATION_PRECEDES_LEDGER')
        require(max(stamp(calendar['decision_close_at']),stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at']))<=stamp(admission['reviewed_at'])<=now and admission['source_references'] and all(p in pins for p in admission['source_references']),'MONTHLY_ADMISSION_SOURCE_REQUIRED')
        require(all(p in files for p in (*WORKER_DEPENDENCIES,WORKER)) and pins[WORKER]==WORKER_SHA256,'MONTHLY_IMPLEMENTATION_CLOSURE')
        domain=set(args['prices']);needed=domain|{s for s,q in ledger['shares'].items() if q}
        quotes={q['security_id']:q for q in data['valuation_quotes']}
        require(len(quotes)==len(data['valuation_quotes']) and set(quotes)==needed and set(data['bar_sources'])==needed,'MONTHLY_FULL_VALUATION_DOMAIN')
        require(domain==set(args['metadata']) and needed<=set(identities['securities']) and identities['source_references'] and all(p in pins for p in identities['source_references']),'MONTHLY_IDENTITY_DOMAIN')
        for sid in needed:
            source=data['bar_sources'][sid];quote=quotes[sid];security=identities['securities'][sid]
            if sid in domain:require(all(security.get(k)==v for k,v in args['metadata'][sid].items()),'MONTHLY_IDENTITY_MISMATCH')
            raw=files[source['path']];bars=parse_provider_ohlc(raw,security['ticker']);index=bars['dates'].index(day)
            parsed=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=Decimal)['chart']['result'][0]
            values=[Fraction(str(parsed['indicators']['quote'][0][k][index])) for k in ('open','high','low','close')]
            o,h,l,c=values
            require(min(values)>0 and l<=min(o,c)<=max(o,c)<=h,'MONTHLY_VALUATION_OHLC')
            require(quote['as_of']==day and source['price_basis']==quote['price_basis']==args['price_basis']
                and c==number(quote['price']) and source['path'] in quote['source_references']
                and all(p in pins for p in quote['source_references'])
                and (sid not in domain or c==number(args['prices'][sid])),'MONTHLY_VALUATION_COORDINATE')
        arguments=dict(decision_date=day,account_state=dict(asof=day,revision=ledger['revision'],cash=ledger['cash'],shares=deepcopy(ledger['shares']),reserved_cash='0'),
            valuation_quotes=deepcopy(data['valuation_quotes']),source_hashes=deepcopy(pins),search_arguments=deepcopy(args))
        binding=dict(account_id=ledger['account_id'],target_month=calendar['target_month'],state_revision=ledger['revision'],input_sha256=pins[docs['training']],package_identity=identity,chain_sha256=_hash(state))
        return state,arguments,calendar,identities,binding

    def _connect(self):
        self.root.mkdir(parents=True,exist_ok=True)
        connection=sqlite3.connect(self.root/'monthly_decisions.sqlite3',timeout=310)
        connection.execute('PRAGMA journal_mode=WAL')
        tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        require(tables<= {'monthly_decisions'},'FOREIGN_REGISTRY_DATABASE')
        connection.execute('CREATE TABLE IF NOT EXISTS monthly_decisions (id TEXT PRIMARY KEY, binding TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL, result TEXT, result_hash TEXT, error TEXT)')
        return connection

    def _save_inputs(self,key,package):
        root=self.root.resolve();folder=root/'inputs';folder.mkdir(exist_ok=True)
        require(folder.resolve().is_relative_to(root),'REGISTRY_PATH_ESCAPE')
        for p,raw in package['files'].items():_publish(folder/package['source_hashes'][p],raw)
        _publish(folder/(key+'.json'),canonical(dict(documents=package['documents'],source_hashes=package['source_hashes'])))
        return self._load_inputs(key)

    def _load_inputs(self,key):
        folder=(self.root/'inputs').resolve();require(folder.is_relative_to(self.root.resolve()),'REGISTRY_PATH_ESCAPE')
        manifest_path=folder/(key+'.json');require(manifest_path.stat().st_size<=4*1024*1024,'REGISTRY_SIZE_LIMIT')
        manifest=document(manifest_path.read_bytes());files={};total=0
        require(type(manifest['source_hashes'])is dict and 0<len(manifest['source_hashes'])<=2000,'REGISTRY_SOURCE_COUNT')
        for p,h in manifest['source_hashes'].items():
            CurrentQuantityV2CurrentCashSources._path(p)
            require(type(h)is str and len(h)==64 and all(c in '0123456789abcdef' for c in h),'REGISTRY_HASH_INVALID')
            path=folder/h;require(path.resolve().is_relative_to(folder),'REGISTRY_PATH_ESCAPE')
            size=path.stat().st_size;total+=size;require(size<=32*1024*1024 and total<=128*1024*1024,'REGISTRY_SIZE_LIMIT')
            raw=path.read_bytes();require(sha256(raw).hexdigest()==h,'REGISTRY_SOURCE_CHANGED');files[p]=raw
        return dict(files=files,**manifest)

    def _save_state_snapshot(self,key,state,binding):
        folder=(self.root/'inputs').resolve();require(folder.is_relative_to(self.root.resolve()),'REGISTRY_PATH_ESCAPE')
        raw=canonical(review_chain(state))
        require(len(raw)<=16*1024*1024 and sha256(raw).hexdigest()==binding['chain_sha256'],'REGISTRY_STATE_SNAPSHOT_INVALID')
        path=folder/(key+'.state.json');require(not path.is_symlink() and path.resolve().is_relative_to(folder),'REGISTRY_PATH_ESCAPE')
        _publish(path,raw)

    def audit(self,registration_id,account_id):
        """Historical-only read from the originally recorded account snapshot.

        Does not relax execution read binding or reconstruct missing old evidence.
        No clock, worker, account access, network, schema migration or writes.
        """
        require(type(registration_id)is str and len(registration_id)==64 and all(c in '0123456789abcdef' for c in registration_id),'INVALID_REGISTRATION_ID')
        require(type(account_id)is str and bool(account_id.strip()),'INVALID_ACCOUNT_ID')
        root=self.root.resolve();database=self.root/'monthly_decisions.sqlite3'
        require(database.resolve().is_relative_to(root),'REGISTRY_PATH_ESCAPE')
        require(database.is_file(),'MONTHLY_REGISTRY_MISSING')
        with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as con:
            row=con.execute('SELECT binding FROM monthly_decisions WHERE id=?',(registration_id,)).fetchone()
        require(row is not None,'MONTHLY_REGISTRATION_UNKNOWN');binding=document(row[0].encode())
        require(_hash(binding)==registration_id,'MONTHLY_REGISTRATION_BINDING_CHANGED')
        require(binding['account_id']==account_id,'ACCOUNT_BINDING_MISMATCH')
        folder=(root/'inputs').resolve();require(folder.is_relative_to(root),'REGISTRY_PATH_ESCAPE')
        path=folder/(registration_id+'.state.json');require(not path.is_symlink() and path.resolve().is_relative_to(folder),'REGISTRY_PATH_ESCAPE')
        require(path.is_file(),'HISTORICAL_STATE_SNAPSHOT_UNAVAILABLE_LEGACY_OR_MISSING')
        require(path.stat().st_size<=16*1024*1024,'REGISTRY_SIZE_LIMIT')
        with path.open('rb') as source:raw=source.read(16*1024*1024+1)
        require(len(raw)<=16*1024*1024,'REGISTRY_SIZE_LIMIT')
        require(sha256(raw).hexdigest()==binding['chain_sha256'],'HISTORICAL_STATE_SNAPSHOT_CHANGED')
        state=review_chain(document(raw))
        require(_hash(state)==binding['chain_sha256'] and state['ledger']['account_id']==account_id
                and state['ledger']['revision']==binding['state_revision'],'HISTORICAL_STATE_BINDING_MISMATCH')
        result=deepcopy(self.read(registration_id,state))
        if result['status'] in ('FAILED','ATTEMPT_STARTED'):
            result['reason']='MONTHLY_RESEARCH_FAILED' if result['status']=='FAILED' else 'MONTHLY_RESEARCH_ATTEMPT_UNFINISHED'
            result['worker_liveness']='UNKNOWN'
        return dict(status='HISTORICAL_AUDIT_ONLY',account_id=account_id,registration_id=registration_id,
            state_revision=binding['state_revision'],chain_sha256=binding['chain_sha256'],result=result,
            historical=True,audit_only=True,execution_blocked=True,selected_for_current_account=False,
            automatic_retry=False,worker_liveness='UNKNOWN',account_mutated=False,orders_created=False)

    @staticmethod
    def _validate_result(package,state,binding,result):
        data=document(package['files'][package['documents']['training']]);calendar=document(package['files'][package['documents']['calendar']]);ledger=state['ledger']
        quotes={q['security_id']:dict(price=str(number(q['price'])),as_of=q['as_of'],price_basis=q['price_basis'],source_references=q['source_references']) for q in data['valuation_quotes']}
        cash=number(ledger['cash']);equity=cash+sum((q*number(quotes[s]['price']) for s,q in ledger['shares'].items() if q),Fraction(0))
        args=deepcopy(data['search_arguments']);args.pop('quote_as_of');args.pop('price_basis');args['entered_cash']=str(equity)
        expected=dict(schema='CAPITAL_DECISION_MECHANIC_V2',selection_method=VERSION,decision_date=args['decision_date'],state_revision=ledger['revision'],available_cash=str(cash),reserved_cash='0',shares=deepcopy(ledger['shares']),valuation_quotes=quotes,investable_equity=str(equity),search_arguments=args,source_hashes=package['source_hashes'])
        decision=result['capital_decision'];project_capital_decision_v2(decision)
        require(decision['binding']==expected and decision['core_calls']==1,'MONTHLY_RESULT_INPUT_MISMATCH')
        mandate=dict(account_id=ledger['account_id'],capital_decision_id=decision['decision_id'],target_month=binding['target_month'],active_date=calendar['active_date'],source_references=[package['documents']['calendar']])
        require(result['registration_id']==_hash(binding) and result['account_id']==ledger['account_id'] and result['state_revision']==ledger['revision'] and result['target_month']==binding['target_month'] and result['target_mandate']==mandate
            and result['status']==('READY' if decision['target_quantities'] is not None else 'INCOMPLETE')
            and result['research_only'] is True and result['execution_blocked'] is True and result['orders_created'] is False and result['source_authenticated'] is False and result['source_bytes_verified'] is True
            and result['implementation_source_hashes']=={p:package['source_hashes'][p] for p in WORKER_DEPENDENCIES},'MONTHLY_RESULT_BINDING_MISMATCH')

    def generate(self,state,training_package,*,retry_failed=False):
        """One synchronous worker, max 300s. Only explicit known-failed retries."""
        package=deepcopy(training_package);state,arguments,calendar,identities,binding=self._prepare(state,package);key=_hash(binding)
        con=self._connect()
        try:
            con.execute('BEGIN IMMEDIATE');row=con.execute('SELECT status FROM monthly_decisions WHERE id=?',(key,)).fetchone()
            if row and row[0] in ('READY','COMPLETED_NO_SELECTION'):con.rollback();return self.read(key,state)
            require(not row or (row[0]=='FAILED' and retry_failed is True),'MONTHLY_ATTEMPT_IN_PROGRESS_OR_RETRY_REQUIRED')
            self._save_inputs(key,package)
            if row is None:self._save_state_snapshot(key,state,binding)
            if row:con.execute("UPDATE monthly_decisions SET status='ATTEMPT_STARTED', attempts=attempts+1,error=NULL WHERE id=?",(key,))
            else:con.execute('INSERT INTO monthly_decisions VALUES (?,?,?,?,?,?,?)',(key,canonical(binding).decode(),'ATTEMPT_STARTED',1,None,None,None))
            con.commit()
            try:
                request=dict(arguments=arguments,pins=package['source_hashes'],sources={p:base64.b64encode(package['files'][p]).decode() for p in WORKER_DEPENDENCIES})
                encoded=canonical(request);require(len(encoded)<=192*1024*1024,'MONTHLY_WORKER_INPUT_LIMIT')
                completed=subprocess.run([sys.executable,'-I','-S','-c',package['files'][WORKER].decode('utf-8-sig')],input=encoded,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300,check=False)
                require(completed.returncode==0 and len(completed.stdout)<=32*1024*1024,'MONTHLY_WORKER_FAILED')
                output=document(completed.stdout);decision=output['decision'];project_capital_decision_v2(decision)
                require(output['loaded_source_hashes']=={p:package['source_hashes'][p] for p in WORKER_DEPENDENCIES},'MONTHLY_WORKER_CLOSURE_MISMATCH')
                require(CurrentQuantityV2DifferenceService._package_identity(self._load_inputs(key))==binding['package_identity'],'REGISTRY_SOURCE_CHANGED')
                self._prepare(state,self._load_inputs(key)) # Final server clock/calendar check after synchronous worker.
                result=dict(status='READY' if decision['target_quantities'] is not None else 'INCOMPLETE',registration_id=key,account_id=binding['account_id'],target_month=binding['target_month'],state_revision=binding['state_revision'],capital_decision=decision,
                    target_mandate=dict(account_id=binding['account_id'],capital_decision_id=decision['decision_id'],target_month=binding['target_month'],active_date=calendar['active_date'],source_references=[package['documents']['calendar']]),
                    research_only=True,execution_blocked=True,source_authenticated=False,source_bytes_verified=True,orders_created=False,implementation_source_hashes=output['loaded_source_hashes'])
                self._validate_result(package,state,binding,result)
                raw=canonical(result).decode();con.execute("UPDATE monthly_decisions SET status=?,result=?,result_hash=? WHERE id=?",("READY" if result["status"]=="READY" else "COMPLETED_NO_SELECTION",raw,sha256(raw.encode()).hexdigest(),key));con.commit()
            except Exception as error:
                con.rollback();con.execute("UPDATE monthly_decisions SET status='FAILED',error=? WHERE id=?",(type(error).__name__+':'+str(error)[:1000],key));con.commit();raise
            return self.read(key,state)
        finally:con.close()

    def read(self,registration_id,state):
        """Read registered result/bytes only; no clock, worker, fetch or source refresh."""
        require(type(registration_id)is str and len(registration_id)==64 and all(c in '0123456789abcdef' for c in registration_id),'INVALID_REGISTRATION_ID')
        state=review_chain(state);path=self.root/'monthly_decisions.sqlite3';require(path.is_file(),'MONTHLY_REGISTRY_MISSING')
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as con:
            row=con.execute('SELECT binding,status,result,result_hash,error FROM monthly_decisions WHERE id=?',(registration_id,)).fetchone()
        require(row is not None,'MONTHLY_REGISTRATION_UNKNOWN');binding=document(row[0].encode())
        require(_hash(binding)==registration_id and binding['chain_sha256']==_hash(state),'MONTHLY_REGISTERED_ACCOUNT_CHANGED')
        package=self._load_inputs(registration_id);require(CurrentQuantityV2DifferenceService._package_identity(package)==binding['package_identity'],'REGISTRY_SOURCE_CHANGED')
        if row[1] not in ('READY','COMPLETED_NO_SELECTION'):return dict(status=row[1],registration_id=registration_id,reason=row[4],automatic_retry=False,worker_liveness='UNKNOWN' if row[1]=='ATTEMPT_STARTED' else 'TERMINATED_OR_NOT_STARTED',account_id=binding['account_id'],state_revision=binding['state_revision'],target_month=binding['target_month'])
        require(sha256(row[2].encode()).hexdigest()==row[3],'MONTHLY_RESULT_CHANGED');result=document(row[2].encode());project_capital_decision_v2(result['capital_decision'])
        self._validate_result(package,state,binding,result)
        return result

    def decision_package(self,registration_id,state):
        result=self.read(registration_id,state);require(result['status']=='READY','MONTHLY_RESULT_NOT_READY')
        package=self._load_inputs(registration_id);files=deepcopy(package['files']);pins=deepcopy(package['source_hashes']);identities=document(files[package['documents']['identities']])
        needed={s for m in (state['ledger']['shares'],result['capital_decision']['target_quantities'] or {}) for s,q in m.items() if q}
        identities['securities']={s:identities['securities'][s] for s in needed};documents={}
        for name,value in (('capital_decision',result['capital_decision']),('target_mandate',result['target_mandate']),('identities',identities)):
            p='monthly-generated/'+registration_id+'/'+name+'.json';require(p not in files,'GENERATED_PATH_CONFLICT');files[p]=canonical(value);pins[p]=sha256(files[p]).hexdigest();documents[name]=p
        return dict(files=files,source_hashes=pins,documents=documents)
