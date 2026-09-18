from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from .request_queue import scheduler
from .security import administrator,current_user

router=APIRouter(prefix='/api/queue')

@router.get('')
def queue(user=Depends(current_user)):
    return scheduler.snapshot(None if user['role']=='admin' else user['id'])

class Pause(BaseModel):
    paused: bool

@router.post('/pause')
def pause(body: Pause,user=Depends(administrator)):
    with scheduler.lock:
        scheduler.paused=body.paused
    return scheduler.snapshot()

@router.post('/cancel')
def cancel(body: dict,user=Depends(current_user)):
    key=body.get('key')
    if not isinstance(key,str) or len(key)>100:
        raise HTTPException(400,'Invalid request key.')
    return {'cancelled':scheduler.cancel(key,None if user['role']=='admin' else user['id'])}
