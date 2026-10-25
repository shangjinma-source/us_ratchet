"""Versioned capital journal. Explicit import preserves old claims; no account writes."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json,sqlite3
from core.strategy_account_ledger import canonical,require
from core.strategy_account_difference import number
from data.strategy_continuous32_target_decision import validate_result,PROFILE_ID,VERSION
from core.strategy_profiled_capital_intent_journal import ProfiledCapitalIntentJournal

class ProfiledCapitalJournalV2(ProfiledCapitalIntentJournal):
    TABLES={'intents','claims','prepared','withdrawals','arrivals'}
    def _connect(self,write=False):
        require(not any(p.is_symlink() for p in [self.path,*self.path.parents]),'CAPITAL_JOURNAL_SYMLINK')
        require(self.path.exists(),'CAPITAL_V2_IMPORT_REQUIRED')
        con=sqlite3.connect(self.path.absolute().as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,isolation_level=None,timeout=10)
        try:require({r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}==self.TABLES,'CAPITAL_JOURNAL_RECOVERY_REQUIRED')
        except BaseException:con.close();raise
        return con

    def initialize_from_legacy(self,legacy):
        """Explicit preparation, never implicit during service construction."""
        require(not self.path.exists(),'CAPITAL_V2_ALREADY_EXISTS')
        require(not any(p.is_symlink() for p in [self.path,*self.path.parents]),'CAPITAL_JOURNAL_SYMLINK')
        rows={name:[] for name in ('intents','claims','prepared')}
        if legacy.path.exists():
            with closing(legacy._connect()) as source:
                source.execute('BEGIN')
                for name in rows:rows[name]=source.execute('SELECT * FROM '+name).fetchall()
                for event_id,_ in rows['intents']:legacy._read(source,event_id);legacy._prepared(source,event_id)
                source.rollback()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive file creation prevents replacing any existing failed import.
        with self.path.open('xb'):pass
        with closing(sqlite3.connect(self.path)) as con:
            con.execute('CREATE TABLE intents(event_id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
            con.execute('CREATE TABLE claims(event_id TEXT PRIMARY KEY,intent_sha256 TEXT NOT NULL)')
            con.execute('CREATE TABLE prepared(event_id TEXT PRIMARY KEY,digest TEXT NOT NULL,payload TEXT NOT NULL)')
            con.execute('CREATE TABLE withdrawals(event_id TEXT PRIMARY KEY,digest TEXT NOT NULL,payload TEXT NOT NULL)')
            con.execute('CREATE TABLE arrivals(event_id TEXT PRIMARY KEY,digest TEXT NOT NULL,payload TEXT NOT NULL)')
            for name,values in rows.items():
                if values:con.executemany('INSERT INTO '+name+' VALUES('+','.join('?' for _ in values[0])+')',values)
            con.commit()

    def _document(self,con,table,event_id):
        row=con.execute('SELECT digest,payload FROM '+table+' WHERE event_id=?',(event_id,)).fetchone()
        if row is None:return None
        require(len(row[1].encode())<=16384,'CAPITAL_DOCUMENT_BUDGET')
        item=json.loads(row[1]);require(canonical(item).decode()==row[1] and sha256(canonical(item)).hexdigest()==row[0] and item['event_id']==event_id,'CAPITAL_DOCUMENT_CORRUPT')
        return item

    def arrival(self,event_id):
        with closing(self._connect()) as con:return self._document(con,'arrivals',event_id)

    def save_arrival(self,item):
        raw=canonical(item);require(len(raw)<=16384,'CAPITAL_DOCUMENT_BUDGET')
        with closing(self._connect(True)) as con:
            con.execute('BEGIN IMMEDIATE')
            old=self._document(con,'arrivals',item['event_id'])
            if old is not None:require(old==item,'CAPITAL_EVENT_CONFLICT')
            else:
                require(self._read(con,item['event_id']) is None,'CAPITAL_LEGACY_EVENT_NOT_ARRIVAL')
                con.execute('INSERT INTO arrivals VALUES(?,?,?)',(item['event_id'],sha256(raw).hexdigest(),raw.decode()))
            con.commit()
        return deepcopy(item)

    def withdraw(self,event_id,*,target_store,reason,checked_at):
        require(reason=='FUNDS_NOT_RECEIVED','CAPITAL_WITHDRAWAL_REASON')
        status=self.reconcile(event_id,target_store=target_store)
        require(status['status'] in {'NOT_FOUND','INTENT_RECORDED','RECOVERY_REQUIRED','WITHDRAWN'},'CAPITAL_WITHDRAWAL_NOT_ALLOWED')
        with closing(self._connect(True)) as con:
            con.execute('BEGIN IMMEDIATE')
            intent=self._read(con,event_id)
            arrival=self._document(con,'arrivals',event_id)
            require(intent is not None or arrival is not None,'CAPITAL_INTENT_REQUIRED')
            subject=intent if intent is not None else arrival
            require(self._prepared(con,event_id) is None,'CAPITAL_PREPARED_WITHDRAWAL_REFUSED')
            old=self._document(con,'withdrawals',event_id)
            if old is None:
                item=dict(event_id=event_id,intent_sha256=sha256(canonical(subject)).hexdigest(),reason=reason,checked_at=checked_at)
                raw=canonical(item);con.execute('INSERT INTO withdrawals VALUES(?,?,?)',(event_id,sha256(raw).hexdigest(),raw.decode()))
            con.commit()
        return dict(status='WITHDRAWN',event_id=event_id,credited=False)

    def reconcile(self,event_id,*,target_store):
        result=super().reconcile(event_id,target_store=target_store)
        with closing(self._connect()) as con:
            withdrawn=self._document(con,'withdrawals',event_id)
            if withdrawn:
                intent=self._read(con,event_id) or self._document(con,'arrivals',event_id)
                require(withdrawn['intent_sha256']==sha256(canonical(intent)).hexdigest() and result['status'] in {'NOT_FOUND','RECOVERY_REQUIRED','INTENT_RECORDED'},'CAPITAL_WITHDRAWAL_CONFLICT')
                return dict(status='WITHDRAWN',event_id=event_id,may_start_selection=False)
        return result

    def claim_selection_once(self,event_id,*,account_state,previous_target):
        with closing(self._connect(True)) as con:
            con.execute('BEGIN IMMEDIATE')
            intent=self._read(con,event_id);require(intent is not None,'CAPITAL_INTENT_REQUIRED')
            require(self._document(con,'withdrawals',event_id) is None,'CAPITAL_INTENT_WITHDRAWN')
            digest=sha256(canonical(intent)).hexdigest()
            existing=con.execute('SELECT intent_sha256 FROM claims WHERE event_id=?',(event_id,)).fetchone()
            if existing:
                require(existing==(digest,),'CAPITAL_CLAIM_CORRUPT')
                return dict(status='RECOVERY_REQUIRED',may_start_selection=False,intent_sha256=digest)
            self._validate(intent,account_state,previous_target)
            for (raw,) in con.execute('SELECT intents.payload FROM intents JOIN claims USING(event_id)'):
                other=json.loads(raw)
                if other['account_id']==intent['account_id'] and other['previous_target_id']==intent['previous_target_id']:
                    withdrawn=self._document(con,'withdrawals',other['event_id'])
                    require(withdrawn is not None and withdrawn['intent_sha256']==sha256(canonical(other)).hexdigest(),'CAPITAL_TARGET_ALREADY_CLAIMED')
            con.execute('INSERT INTO claims VALUES(?,?)',(event_id,digest));con.commit()
        return dict(status='SELECTION_CLAIMED',may_start_selection=True,intent_sha256=digest,target_request_binding=dict(event_id='capital:'+digest,reason='EXPLICIT_RECONFIGURE',expected_revision=intent['account_revision'],previous_target_id=intent['previous_target_id'],capital_event_id=event_id,capital_intent_sha256=digest))

    def source_directory(self,event_id):
        return self.path.parent/(self.path.stem+'-sources')/sha256(event_id.encode()).hexdigest()

    def seal_sources(self,event_id,files,hashes):
        from data.strategy_upgrade_blob_store_v1 import save_sources
        return save_sources(self.source_directory(event_id),files,hashes)

    def _validate_prepared(self,intent,prepared):
        state=prepared["account_state"];prior=prepared["previous_target"]
        self._validate(intent,state,prior)
        require(prepared["intent_sha256"]==sha256(canonical(intent)).hexdigest(),"CAPITAL_PREPARED_INTENT_MISMATCH")
        decision=prepared["decision"];payload=decision["payload"];binding=payload["input_binding"]
        require(decision["status"]=="TARGET_READY" and
                sha256(canonical(payload)).hexdigest()==decision["decision_id"] and
                sha256(canonical(binding)).hexdigest()==payload["input_id"],"CAPITAL_DECISION_INVALID")
        require(binding["account_id"]==intent["account_id"] and
                binding["account_revision"]==intent["account_revision"] and
                binding["strategy_shares"]==state["shares"] and
                number(binding["execution_context"]["available_cash"])==number(intent["available_balance"]) and
                number(binding["total_uninvested_cash"])==number(state["total_uninvested_cash"]),
                "CAPITAL_DECISION_SNAPSHOT_MISMATCH")
        values={sid:number(binding["marks"][sid]["price"])*q for sid,q in state["shares"].items() if q}
        require(set(binding["holding_market_values"])==set(values) and
                all(number(binding["holding_market_values"][sid])==v for sid,v in values.items()),
                "CAPITAL_HOLDING_VALUATION_MISMATCH")
        equity=number(state["total_uninvested_cash"])+sum(values.values())
        require(number(binding["strategy_equity"])==equity and
                number(binding["search_arguments"]["entered_cash"])==equity,
                "CAPITAL_EQUITY_MISMATCH")
        require(binding.get('selector_profile')==PROFILE_ID and binding.get('selection_method')==VERSION
                and binding.get('continuous_iterations')==32,'CAPITAL_CONTINUOUS32_BINDING_REQUIRED')
        profile=prepared["profile"];args=binding["search_arguments"];result=payload["search_result"]
        require(set(profile)=={"method_version","max_objective_evaluations","source_pins","selector_profile","continuous_iterations"} and
                type(profile["max_objective_evaluations"]) is int and
                profile["max_objective_evaluations"]>0 and
                type(args["max_objective_evaluations"]) is int and
                args["max_objective_evaluations"]==profile["max_objective_evaluations"] and
                result["method_version"]==profile["method_version"]==VERSION and
                profile["selector_profile"]==PROFILE_ID and type(profile["continuous_iterations"])is int
                and profile["continuous_iterations"]==32,"CAPITAL_PROFILE_MISMATCH")
        from data.strategy_upgrade_blob_store_v1 import load_sources,validate_files
        pins=binding["source_hashes"]
        if 'source_blob_reference' in prepared:
            files=load_sources(self.source_directory(intent['event_id']),prepared['source_blob_reference'])
            validate_files(files,pins)
        else:
            # Old prepared records remain readable under the original protocol.
            return super()._validate_prepared(intent,prepared)
        require(bool(profile["source_pins"]) and all(pins.get(n)==h for n,h in profile["source_pins"].items()),
                "CAPITAL_PROFILE_SOURCE_MISMATCH")
        require(validate_result(result,args)==payload["target_quantities"],"CAPITAL_DECISION_QUANTITIES_MISMATCH")

    def prepare(self,event_id,*,decision,source_files,profile,account_state,previous_target):
        from data.strategy_upgrade_blob_store_v1 import load_sources
        directory=self.source_directory(event_id)
        reference=dict(schema='UPGRADE_SOURCE_BLOB_REFERENCE_V1',manifest_sha256=sha256((directory/'manifest.json').read_bytes()).hexdigest())
        require(load_sources(directory,reference)==source_files,'CAPITAL_SOURCE_CHANGED')
        with closing(self._connect(True)) as con:
            con.execute('BEGIN IMMEDIATE')
            intent=self._read(con,event_id);require(intent is not None,'CAPITAL_INTENT_REQUIRED')
            digest=sha256(canonical(intent)).hexdigest()
            require(con.execute('SELECT intent_sha256 FROM claims WHERE event_id=?',(event_id,)).fetchone()==(digest,),'CAPITAL_SELECTION_CLAIM_REQUIRED')
            value=dict(intent_sha256=digest,decision=deepcopy(decision),profile=deepcopy(profile),account_state=deepcopy(account_state),previous_target=deepcopy(previous_target),source_blob_reference=reference)
            self._validate_prepared(intent,value)
            raw=canonical(value);require(len(raw)<=48*1024*1024,'CAPITAL_PREPARED_BUDGET')
            old=self._prepared(con,event_id);require(old is None or old==value,'CAPITAL_PREPARED_CONFLICT')
            if old is None:con.execute('INSERT INTO prepared VALUES(?,?,?)',(event_id,sha256(raw).hexdigest(),raw.decode()))
            con.commit()
        return dict(status='PREPARED_PUBLISH_ONLY',prepared_sha256=sha256(raw).hexdigest(),may_start_selection=False)
