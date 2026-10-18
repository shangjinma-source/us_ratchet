"""Append-only single replacement evidence grammar; no IO or evaluation."""
import hashlib
import json


def require(ok, message):
    if not ok: raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(raw): return hashlib.sha256(raw).hexdigest()


def make_record(*, context_sha256, sequence, previous_sha256, global_ordinal, task_id, stage, payload):
    body = dict(schema='SINGLE_REPLACEMENT_JOURNAL_RECORD_V1', context_sha256=context_sha256,
                sequence=sequence, previous_sha256=previous_sha256, global_ordinal=global_ordinal,
                task_id=task_id, stage=stage, payload=payload)
    return dict(body=body, record_sha256=sha(encode(body)))


def inspect_journal(raw, *, context_sha256, ordered_tasks):
    require(type(raw) is bytes, 'Original journal bytes')
    lines = raw.splitlines(keepends=True); tail = bool(lines and not lines[-1].endswith(b'\n'))
    if tail: lines.pop()
    previous = '0'*64; cursor = 0; active = None; terminals = []; records = []; offset = 0
    def unique(pairs):
        d = {}
        for k,v in pairs:
            require(k not in d, 'Duplicate JSON key'); d[k]=v
        return d
    for seq, line in enumerate(lines):
        value = json.loads(line.decode('utf-8'), object_pairs_hook=unique,
                           parse_constant=lambda v: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        require(type(value) is dict and set(value)=={'body','record_sha256'}, 'Journal envelope')
        b=value['body']; require(set(b)=={'schema','context_sha256','sequence','previous_sha256','global_ordinal','task_id','stage','payload'}, 'Journal body')
        require(value['record_sha256']==sha(encode(b)), 'Record hash')
        require(b['schema']=='SINGLE_REPLACEMENT_JOURNAL_RECORD_V1' and b['context_sha256']==context_sha256
                and type(b['sequence']) is int and b['sequence']==seq and b['previous_sha256']==previous, 'Hashchain context/order')
        require(cursor<len(ordered_tasks), 'No record beyond shard')
        task=ordered_tasks[cursor]
        require(type(b['global_ordinal']) is int and b['global_ordinal']==task['global_ordinal'] and b['task_id']==task['task_id'], 'Original task order')
        stage=b['stage']; p=b['payload']
        if stage=='START':
            require(active is None and (not terminals or terminals[-1]['outcome'] in ('FEASIBLE','INFEASIBLE')), 'No retry or post-failure dispatch')
            require(set(p)=={'task','dispatch_may_have_occurred'} and p['dispatch_may_have_occurred'] is True and encode(p['task'])==encode(task), 'Complete original START task')
            active=dict(stage='START', raw=None)
        elif stage in ('RAW_RETURNED','RAW_EXCEPTION'):
            require(active is not None and active['stage']=='START', 'Exactly one raw per START')
            require(p['call_invoked'] is True and type(p['call_count']) is int and p['call_count']==1
                    and p['returned'] is (stage=='RAW_RETURNED'), 'Actual call fact')
            active=dict(stage=stage,raw=p)
        elif stage=='POSTCHECK':
            require(active is not None and active['stage'] in ('RAW_RETURNED','RAW_EXCEPTION'), 'Raw durable before post')
            outcome=p['outcome']; require(outcome in ('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE'), 'Terminal class')
            if active['stage']=='RAW_EXCEPTION': require(outcome=='EVALUATION_EXCEPTION','Exception is not economic failure')
            else: require(outcome!='EVALUATION_EXCEPTION','Returned result cannot be invocation exception')
            if outcome in ('FEASIBLE','INFEASIBLE'):
                r=active['raw']; require(r['result_preserved_as_json'] is True and type(r['result']) is dict
                    and r['result']['status']==outcome and r['result']['feasible'] is (outcome=='FEASIBLE'), 'Accepted result identity')
            terminals.append(dict(global_ordinal=task['global_ordinal'],task_id=task['task_id'],outcome=outcome))
            active=None; cursor+=1
        else: raise ValueError('Unknown journal stage')
        records.append(dict(sequence=seq,byte_start=offset,byte_stop=offset+len(line),record_sha256=value['record_sha256'],stage=stage,global_ordinal=task['global_ordinal']))
        offset+=len(line);previous=value['record_sha256']
    unresolved = ordered_tasks[cursor]['global_ordinal'] if cursor<len(ordered_tasks) and (active is not None or tail) else None
    require(not tail or cursor<len(ordered_tasks), 'Tail beyond completed shard')
    return dict(complete=cursor==len(ordered_tasks) and not tail and active is None,
                terminal_rows=terminals,unresolved_ordinal=unresolved,
                undispatched_ordinals=[t['global_ordinal'] for t in ordered_tasks[cursor+int(unresolved is not None):]],
                records=records,partial_tail_present=tail,journal_sha256=sha(raw),terminal_record_sha256=previous,
                automatic_retry_allowed=False)
