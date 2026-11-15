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
app.version='3.0.0'

@app.get('/api/autonomy/evaluation/view')
def evaluation_view(u=Depends(admin)):
    p=ROOT/'reports/evaluation.html'
    if not p.exists():raise HTTPException(404,'尚未生成评测，运行 tools/benchmark.py')
    return FileResponse(p,media_type='text/html')

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
        return await asyncio.to_thread(rpc,'/command',{'command':body.command,'data':data,'owner':'web'},8)
    except Exception as e:raise HTTPException(409,str(e))

@app.get('/api/autonomy/export')
async def export(u=Depends(admin)):
    try:r=await asyncio.to_thread(rpc,'/record')
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

@app.get('/api/autonomy/tasks')
async def flight_tasks(u=Depends(admin)):
    try:return await asyncio.to_thread(rpc,'/command',{'command':'tasks','data':{},'owner':'web'},8)
    except Exception as e:raise HTTPException(503,str(e))

@app.get('/help/{kind}')
def product_help(kind:str):
    names={'manual':'晴空邻里_全界面与按钮使用说明_20261114.html','intro':'晴空邻里_项目介绍_20261114.html'}
    if kind not in names:raise HTTPException(404,'说明页面不存在')
    path=ROOT/'output/产品介绍与操作手册'/names[kind]
    if not path.is_file():raise HTTPException(404,'本副本缺少说明文件，请使用完整交付包')
    return FileResponse(path,media_type='text/html')
