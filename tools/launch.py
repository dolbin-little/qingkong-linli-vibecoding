from pathlib import Path
import subprocess,sys,time,json,urllib.request,os,argparse
ROOT=Path(__file__).resolve().parents[1];PY=ROOT/'runtime/python/python.exe'
def health(url):
    try:
        with urllib.request.urlopen(url,timeout=.4) as r:return json.load(r)
    except Exception:return None
def start(role,args,url=None):
    pfile=ROOT/'data'/('process-'+role+'.json')
    if pfile.exists():
        try:
            record=json.loads(pfile.read_text(encoding='utf-8'))
            if str(ROOT)==record.get('root') and os.name=='nt':
                executable=str(PY).replace("'","''")
                query=subprocess.run(['powershell','-NoProfile','-Command',"$p=Get-CimInstance Win32_Process -Filter 'ProcessId="+str(int(record['pid']))+"'; if($p -and $p.ExecutablePath -eq '"+executable+"'){'owned'}"],capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=0x08000000)
                if (query.stdout or '').strip()=='owned':return
        except (ValueError,OSError,KeyError):pass
    if url and health(url):raise RuntimeError(role+'端口已被其他进程占用；本项目不会停止其他进程')
    log=(ROOT/'logs'/(role+'.log')).open('ab')
    flags=0x08000000 if os.name=='nt' else 0
    env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONUTF8']='1';env['GREENFLIGHT_DB']=str(ROOT/'data/community.db')
    p=subprocess.Popen([str(PY),'-B']+args,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=flags);log.close()
    pfile.write_text(json.dumps({'pid':p.pid,'role':role,'command':args,'root':str(ROOT),'time':time.time()}),encoding='utf-8')
    if url:
        for _ in range(80):
            if health(url):return
            if p.poll() is not None:raise RuntimeError(role+'启动失败，查看logs/'+role+'.log')
            time.sleep(.2)
        raise RuntimeError(role+'启动超时')
def main():
    for name in ('data','logs','reports'):ROOT.joinpath(name).mkdir(exist_ok=True)
    p=argparse.ArgumentParser();p.add_argument('--desktop',action='store_true');p.add_argument('--web-only',action='store_true');p.add_argument('--no-browser',action='store_true');a=p.parse_args()
    start('simulator',['-m','autonomy.simulator'])
    time.sleep(.3)
    start('worker',['-m','autonomy.worker'],'http://127.0.0.1:19052/health')
    if not a.desktop:start('web',['-m','uvicorn','sky_platform:app','--host','127.0.0.1','--port','19051'],'http://127.0.0.1:19051/api/health')
    if a.desktop or not a.web_only:start('desktop',['-m','desktop.console'])
    if not a.no_browser and not a.desktop:
        import webbrowser;webbrowser.open('http://127.0.0.1:19051/')
    print('晴空邻里已启动。网页19051；独立飞行进程19052；模拟飞控UDP18751。')
if __name__=='__main__':main()
