"""Isolated capital intent journal; target publication is the consumption authority.

Separate databases are not an atomic transaction. A durable one-shot claim gates
selection; after interruption an absent target means recovery, never permission
to run selection again. Consumption is derived from the validated target journal.
No cash, account or target writes are performed here.
"""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import base64

from core.strategy_account_ledger import canonical, replay, require
from core.strategy_account_difference import number
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_continuous32_target_decision import validate_result,PROFILE_ID,VERSION


class ProfiledCapitalIntentJournal:
    def __init__(self, path):
        self.path = Path(path)

    def _connect(self, write=False):
        require(not any(p.is_symlink() for p in [self.path,*self.path.parents]), "CAPITAL_JOURNAL_SYMLINK")
        if write and not self.path.exists():
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with closing(sqlite3.connect(self.path)) as con:
                con.execute("CREATE TABLE IF NOT EXISTS intents(event_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
                con.execute("CREATE TABLE IF NOT EXISTS claims(event_id TEXT PRIMARY KEY, intent_sha256 TEXT NOT NULL)")
                con.execute("CREATE TABLE IF NOT EXISTS prepared(event_id TEXT PRIMARY KEY, digest TEXT NOT NULL, payload TEXT NOT NULL)")
                con.commit()
        con=sqlite3.connect(self.path.absolute().as_uri()+("?mode=rw" if write else "?mode=ro"),
                            uri=True,isolation_level=None,timeout=10)
        try:
            require({r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    == {"intents","claims","prepared"}, "CAPITAL_JOURNAL_RECOVERY_REQUIRED")
        except BaseException:
            con.close()
            raise
        return con

    def _read(self, con, event_id):
        row=con.execute("SELECT payload FROM intents WHERE event_id=?",(event_id,)).fetchone()
        if row is None:return None
        require(len(row[0].encode())<=16384,"CAPITAL_INTENT_BUDGET")
        intent=json.loads(row[0])
        require(canonical(intent).decode()==row[0] and intent["event_id"]==event_id,
                "CAPITAL_INTENT_CORRUPT")
        return intent

    def intent(self,event_id):
        if not self.path.exists():return None
        with closing(self._connect()) as con:
            return deepcopy(self._read(con,event_id))

    @staticmethod
    def _validate(intent, state, target):
        require(type(intent) is dict and set(intent)=={
            "event_id","account_id","account_revision","previous_target_id","contribution_amount",
            "available_balance","balance_confirmation_reference"}, "CAPITAL_INTENT_FIELDS")
        require(type(intent["event_id"]) is str and 0<len(intent["event_id"])<=128,"CAPITAL_EVENT_ID")
        require(re.fullmatch("[a-f0-9]{64}",intent["account_revision"]) is not None,"CAPITAL_REVISION")
        require(number(intent["contribution_amount"])>0 and number(intent["available_balance"])>=0,
                "CAPITAL_AMOUNTS_INVALID")
        require(replay(state["account_id"],[r["payload"] for r in state["events"]])==state,
                "ACCOUNT_REPLAY_MISMATCH")
        require(intent["account_id"]==state["account_id"] and intent["account_revision"]==state["revision"],
                "STALE_REVISION")
        require(target is not None and intent["previous_target_id"]==target["target_id"]
                and target["payload"]["account_id"]==state["account_id"],"STALE_TARGET")
        require(state["cash_confirmation_valid"] and
                number(intent["available_balance"])==number(state["available_cash"]),
                "CAPITAL_BALANCE_CONFIRMATION_REQUIRED")
        confirmations=[r["payload"] for r in state["events"] if r["payload"]["kind"]=="CASH_CONFIRM"]
        require(bool(confirmations),"CAPITAL_BALANCE_CONFIRMATION_REQUIRED")
        latest=confirmations[-1]
        require(intent["balance_confirmation_reference"]==dict(event_id=latest["event_id"],
                payload_sha256=sha256(canonical(latest)).hexdigest()),"CAPITAL_BALANCE_REFERENCE_MISMATCH")

    def record(self, intent, *, account_state, previous_target):
        raw=canonical(intent)
        require(len(raw)<=16384,"CAPITAL_INTENT_BUDGET")
        with closing(self._connect(True)) as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                old=self._read(con,intent["event_id"])
                if old is not None:
                    require(old==intent,"CAPITAL_EVENT_CONFLICT")
                    con.rollback()
                    return deepcopy(old)
                self._validate(intent,account_state,previous_target)
                require(con.execute("SELECT COUNT(*) FROM intents").fetchone()[0]<1000,"CAPITAL_HISTORY_BUDGET")
                con.execute("INSERT INTO intents VALUES(?,?)",(intent["event_id"],raw.decode()))
                con.commit()
                return deepcopy(intent)
            except BaseException:
                con.rollback()
                raise

    def claim_selection_once(self, event_id, *, account_state, previous_target):
        with closing(self._connect(True)) as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                intent=self._read(con,event_id)
                require(intent is not None,"CAPITAL_INTENT_REQUIRED")
                digest=sha256(canonical(intent)).hexdigest()
                claim=con.execute("SELECT intent_sha256 FROM claims WHERE event_id=?",(event_id,)).fetchone()
                if claim is not None:
                    require(claim[0]==digest,"CAPITAL_CLAIM_CORRUPT")
                    con.rollback()
                    return dict(status="RECOVERY_REQUIRED",may_start_selection=False,intent_sha256=digest)
                self._validate(intent,account_state,previous_target)
                for (other_raw,) in con.execute(
                        "SELECT intents.payload FROM intents JOIN claims USING(event_id)"):
                    other=json.loads(other_raw)
                    require(not (other["account_id"]==intent["account_id"] and
                                 other["previous_target_id"]==intent["previous_target_id"]),
                            "CAPITAL_TARGET_ALREADY_CLAIMED")
                con.execute("INSERT INTO claims VALUES(?,?)",(event_id,digest))
                con.commit()
                return dict(status="SELECTION_CLAIMED",may_start_selection=True,intent_sha256=digest,
                    target_request_binding=dict(event_id="capital:"+digest,reason="EXPLICIT_RECONFIGURE",
                        expected_revision=intent["account_revision"],
                        previous_target_id=intent["previous_target_id"],
                        capital_event_id=event_id,capital_intent_sha256=digest))
            except BaseException:
                con.rollback()
                raise

    def reconcile(self, event_id, *, target_store):
        """Read the authoritative validated target history; never write consumption."""
        require(isinstance(target_store,StrategyMonthlyTargetStore),"AUTHORITATIVE_TARGET_STORE_REQUIRED")
        if not self.path.exists():return dict(status="NOT_FOUND",may_start_selection=False)
        with closing(self._connect()) as con:
            intent=self._read(con,event_id)
            if intent is None:return dict(status="NOT_FOUND",may_start_selection=False)
            digest=sha256(canonical(intent)).hexdigest()
            claim=con.execute("SELECT intent_sha256 FROM claims WHERE event_id=?",(event_id,)).fetchone()
            require(claim is None or claim[0]==digest,"CAPITAL_CLAIM_CORRUPT")
            prepared=self._prepared(con,event_id)
            require(prepared is None or claim==(digest,),"CAPITAL_SELECTION_CLAIM_REQUIRED")
        matches=[t for t in target_store.history() if
                 t["payload"]["request"].get("capital_event_id")==event_id]
        require(len(matches)<=1,"CAPITAL_MULTIPLE_TARGET_PUBLICATIONS")
        if matches:
            target=matches[0];payload=target["payload"];request=payload["request"]
            require(prepared is not None,"CAPITAL_PREPARED_CANDIDATE_REQUIRED")
            self._validate_prepared(intent,prepared)
            require(claim is not None and request.get("capital_intent_sha256")==digest
                    and request.get("event_id")=="capital:"+digest
                    and request.get("reason")=="EXPLICIT_RECONFIGURE"
                    and request.get("previous_target_id")==intent["previous_target_id"]
                    and request.get("expected_revision")==intent["account_revision"]
                    and payload["account_id"]==intent["account_id"]
                    and payload["previous_target_id"]==intent["previous_target_id"],
                    "CAPITAL_PUBLICATION_BINDING_MISMATCH")
            require(payload["decision"]==prepared["decision"] and
                    payload["target_quantities"]==prepared["decision"]["payload"]["target_quantities"]
                    and request.get("capital_prepared_sha256")==sha256(canonical(prepared)).hexdigest(),
                    "CAPITAL_PUBLISHED_DECISION_MISMATCH")
            return dict(status="CONSUMED_BY_PUBLISHED_TARGET",target_id=target["target_id"],
                        intent_sha256=digest,may_start_selection=False)
        if prepared is not None:self._validate_prepared(intent,prepared)
        return dict(status="PREPARED_PUBLISH_ONLY" if prepared else "RECOVERY_REQUIRED" if claim else "INTENT_RECORDED",
                    intent_sha256=digest,may_start_selection=False)

    def _prepared(self,con,event_id):
        row=con.execute("SELECT digest,payload FROM prepared WHERE event_id=?",(event_id,)).fetchone()
        if row is None:return None
        require(len(row[1].encode())<=48*1024*1024,"CAPITAL_PREPARED_BUDGET")
        value=json.loads(row[1])
        require(canonical(value).decode()==row[1] and sha256(row[1].encode()).hexdigest()==row[0],
                "CAPITAL_PREPARED_CORRUPT")
        return value

    @classmethod
    def _validate_prepared(cls,intent,prepared):
        state=prepared["account_state"];prior=prepared["previous_target"]
        cls._validate(intent,state,prior)
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
        files={name:base64.b64decode(encoded,validate=True) for name,encoded in prepared["source_files"].items()}
        pins=binding["source_hashes"]
        require(set(files)==set(pins) and 0<len(files)<=2000 and
                sum(map(len,files.values()))<=32*1024*1024 and
                all(sha256(raw).hexdigest()==pins[name] for name,raw in files.items()),
                "CAPITAL_SOURCE_CLOSURE_MISMATCH")
        require(bool(profile["source_pins"]) and all(pins.get(n)==h for n,h in profile["source_pins"].items()),
                "CAPITAL_PROFILE_SOURCE_MISMATCH")
        require(validate_result(result,args)==payload["target_quantities"],"CAPITAL_DECISION_QUANTITIES_MISMATCH")

    def prepare(self,event_id,*,decision,source_files,profile,account_state,previous_target):
        """Called once with server-generated selection output; never runs selection."""
        require(type(source_files) is dict and 0<len(source_files)<=2000
                and all(type(k)is str and type(v)is bytes for k,v in source_files.items())
                and sum(map(len,source_files.values()))<=32*1024*1024,"CAPITAL_SOURCE_BUDGET")
        with closing(self._connect(True)) as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                intent=self._read(con,event_id);require(intent is not None,"CAPITAL_INTENT_REQUIRED")
                digest=sha256(canonical(intent)).hexdigest()
                claim=con.execute("SELECT intent_sha256 FROM claims WHERE event_id=?",(event_id,)).fetchone()
                require(claim==(digest,),"CAPITAL_SELECTION_CLAIM_REQUIRED")
                value=dict(intent_sha256=digest,decision=deepcopy(decision),profile=deepcopy(profile),
                    account_state=deepcopy(account_state),previous_target=deepcopy(previous_target),
                    source_files={k:base64.b64encode(v).decode("ascii") for k,v in source_files.items()})
                self._validate_prepared(intent,value)
                raw=canonical(value);require(len(raw)<=48*1024*1024,"CAPITAL_PREPARED_BUDGET")
                old=self._prepared(con,event_id)
                require(old is None or old==value,"CAPITAL_PREPARED_CONFLICT")
                if old is None:con.execute("INSERT INTO prepared VALUES(?,?,?)",(event_id,sha256(raw).hexdigest(),raw.decode()))
                con.commit()
                return dict(status="PREPARED_PUBLISH_ONLY",prepared_sha256=sha256(raw).hexdigest(),may_start_selection=False)
            except BaseException:
                con.rollback()
                raise

    def publication_candidate(self,event_id,*,account_state,previous_target):
        """Return only the sealed candidate for publication, with fresh snapshot CAS."""
        with closing(self._connect()) as con:
            intent=self._read(con,event_id);require(intent is not None,"CAPITAL_INTENT_REQUIRED")
            value=self._prepared(con,event_id);require(value is not None,"CAPITAL_PREPARED_CANDIDATE_REQUIRED")
            self._validate_prepared(intent,value)
            self._validate(intent,account_state,previous_target)
            digest=sha256(canonical(intent)).hexdigest()
            require(con.execute("SELECT intent_sha256 FROM claims WHERE event_id=?",(event_id,)).fetchone()==(digest,),
                    "CAPITAL_SELECTION_CLAIM_REQUIRED")
            return dict(decision=deepcopy(value["decision"]),profile=deepcopy(value["profile"]),may_start_selection=False,
                request=dict(event_id="capital:"+digest,reason="EXPLICIT_RECONFIGURE",
                    expected_revision=intent["account_revision"],previous_target_id=intent["previous_target_id"],
                    capital_event_id=event_id,capital_intent_sha256=digest,
                    capital_prepared_sha256=sha256(canonical(value)).hexdigest()))
