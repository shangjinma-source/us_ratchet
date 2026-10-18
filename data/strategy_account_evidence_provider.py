"""Server-owned assembly of pinned training, current marks and action evidence.

Construction is read-only. Explicit invocation captures quotes, never changes an
account or selects a portfolio. The caller supplies reviewed deployment pins.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical
from data.current_quantity_v2_monthly_training import compile_saved_training
from data.current_research_capital_decision_v2 import REQUIRED_PINS
from data.strategy_account_target_inputs import require, stamp, build_target_inputs
from data.strategy_account_unit_review import review_interval
from data.strategy_account_mark_reference import decode_current_mark as decode_intraday_reference
from fractions import Fraction


class StrategyAccountEvidenceProvider:
    def __init__(self, *, root, manifest_path, manifest_sha256, training_closed_at,
                 market_capture, action_capture, limits_builder, output_root, runtime_pins=None, clock=None):
        self.root = Path(root).resolve()
        self.manifest_path, self.manifest_hash = manifest_path, manifest_sha256
        self.closed = training_closed_at
        self.market, self.actions, self.limits = market_capture, action_capture, limits_builder
        self.output = Path(output_root)
        self.clock = clock or (lambda:datetime.now(timezone.utc))
        require(type(runtime_pins) is dict and set(REQUIRED_PINS) <= set(runtime_pins),
                'SELECTION_RUNTIME_PINS_REQUIRED')
        self.runtime_pins = {path: runtime_pins[path] for path in REQUIRED_PINS}
        require(all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value)
                    for value in self.runtime_pins.values()), 'SELECTION_RUNTIME_HASH_REQUIRED')

    def _read(self, path, expected):
        require(type(path) is str and '\\' not in path and ':' not in path
                and not PurePosixPath(path).is_absolute()
                and all(part not in ('', '.', '..') for part in path.split('/')), 'UNSAFE_TRAINING_PATH')
        source = self.root/path
        require(not any(p.is_symlink() for p in [source, *source.parents]), 'TRAINING_SYMLINK_REFUSED')
        require(source.is_file() and source.stat().st_size <= 32*1024*1024, 'TRAINING_SOURCE_MISSING_OR_TOO_LARGE')
        raw = source.read_bytes()
        require(sha256(raw).hexdigest() == expected, 'TRAINING_SOURCE_CHANGED')
        return raw

    def training(self):
        raw = self._read(self.manifest_path, self.manifest_hash)
        manifest = json.loads(raw)
        pins = dict(manifest['source_hashes'])
        # Saved training manifests describe their own inputs. Selection also needs
        # the separately reviewed executing V2 sources; never self-sign them or
        # rewrite the sealed manifest to manufacture these deployment approvals.
        for path, expected in self.runtime_pins.items():
            require(path not in pins or pins[path] == expected, 'SELECTION_RUNTIME_PIN_CONFLICT')
            pins[path] = expected
        require(len(pins) < 2000, 'TRAINING_SOURCE_DOMAIN_TOO_LARGE')
        files = {}; total = 0
        for path, expected in pins.items():
            value = self._read(path, expected); total += len(value)
            require(total <= 128*1024*1024, 'TRAINING_SOURCE_BUDGET')
            files[path] = value
        require(self.manifest_path not in pins or pins[self.manifest_path] == self.manifest_hash,
                'TRAINING_MANIFEST_CONFLICT')
        files[self.manifest_path] = raw; pins[self.manifest_path] = self.manifest_hash
        package = dict(files=files, source_hashes=pins, documents={'training_manifest':self.manifest_path})
        compiled = compile_saved_training(package, self.manifest_path)
        args = compiled['input']['search_arguments']
        require(stamp(self.closed).astimezone(ZoneInfo('America/New_York')).date().isoformat()
                == args['decision_date'], 'TRAINING_CLOSE_DATE_MISMATCH')
        return package, args

    def __call__(self, state):
        package, historical = self.training()
        return self._assemble(state,package,historical)

    def selection(self, state):
        """Validate selection evidence without evaluating any entry-limit rule."""
        package, historical = self.training()
        return self._assemble(state, package, historical, selection_only=True)

    def valuation(self, state):
        """Review held-share marks without cash approval, selection or limit writes."""
        from core.strategy_account_ledger import replay
        require(replay(state['account_id'],[r['payload'] for r in state['events']])==state,'ACCOUNT_REPLAY_MISMATCH')
        if not any(state['shares'].values()):return {}
        package,historical=self.training()
        result=self._assemble(state,package,historical,target_quantities={},execution_only=True,valuation_only=True)
        return {sid:mark for sid,mark in result.items() if state['shares'].get(sid,0)}

    def execution(self,state,target,now=None):
        # now is interface compatibility only: all operative timestamps are server-clock reads.
        decision=target['payload']['decision'];payload=decision['payload'];binding=payload['input_binding']
        require(decision['decision_id']==sha256(canonical(payload)).hexdigest()
                and payload['input_id']==sha256(canonical(binding)).hexdigest(),'FROZEN_TARGET_CHANGED')
        require(binding['account_id']==state['account_id'],'TARGET_ACCOUNT_MISMATCH')
        require(binding['documents']['training_manifest']==self.manifest_path
                and binding['source_hashes'].get(self.manifest_path)==self.manifest_hash,'TARGET_TRAINING_BINDING_MISMATCH')
        raw=self._read(self.manifest_path,self.manifest_hash);manifest=json.loads(raw)
        historical=deepcopy(binding['historical_search_arguments'])
        require(manifest['decision_date']==historical['decision_date']==binding['training_cutoff_date']
                ==stamp(self.closed).astimezone(ZoneInfo('America/New_York')).date().isoformat(),'TARGET_TRAINING_DATE_MISMATCH')
        quantities=payload['target_quantities']
        require(decision['status']=='TARGET_READY' and type(quantities)is dict
                and set(quantities)<=set(historical['metadata']) and all(type(q)is int and q>0 for q in quantities.values()),'INVALID_FROZEN_TARGET')
        needed=set(quantities)|{sid for sid,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
        from core.strategy_account_ledger import replay
        require(replay(state['account_id'],[r['payload'] for r in state['events']])==state,'ACCOUNT_REPLAY_MISMATCH')
        require(state['cash_confirmation_valid'] and state['execution_ready'],'CASH_RECONFIRMATION_REQUIRED')
        if not needed:
            stamp(self.clock().isoformat())
            return dict(marks={},limits={})
        package=dict(files={self.manifest_path:raw},source_hashes={self.manifest_path:self.manifest_hash},documents={})
        return self._assemble(state,package,historical,target_quantities=quantities,execution_only=True)

    def _assemble(self,state,package,historical,*,target_quantities=None,execution_only=False,selection_only=False,valuation_only=False):
        maximum_age = 900 if selection_only else 120
        begun = stamp(self.clock().isoformat())
        require(stamp(self.closed) <= begun, 'TRAINING_NOT_CLOSED')
        directory = self.output/uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        def save(name, value):
            with (directory/name).open('xb') as stream: stream.write(canonical(value))
        save('started.json', dict(account_id=state['account_id'], revision=state['revision'],
             started_at=begun.isoformat(), training_manifest_sha256=self.manifest_hash))
        try:
            market = self.market.capture(state=deepcopy(state), candidate_metadata=({sid:historical['metadata'][sid] for sid in target_quantities} if execution_only else historical['metadata']),
                                         output_directory=directory/'market')
            marks = market['marks']; marks_raw = canonical(marks)
            needed=(set(target_quantities) if execution_only else set(historical['metadata']))|{s for s,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN'}
            require(set(marks)==needed and market.get('account_id')==state['account_id'] and market.get('account_revision')==state['revision'],'MARKET_ACCOUNT_OR_DOMAIN_MISMATCH')
            quote_now=stamp(self.clock().isoformat())
            quote_records=[]
            for sid,mark in marks.items():
                refs=mark['source_hashes'];require(set(refs)==set(mark['source_references']),'MARK_SOURCE_BINDING')
                receipts=[]
                for path,h in refs.items():
                    require(path in market['files'] and market['source_hashes'].get(path)==h and sha256(market['files'][path]).hexdigest()==h,'MARK_SOURCE_CHANGED')
                    try:value=json.loads(market['files'][path])
                    except (ValueError,UnicodeError):continue
                    if type(value)is dict and 'raw_path' in value:receipts.append(value)
                require(len(receipts)==1,'MARK_RECEIPT_REQUIRED');receipt=receipts[0]
                require(receipt['security_id']==sid and receipt['ticker']==mark['ticker'] and receipt['captured_at']==mark['captured_at'] and refs.get(receipt['raw_path'])==receipt['raw_sha256'],'MARK_RECEIPT_MISMATCH')
                decoded=decode_intraday_reference(market['files'][receipt['raw_path']],ticker=mark['ticker'],captured_at=stamp(mark['captured_at']),now=quote_now,maximum_age_seconds=maximum_age)
                require(Fraction(decoded['last_price'])==Fraction(mark['price']) and stamp(decoded['last_at'])==stamp(mark['observed_at']),'MARK_RAW_VALUE_MISMATCH')
                quote_records.append((market['files'][receipt['raw_path']],mark))
            floor = stamp(self.closed)
            for row in state['events']:
                if row['payload'].get('executed_at'):
                    floor = min(floor, stamp(row['payload']['executed_at']))
            request = dict(account_id=state['account_id'], state_revision=state['revision'],
                window_start=floor.isoformat(), observed_floor=max(max(stamp(m['captured_at']),stamp(m['observed_at'])) for m in marks.values()).isoformat(),
                securities={sid:{'ticker':m['ticker']} for sid,m in marks.items()}, current_target_quantities={})
            actions = self.actions.capture(request, output_directory=directory/'actions')
            now = stamp(self.clock().isoformat())
            review = review_interval(state=state, securities=request['securities'], marks=marks, action_package=actions,
                training_manifest_sha256=self.manifest_hash,
                historical_search_arguments_sha256=sha256(canonical(historical)).hexdigest(),
                historical_price_basis=historical['price_basis'], training_closed_at=self.closed,
                marks_sha256=sha256(marks_raw).hexdigest(), now=now.isoformat())
            execution = None if selection_only or valuation_only else self.limits(state=deepcopy(state), target_quantities=target_quantities,
                                    quote_domain=None if execution_only else set(marks),
                                    market_capture=market, unit_review=review, now=now.isoformat())
            for source in (market, actions):
                require(set(source['files']) == set(source['source_hashes']), 'PROVIDER_SOURCE_DOMAIN')
                for path, value in source['files'].items():
                    expected = source['source_hashes'][path]
                    require(sha256(value).hexdigest() == expected, 'PROVIDER_SOURCE_CHANGED')
                    require(path not in package['files'] or package['files'][path] == value, 'PROVIDER_SOURCE_CONFLICT')
                    package['files'][path] = value; package['source_hashes'][path] = expected
            documents = {}
            for label, value in (('marks', marks), ('unit_review', review)):
                raw = canonical(value); path = 'strategy-evidence/'+sha256(raw).hexdigest()+'.json'
                package['files'][path] = raw; package['source_hashes'][path] = sha256(raw).hexdigest()
                documents[label] = path; save(label+'.json', value)
            require(len(package['files']) <= 2000 and sum(map(len, package['files'].values())) <= 128*1024*1024,
                    'COMBINED_SOURCE_BUDGET')
            finished = stamp(self.clock().isoformat())
            require(finished >= now >= begun, 'SERVER_CLOCK_ROLLBACK')
            for raw,mark in quote_records:
                ref=decode_intraday_reference(raw,ticker=mark['ticker'],captured_at=stamp(mark['captured_at']),now=finished,maximum_age_seconds=maximum_age)
                require(finished<stamp(ref['refresh_by']),'FINAL_MARK_EXPIRED')
            if not execution_only:build_target_inputs(state=state,source_package=package,manifest_path=self.manifest_path,
                marks_path=documents['marks'],unit_review_path=documents['unit_review'],now=finished.isoformat(),maximum_mark_age_seconds=maximum_age)
            if not selection_only and not valuation_only:
                require(type(execution)is dict and type(execution.get('limits'))is dict and set(execution['limits'])==set(marks),'LIMIT_DOMAIN_MISMATCH')
                for sid,limit in execution['limits'].items():
                    require(limit['security_id']==sid and limit['price_basis']==marks[sid]['price_basis'] and limit['observed_at']==marks[sid]['observed_at'] and Fraction(limit['buy'])>0 and Fraction(limit['sell'])>0,'LIMIT_MARK_BINDING_MISMATCH')
            save('complete.json', dict(status='EVIDENCE_ASSEMBLED_NOT_EXECUTED', finished_at=finished.isoformat(),
                documents=documents, source_hashes=package['source_hashes'], account_mutated=False))
            if valuation_only:return deepcopy(marks)
            if execution_only:return dict(marks=deepcopy(marks),limits=deepcopy(execution['limits']))
            result = dict(source_package=package, manifest_path=self.manifest_path,
                marks_path=documents['marks'], unit_review_path=documents['unit_review'])
            if not selection_only: result['limits'] = execution['limits']
            return result
        except Exception as error:
            reason = str(error) if isinstance(error, ValueError) and str(error).replace('_','').isalnum() else 'EVIDENCE_UNAVAILABLE'
            save('failed.json', dict(status='BLOCKED', reason=reason, account_mutated=False))
            raise
