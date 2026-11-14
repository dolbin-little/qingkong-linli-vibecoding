from pathlib import Path
import zipfile,hashlib,json,time
R=Path(__file__).resolve().parents[1];dest=R.parent/'晴空邻里_网页与独立飞行软件_完整交付_20261105.zip'
files=[]
for p in R.rglob('*'):
    if not p.is_file():continue
    rel=p.relative_to(R);name=p.name
    if any(x in ('__pycache__','.pytest_cache','.git','logs') for x in rel.parts):continue
    if name.endswith(('.pyc','.pyo')) or '.db' in name or name=='local-control.key' or name.startswith('process-') or name.startswith('导师资料'):continue
    if name.startswith('simulator-truth'):continue
    files.append((p,rel))
with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p,rel in files:z.write(p,R.name+'/'+rel.as_posix())
    for d in ('data','logs','reports'):z.writestr(R.name+'/'+d+'/',b'')
with zipfile.ZipFile(dest) as z:
    bad=z.testzip()
    if bad:raise RuntimeError('archive CRC failure: '+bad)
    names=set(z.namelist())
    for key in ['启动全部.cmd','启动网页平台.cmd','启动独立飞行软件.cmd','runtime/python/python.exe','runtime/python/python312.dll','desktop/console.py','frontend/sky.html','autonomy/worker.py']:
        if R.name+'/'+key not in names:raise RuntimeError('missing '+key)
digest=hashlib.sha256(dest.read_bytes()).hexdigest();dest.with_suffix('.zip.sha256.txt').write_text(digest+'  '+dest.name+'\n',encoding='utf-8')
out={'zip':str(dest),'bytes':dest.stat().st_size,'MiB':round(dest.stat().st_size/1024**2,2),'files':len(files),'sha256':digest,'CRC':'passed','excluded':'live DB, session key, PID files, cache, runtime logs, raw advisor CV'}
(R.parent/'交付文件信息.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False))
