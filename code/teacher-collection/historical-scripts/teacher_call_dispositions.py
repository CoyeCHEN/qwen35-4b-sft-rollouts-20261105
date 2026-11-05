"""Separate observed Assistant targets from recovered empty transport placeholders.

Raw attempts remain in Recorder and the cost ledger. Only an explicit native
retry chain reaching a normal observed response can exempt an empty error call
from the Assistant target set. Partial generations are never silently omitted.
"""


def _has_observed_content(call):
    response=call.get('native_response') or {}
    if response.get('content'):return True
    for chunk in call.get('chunks',[]):
        for choice in chunk.get('choices',[]):
            delta=choice.get('delta') or {}
            if any(delta.get(k) for k in ['content','reasoning','reasoning_content','tool_calls']):return True
    return False


def dispositions(calls):
    values=list(calls);by_id={c['call_id']:c for c in values}
    if len(by_id)!=len(values):raise ValueError('Duplicate model call identity')
    children={}
    for call in values:
        parent=call.get('retry_of')
        if parent:
            if parent not in by_id or by_id[parent]['source']!=call['source']:
                raise ValueError('Native retry link does not refer to the same source')
            children.setdefault(parent,[]).append(call['call_id'])
    result=[]
    for call in values:
        response=call.get('native_response') or {}
        empty_failure=(call.get('status') in ('error','aborted') and
            response.get('stopReason') in (None,'error','aborted') and not _has_observed_content(call))
        recovered=None
        if empty_failure:
            ident=call['call_id'];seen=set()
            while ident in children:
                if ident in seen:raise ValueError('Cyclic native retry links')
                seen.add(ident);next_ids=children[ident]
                if len(next_ids)!=1:raise ValueError('Ambiguous native retry chain')
                ident=next_ids[0];following=by_id[ident]
                if (following.get('native_response') or {}).get('stopReason') in ('stop','toolUse'):
                    recovered=ident;break
        result.append(dict(call_id=call['call_id'],source=call['source'],retry_of=call.get('retry_of'),
            stop_reason=response.get('stopReason'),status=call.get('status'),observed_assistant_content=_has_observed_content(call),
            disposition='RECOVERED_EMPTY_TRANSPORT_CALL_NO_ASSISTANT_TARGET' if recovered else
                'UNRECOVERED_EMPTY_CALL' if empty_failure else 'ASSISTANT_TARGET' if call['source']=='agent' else 'AUXILIARY_MODEL_CALL',
            recovered_by_call_id=recovered))
    return result
