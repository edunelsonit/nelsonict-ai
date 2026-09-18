"""Bounded FIFO admission shared by chat, evaluation and public requests."""
import threading
import time
from dataclasses import dataclass, field
from .inference import runtime
from .config import settings


@dataclass
class Ticket:
    key: str
    user_id: int
    kind: str
    stop: threading.Event = field(default_factory=threading.Event)
    created: float = field(default_factory=time.monotonic)
    running: bool = False


class RequestQueue:
    def __init__(self):
        self.lock = threading.RLock()
        self.items = []
        self.paused = False

    def submit(self, key, user_id, kind='chat'):
        with self.lock:
            if self.paused:
                raise RuntimeError('Queue is paused by an administrator.')
            if runtime.model is None:
                raise RuntimeError('No model is loaded. Ask an administrator to load a GGUF model.')
            if any(t.key == key for t in self.items):
                raise RuntimeError('This request already has a response waiting or running.')
            if len(self.items) >= settings.queue_limit:
                raise RuntimeError('Request queue is full. Please try again later.')
            if sum(t.user_id == user_id for t in self.items) >= settings.queue_per_user:
                raise RuntimeError('Your request limit is reached. Finish or cancel an earlier request.')
            ticket = Ticket(key, user_id, kind)
            self.items.append(ticket)
            return ticket

    def wait(self, ticket, progress=lambda _: None):
        last = None
        while True:
            with self.lock:
                if ticket.stop.is_set() or ticket not in self.items:
                    raise RuntimeError('Request cancelled.')
                if time.monotonic() - ticket.created > settings.queue_timeout:
                    raise RuntimeError('Queue waiting time limit reached.')
                position = self.items.index(ticket)
                if position == 0 and not self.paused:
                    try:
                        runtime.reserve(ticket.key, ticket.user_id)
                    except RuntimeError:
                        if runtime.model is None and not runtime.loading:
                            raise RuntimeError('Model was unloaded while waiting.')
                    else:
                        runtime.active[ticket.key] = (ticket.user_id, ticket.stop)
                        ticket.running = True
                        return
                position += 1
            if position != last:
                progress({'type':'queue','position':position,'message':f'Waiting in queue · position {position}'})
                last = position
            ticket.stop.wait(0.2)

    def finish(self, ticket):
        with self.lock:
            if ticket.running:
                runtime.release(ticket.key)
                ticket.running = False
            if ticket in self.items:
                self.items.remove(ticket)

    def cancel(self, key, user_id=None):
        with self.lock:
            for t in list(self.items):
                if t.key == key and (user_id is None or t.user_id == user_id):
                    t.stop.set()
                    if not t.running:
                        self.items.remove(t)
                    return True
        return False

    def cancel_user(self, user_id):
        with self.lock:
            for t in list(self.items):
                if t.user_id == user_id:
                    self.cancel(t.key, user_id)

    def snapshot(self, user_id=None):
        with self.lock:
            return {'paused':self.paused,'requests':[
                {'key':t.key,'user_id':t.user_id,'kind':t.kind,
                 'position':0 if t.running else i+1,'status':'running' if t.running else 'waiting'}
                for i,t in enumerate(self.items) if user_id is None or t.user_id == user_id]}


scheduler = RequestQueue()
