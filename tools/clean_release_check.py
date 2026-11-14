"""Verify a complete ZIP in a new extracted directory; only local simulators."""
from pathlib import Path
import contextlib, ctypes, hashlib, json, os, shutil, socket, subprocess, sys, time, urllib.request, zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
ARCHIVE=ROOT.parent/'交付/晴空邻里_软件创新版_完整运行包_20261114.zip'
STAGE=ROOT.parent/'交付'/('启动验证_20261114_'+time.strftime('%H%M%S'))
FLAGS=0x08000000 if os.name=='nt' else 0
report={'kind':'fresh-extraction-startup','archive':str(ARCHIVE),'started':time.strftime('%Y-%m-%d %H:%M:%S'),'checks':[],'scope':'Windows本机，新解压目录，使用包内Python；自建模拟飞控，无实机'}

def run(args,cwd):
    p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=FLAGS,env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'})
    if p.returncode:raise RuntimeError(p.stdout[-2000:]+p.stderr[-2000:])
    return p.stdout

def url(path):
    with urllib.request.urlopen('http://127.0.0.1:19051'+path,timeout=5) as r:return r.read()

def stop(root):run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(root/'tools/stop.ps1')],root)

def check(v,name):
    if not v:raise AssertionError(name)
    report['checks'].append(name);print('PASS',name,flush=True)

extracted=None
try:
    from autonomy.client import rpc
    s=rpc();check(not s['telemetry']['armed'] and not s.get('business_task'),'原副本地面无活动任务')
    stop(ROOT)
    started=time.monotonic();STAGE.mkdir()
    with zipfile.ZipFile(ARCHIVE) as z:
        for name in z.namelist():
            candidate=(STAGE/name).resolve()
            if STAGE.resolve() not in candidate.parents:raise ValueError('Invalid archive path')
        z.extractall(STAGE)
    extracted=STAGE/ROOT.name;py=extracted/'runtime/python/python.exe'
    check(py.is_file() and not (extracted/'runtime').is_symlink(),'完整依赖实际解压')
    check(not (extracted/'config/local-control.key').exists(),'不携带原控制密钥')
    report['extraction_seconds']=round(time.monotonic()-started,2)
    boot=time.monotonic()
    print(run([str(py),'-X','utf8','-B','tools/launch.py','--web-only','--no-browser'],extracted),flush=True)
    check(json.loads(url('/api/health')) is not None,'新解压目录网页健康')
    check('晴空邻里'.encode() in url('/'),'网页首页可访问')
    check((extracted/'config/local-control.key').is_file(),'独立生成控制密钥')
    report['boot_seconds']=round(time.monotonic()-boot,2)
    print(run([str(py),'-X','utf8','-B','tools/launch.py','--desktop'],extracted),flush=True)
    record=json.loads((extracted/'data/process-desktop.json').read_text(encoding='utf8'))
    time.sleep(2)
    handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,record['pid'])
    check(bool(handle),'新副本桌面进程持续运行')
    if handle:ctypes.windll.kernel32.CloseHandle(handle)
    check(Path(record['root']).resolve()==extracted.resolve(),'桌面进程归属新解压副本')
    print(run([str(py),'-X','utf8','-B','tools/business_acceptance.py'],extracted),flush=True)
    business=json.loads((extracted/'reports/business-acceptance.json').read_text(encoding='utf8'))
    check(len(business['checks'])==17,'新解压副本17项业务检查')
    report['business_check_count']=len(business['checks'])
    report['elapsed_seconds']=round(time.monotonic()-started,2)
    check(report['elapsed_seconds']<600,'解压启动与业务联调共计少于10分钟')
    report['passed']=True
except Exception as e:
    report['passed']=False;report['error']=repr(e)
finally:
    if extracted and (extracted/'tools/stop.ps1').exists():
        with contextlib.suppress(Exception):stop(extracted)
    report['archive_sha256']=hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    (ROOT/'reports/clean-start-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    # Preserve the verification evidence, remove only our new extraction tree.
    if STAGE.exists() and STAGE.resolve().parent==(ROOT.parent/'交付').resolve() and STAGE.name.startswith('启动验证_20261114_'):
        shutil.rmtree(STAGE)
    print(run([str(ROOT/'runtime/python/python.exe'),'-B','tools/launch.py','--web-only','--no-browser'],ROOT),flush=True)
    print(json.dumps(report,ensure_ascii=False),flush=True)
if not report.get('passed'):sys.exit(1)
