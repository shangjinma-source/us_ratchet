"""Explicit source composition for run_daily, with create-only review archives.

Construction performs no IO. Only capture callbacks may use the configured
transports. No fee, account, unit review or source-admission defaults are inferred.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json

from backtest.current_quantity_v2_close_capture_simulation import prepare_close_captures, _read
from backtest.current_quantity_v2_monthly_simulation import digest
from backtest.current_quantity_v2_simulated_settlement import _references
from data.current_quantity_v2_completed_session_minutes import fetch_bytes
from data.current_quantity_v2_difference_plan import require, stamp
from data.current_quantity_v2_late_unit_review import BoundedLateUnitReview, replay


def _write(root, name, value):
    # Use the bounded path reader's validation rules before making new parents.
    from pathlib import PurePosixPath
    require(type(name) is str and '\\' not in name and ':' not in name
            and not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts,
            'INVALID_REVIEW_ARCHIVE_PATH')
    path=root/name
    require(path.resolve().is_relative_to(root) and not path.is_symlink()
            and not any(parent.is_symlink() for parent in path.parents), 'INVALID_REVIEW_ARCHIVE_PATH')
    raw=value if type(value) is bytes else json.dumps(value,sort_keys=True).encode()
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():require(_read(root,name)==raw, 'REVIEW_ARCHIVE_FILE_CONFLICT')
    else:
        with path.open('xb') as stream:stream.write(raw)


class DailyEvidenceProviders:
    def __init__(self, *, store, root, schedule_path, schedule_sha256, evidence_directory,
                 fee_provider, origin_files_reader, clock, minute_fetch=fetch_bytes, late_review=None):
        self.store=store;self.root=Path(root).resolve();self.schedule_path=schedule_path
        self.schedule_sha256=schedule_sha256;self.directory=Path(evidence_directory).resolve()
        self.fee_provider=fee_provider;self.origin_files_reader=origin_files_reader;self.clock=clock
        self.minute_fetch=minute_fetch;self.late_review=late_review or BoundedLateUnitReview(clock=clock)

    def _directory(self, simulation, day, purpose):
        return self.directory/digest([simulation['simulation_id'],day])/purpose

    def capture_arguments(self, simulation, day):
        schedule=json.loads(_read(self.root,self.schedule_path,{self.schedule_path:self.schedule_sha256}))
        require(schedule['schema']=='SCHEDULED_REGULAR_SESSIONS_V1', 'SIMULATION_SCHEDULE_SCHEMA')
        rows=[row for row in schedule['sessions'] if row['date']==day]
        require(len(rows)==1 and stamp(rows[0]['close_at'])==stamp(
            simulation['valuation']['registration']['calendar']['closes'][day]), 'REGISTERED_CLOSE_MISMATCH')
        refs=_references(simulation['chain'])
        require(all(stamp(refs[o['security_id']]['session_open'])==stamp(rows[0]['open_at'])
                    and stamp(o['session_close'])==stamp(rows[0]['close_at'])
                    for o in simulation['chain']['ledger']['orders'].values()), 'ORDER_CALENDAR_MISMATCH')
        return dict(fees=self.fee_provider(deepcopy(simulation),day),
            calendar_source_reference='sha256:'+self.schedule_sha256,
            directory=self._directory(simulation,day,'settlement'),fetch=self.minute_fetch)

    def _reviews(self, simulation, root, captures, pins, reuse=None):
        try:
            return self._reviews_impl(simulation,root,captures,pins,reuse)
        except Exception as error:
            if ((root/'bounded-review-request.json').is_file()
                    and not (root/'bounded-review-ready.json').exists()
                    and not (root/'bounded-review-failure.json').exists()):
                reason=str(error) if str(error) in ('LATE_UNIT_CHANGE_CANDIDATE','LATE_UNIT_REVIEW_UNAVAILABLE') else 'REVIEW_CAPTURE_OR_ARCHIVE_FAILED'
                try:failed_at=stamp(self.clock()).isoformat()
                except Exception:failed_at=None
                _write(root,'bounded-review-failure.json',dict(reason=reason,error_type=type(error).__name__,
                    failed_at=failed_at,failed_action_raw_archived=False,automatic_retry_allowed=False))
            raise

    def _reviews_impl(self, simulation, root, captures, pins, reuse=None):
        refs=_references(simulation['chain']);ledger=simulation['chain']['ledger']
        items={}
        for sid,paths in captures.items():
            raw=_read(root,paths['raw'],pins);receipt=json.loads(_read(root,paths['receipt'],pins))
            require(sha256(raw).hexdigest()==receipt['raw_sha256'], 'REVIEW_CAPTURE_CHANGED')
            items[sid]=dict(reference_sha256=digest(refs[sid]),capture_sha256=sha256(raw).hexdigest(),
                            captured_at=receipt['captured_at'])
        request=dict(kind='ISOLATED_BOUNDED_REVIEW_ARCHIVE_V1',simulation_id=simulation['simulation_id'],
                     account_id=ledger['account_id'],state_revision=ledger['revision'],items=items)
        request_name='bounded-review-request.json';ready_name='bounded-review-ready.json'
        if (root/request_name).exists():
            require(json.loads(_read(root,request_name))==request, 'REVIEW_ARCHIVE_REQUEST_CONFLICT')
            require((root/ready_name).is_file(), 'REVIEW_ARCHIVE_INCOMPLETE_NO_RETRY')
            result=json.loads(_read(root,ready_name))
            require(result['request_sha256']==digest(request) and set(result['unit_reviews'])==set(items), 'REVIEW_ARCHIVE_CHANGED')
        else:
            _write(root,request_name,request)
            result=dict(request_sha256=digest(request),unit_reviews={},source_hashes={})
            for sid,paths in captures.items():
                ref=refs[sid];raw=_read(root,paths['raw'],pins);item=items[sid]
                reused=(reuse or {}).get(sid)
                if reused is not None:
                    old_root,old_result=reused
                    review_path=old_result['unit_reviews'][sid]
                    review=json.loads(_read(old_root,review_path,old_result['source_hashes']))
                    require(review['reference_sha256']==item['reference_sha256']
                            and review['capture_raw_sha256']==item['capture_sha256'], 'REVIEW_REUSE_BINDING_CHANGED')
                    package=dict(review_path=review_path,files={p:_read(old_root,p,old_result['source_hashes'])
                        for p in [*review['source_references'],review_path]})
                    package['source_hashes']={p:sha256(v).hexdigest() for p,v in package['files'].items()}
                else:
                    package=self.late_review.capture(reference=deepcopy(ref),capture_raw=raw,
                        captured_at=item['captured_at'],origin_files=self.origin_files_reader(deepcopy(simulation),deepcopy(ref)),
                        account_id=ledger['account_id'],state_revision=ledger['revision'])
                for path,body in package['files'].items():
                    require(sha256(body).hexdigest()==package['source_hashes'][path], 'REVIEW_PACKAGE_CHANGED')
                    _write(root,path,body)
                result['unit_reviews'][sid]=package['review_path'];result['source_hashes'].update(package['source_hashes'])
            # Validate all evidence before publishing a reusable ready marker.
            self._replay_reviews(root,result,refs,items)
            _write(root,ready_name,result)
        self._replay_reviews(root,result,refs,items)
        return dict(unit_reviews=result['unit_reviews'],source_hashes=result['source_hashes'])

    def _replay_reviews(self,root,result,refs,items):
        observed=stamp(self.clock())
        for sid,path in result['unit_reviews'].items():
            review=json.loads(_read(root,path,result['source_hashes']))
            replay(review,reference=refs[sid],capture_raw_sha256=items[sid]['capture_sha256'],
                captured_at=items[sid]['captured_at'],observed_at=observed,
                read=lambda name:_read(root,name,result['source_hashes']))

    def settlement_review(self, simulation, prepared):
        root=Path(prepared['directory']).resolve();day=prepared['request']['session']
        require(root==self._directory(simulation,day,'settlement'), 'UNEXPECTED_SETTLEMENT_DIRECTORY')
        ready=json.loads(_read(root,'ready.json'))
        require(ready['request_sha256']==digest(prepared['request']), 'SETTLEMENT_BINDING_CHANGED')
        captures={sid:{key:child+'/'+name for key,name in [('raw','response.bin'),('receipt','receipt.json'),('minutes','minutes.json')]}
                  for sid,child in ready['captures'].items()}
        pins={name:sha256(_read(root,name)).hexdigest() for row in captures.values() for name in row.values()}
        return self._reviews(simulation,root,captures,pins)

    def close_arguments(self, simulation, day):
        current=self.store.read(simulation['simulation_id'])
        require(current['simulation']==simulation, 'STALE_SIMULATION_REVISION')
        held={sid for sid,q in simulation['chain']['ledger']['shares'].items() if q}
        old_root=self._directory(simulation,day,'settlement');existing={};pins={};reuse={}
        # Only bytes already consumed by the persisted settlement batch qualify
        # for automatic reuse; a loose filesystem directory is not authority.
        accepted={}
        for batch in simulation['batches']:
            for item in batch['request'].get('evidence',{}).values():
                if item['session']==day:accepted[item['security_id']]=item['source_reference']
        if (old_root/'ready.json').is_file():
            ready=json.loads(_read(old_root,'ready.json'))
            for sid in held.intersection(accepted):
                if sid not in ready['captures']:continue
                child=ready['captures'][sid]
                raw_name=child+'/response.bin';raw=_read(old_root,raw_name)
                require('sha256:'+sha256(raw).hexdigest()==accepted[sid], 'SETTLEMENT_REUSE_BYTES_CHANGED')
                paths={key:(old_root/child/name).relative_to(self.directory).as_posix()
                       for key,name in [('raw','response.bin'),('receipt','receipt.json'),('minutes','minutes.json')]}
                existing[sid]=paths
                pins.update({name:sha256(_read(self.directory,name)).hexdigest() for name in paths.values()})
                if (old_root/'bounded-review-ready.json').is_file():
                    reuse[sid]=(old_root,json.loads(_read(old_root,'bounded-review-ready.json')))
        # The pinned calendar lives under explicit root, while reused captures
        # live in the evidence tree. Copy only that exact pinned calendar there.
        calendar=_read(self.root,self.schedule_path,{self.schedule_path:self.schedule_sha256})
        _write(self.directory,'calendar/'+self.schedule_sha256+'.json',calendar)
        prepared=prepare_close_captures(store=self.store,simulation_id=simulation['simulation_id'],
            expected_revision=current['revision'],session=day,root=self.directory,
            schedule_path='calendar/'+self.schedule_sha256+'.json',schedule_sha256=self.schedule_sha256,
            directory=self._directory(simulation,day,'close'),fetch=self.minute_fetch,clock=self.clock,
            existing_captures=existing,existing_source_hashes=pins)
        if any(value!='COMPLETE_SESSION_MINUTES' for value in prepared['statuses'].values()):
            return dict(status='MISSING_CLOSE_EVIDENCE',reason='INCOMPLETE_SAVED_SESSION_MINUTES')
        root=Path(prepared['root'])
        reviewed=self._reviews(simulation,root,prepared['captures'],prepared['source_hashes'],reuse)
        return dict(root=root,captures=prepared['captures'],unit_reviews=reviewed['unit_reviews'],
                    source_hashes=dict(prepared['source_hashes'],**reviewed['source_hashes']))
