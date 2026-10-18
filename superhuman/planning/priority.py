"""Transparent, deterministic ordering; suggestions never execute tasks."""
from . import store
from superhuman.knowledge.store import today

RANK={'critical':0,'high':1,'normal':2,'low':3,'unset':4}

def edit_url(scope,kind='',ident=''):
    from urllib.parse import quote
    base='/department-plans/'+quote(scope,safe='')
    return base+('/'+kind+'/'+quote(ident,safe='') if kind else '')

def actions(scope,plan=None):
    from superhuman.repairs.actions import actions as repaired
    return repaired(scope,plan)

def all_departments():
    from superhuman.departments.store import departments
    return [(scope,name,store.snapshot(scope)) for scope,name in departments()]

def queue():
    from superhuman.repairs.actions import queue as repaired
    return repaired()

def next_step(scope,fallback):
    from superhuman.repairs.actions import next_step as repaired
    return repaired(scope,fallback)
