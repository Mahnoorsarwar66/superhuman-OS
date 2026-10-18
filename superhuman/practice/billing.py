"""Attribution only; existing atomic budget guard remains authoritative."""
from contextvars import ContextVar
from contextlib import contextmanager
project=ContextVar('practice_billing_project',default=None)
@contextmanager
def scope(pid,mid):
 token=project.set((pid,mid))
 try:yield
 finally:project.reset(token)
def link(db,ident):
 from superhuman.departments.store import tables
 value=project.get()
 if value and 'practice_cost_links' in tables(db):db.execute('INSERT INTO practice_cost_links VALUES(?,?,?)',(ident,*value))
