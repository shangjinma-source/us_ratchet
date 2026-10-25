"""Validate the supported execution subsets without changing saved advice."""
from core.strategy_account_ledger import require


def validate_execution_shape(binding, response):
    schema=binding.get('schema')
    if schema=='DAILY_EXECUTION_PROJECTION_V1':return
    require(schema=='DAILY_BUY_DATA_WAIT_SELL_EXECUTION_V1','BINDING_SCHEMA')
    require(binding.get('projection_semantics')==response.get('projection_semantics')==
            'EXECUTION_SUBSET_NOT_STRATEGY_TARGET','FOLLOWUP_SUBSET_SEMANTICS')
    effective=binding['effective_target_quantities'];execution=binding['execution_quantities']
    require(effective==response['effective_target_quantities'] and
            execution==response['execution_quantities'],'FOLLOWUP_SUBSET_TARGET_CHANGED')
    rows=response['daily_gate']['rows']
    held={r['security_id']:r['held'] for r in rows}
    require(len(held)==len(rows) and set(held)==set(effective)==set(execution),'FOLLOWUP_SUBSET_DOMAIN')
    require(all(type(q)is int and q>=0 for q in list(held.values())+list(effective.values())+list(execution.values())),
            'FOLLOWUP_SUBSET_QUANTITY')
    require(execution=={sid:min(held[sid],q) for sid,q in effective.items()},'FOLLOWUP_SELL_ONLY_PROJECTION')
    waiting={sid:q-held[sid] for sid,q in effective.items() if q>held[sid]}
    require(binding['waiting_buys']==waiting,'FOLLOWUP_WAITING_BUYS_CHANGED')
    wait_rows=response.get('waiting_data',[])
    require(len(wait_rows)==len(waiting) and
            {r['security_id']:r['quantity'] for r in wait_rows}==waiting and
            all(r['reason']=='WAIT_BUY_MINUTE_DATA' for r in wait_rows),'FOLLOWUP_WAITING_DATA_CHANGED')
    seen=set()
    for order in response['new_orders']:
        sid=order['security_id'];quantity=order['quantity']
        require(sid in held and sid not in seen and order['side']=='SELL' and
                type(quantity)is int and 0<quantity<=held[sid]-execution[sid],
                'FOLLOWUP_SUBSET_ORDER_INVALID')
        seen.add(sid)
