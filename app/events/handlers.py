"""One handler per event type. Handlers mutate state through core services and return Effects.

Handlers for later milestones are registered as they are built; until then the router
answers 501 for those event types.
"""
from app import state
from app.events import schemas as sc
from app.events.router import EventError, UnitOfWork, handles
from app.models import Customer
from app.realtime.trace import trace


@handles("set_language")
def on_set_language(uow: UnitOfWork, p: sc.SetLanguage):
    state.put(uow.s, "lang", p.lang)
    trace("router", f"Language → {p.lang}")


@handles("set_focus_customer")
def on_set_focus_customer(uow: UnitOfWork, p: sc.SetFocusCustomer):
    if uow.s.get(Customer, p.customer_id) is None:
        raise EventError(f"unknown customer {p.customer_id}", 404)
    state.put(uow.s, "focus_customer", p.customer_id)
