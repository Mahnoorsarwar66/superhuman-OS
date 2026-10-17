"""Typed model action arguments; no JSON encoded inside another JSON string."""
from .tools import REGISTRY

def schema():
    variants=[{'type':'object','properties':{},'required':[],'additionalProperties':False}]
    seen=set()
    for tool in REGISTRY.values():
        properties={k:{'type':{str:'string',int:'integer',bool:'boolean'}[v] if k in tool.required else [{str:'string',int:'integer',bool:'boolean'}[v],'null']} for k,v in tool.fields.items()}
        signature=repr(properties)
        if not properties or signature in seen:continue
        seen.add(signature)
        variants.append({'type':'object','properties':properties,'required':list(properties),'additionalProperties':False})
    properties={'action':{'type':'string','enum':['tool','finish']},'tool':{'type':'string','enum':['']+list(REGISTRY)},
        'arguments':{'anyOf':variants},'rationale':{'type':'string'},'final_message':{'type':'string'},
        'evidence_action_ids':{'type':'array','items':{'type':'string'}}}
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
