"""Reuse the original community service backend, add an authenticated flight workbench."""
from fastapi import Depends,HTTPException
from fastapi.responses import FileResponse,Response
from pydantic import BaseModel,Field
import json,asyncio
from backend.app import app,admin,user
from backend import store
from autonomy.client import rpc
from autonomy.models import SCENARIOS
from autonomy.engine import ROOT

app.title='晴空邻里 · 自主飞行与未来城市共享服务'
app.version='2.1.0'

class FlightCommand(BaseModel):
    command:str=Field(min_length=1,max_length=40)
    data:dict=Field(default_factory=dict)

@app.get('/community')
def community():return FileResponse(ROOT/'frontend/community.html')

@app.get('/api/autonomy/state')
async def flight_state(u=Depends(admin)):
    try:return await asyncio.to_thread(rpc,'/state')
    except Exception as e:raise HTTPException(503,str(e))

@app.get('/api/autonomy/scenarios')
def scenarios(u=Depends(admin)):return SCENARIOS

@app.post('/api/autonomy/command')
async def flight_command(body:FlightCommand,u=Depends(admin)):
    if body.command in ('confirm_real','jog','upload'):raise HTTPException(403,'该操作仅在本机独立桌面软件提供')
    try:
        data=dict(body.data)
        if body.command=='load' and data.get('order_id'):
            state=store.read_state();order=next((o for o in state['orders'] if o['id']==data['order_id']),None)
            if not order:raise ValueError('订单不存在')
            # Separate small flight test field; never interpret community metres as geodetic coordinates.
            data['goal']=[10+order['x']/1000*75,10+order['y']/700*55,12.]
            data['scenario']='neighborhood'
        return await asyncio.to_thread(rpc,'/command',{'command':body.command,'data':data,'owner':'web'},8)
    except Exception as e:raise HTTPException(409,str(e))

@app.get('/api/autonomy/export')
async def export(u=Depends(admin)):
    try:r=await asyncio.to_thread(rpc,'/state')
    except Exception as e:raise HTTPException(503,str(e))
    return Response(json.dumps(r,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="sky-flight-report.json"'})

@app.get('/api/autonomy/technical-sources')
def technical_sources(u=Depends(admin)):
    p=ROOT/'docs/技术来源与实现对照.json';return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []

@app.get('/api/autonomy/reports')
def reports(u=Depends(admin)):
    result=[]
    for p in sorted((ROOT/'reports').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        if p.stat().st_size<3_000_000:
            try:result.append({'file':p.name,'data':json.loads(p.read_text(encoding='utf-8'))})
            except ValueError:pass
    return result[:50]
