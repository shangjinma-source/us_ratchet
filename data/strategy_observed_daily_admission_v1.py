"""Optional generation audit around admission; never reconstructs historical advice."""
import sqlite3
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4
from core.strategy_account_difference import require, timestamp
from data.strategy_daily_advice_journal_v1 import encoded


class ObservedDailyAdmission:
    def __init__(self, *, service, monthly, journal, clock, validate_sources, policy_references):
        self.service,self.monthly,self.journal,self.clock=service,monthly,journal,clock
        self.validate_sources=validate_sources
        self.policy_references=deepcopy(policy_references)

    def preview(self, *, expected_revision, target_id):
        started=self.clock()
        self.validate_sources()
        state=deepcopy(self.monthly.accounts.read())
        target=deepcopy(self.monthly.current())
        require(state['revision']==expected_revision and target['target_id']==target_id,'STALE_SNAPSHOT')
        response=deepcopy(self.service.preview(expected_revision=expected_revision,target_id=target_id))
        generated=self.clock()
        require(started<=generated,'CLOCK_MOVED_BACKWARDS')
        require(response.get('status') in {'READY','HOLD','WAIT'},'ADVICE_STATUS_INVALID')
        require(response.get('account_revision')==expected_revision and response.get('target_id')==target_id,'ADVICE_BINDING_MISMATCH')
        event=dict(schema='DAILY_GENERATED_ADVICE_V1',event_id=uuid4().hex,
            account_id=state['account_id'],account_revision=expected_revision,target_id=target_id,
            target_month=target['payload'].get('target_month'),started_at=started.isoformat(),
            generated_at=generated.isoformat(),response=response,response_sha256=sha256(encoded(response)).hexdigest(),
            policy_references=deepcopy(self.policy_references),displayed=False,evidence_complete=False,
            followup_status='NOT_ADMITTED')
        saved=False
        try:
            self.journal.append(event,now=generated)
            saved=True
        except (ValueError,OSError,RuntimeError,sqlite3.Error):
            pass
        def final_result():
            result=deepcopy(response)
            reason=None
            try:
                self.validate_sources()
                require(self.monthly.accounts.read()==state and self.monthly.current()==target,'SNAPSHOT_CHANGED')
                now=self.clock()
                require(now>=generated,'CLOCK_MOVED_BACKWARDS')
                if result['status']=='READY':
                    for order in result.get('new_orders',[]):
                        quote=result.get('reference_quotes',{}).get(order['security_id'],{})
                        require(timestamp(quote['observed_at'])<=generated,'FUTURE_QUOTE')
                        require(now<timestamp(quote['reference_valid_until']),'ADVICE_EXPIRED')
            except (ValueError,KeyError,OSError):
                reason='ADVICE_INVALIDATED_AFTER_GENERATION'
            if reason:
                result.update(status='WAIT',reason=reason,new_orders=[],reference_quotes={})
            return result
        result=final_result()
        if saved:
            try:
                self.journal.record_return(event['event_id'],dict(status=result['status'],checked_at=self.clock().isoformat()))
                checked=final_result()
                if checked['status']!=result['status']:
                    result=checked
                    self.journal.record_return(event['event_id'],dict(status=result['status'],checked_at=self.clock().isoformat()))
            except (ValueError,OSError,RuntimeError,sqlite3.Error):
                saved=False
                result=final_result()
        result['observation_record']=dict(status='SAVED' if saved else 'UNAVAILABLE',
            event_id=event['event_id'] if saved else None,displayed=False,evidence_complete=False)
        return result
