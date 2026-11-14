import urllib.request,urllib.error,json
from .worker import key

def rpc(path='/state',body=None,timeout=3):
    req=urllib.request.Request('http://127.0.0.1:19052'+path,data=json.dumps(body).encode() if body is not None else None,headers={'X-Sky-Key':key(),'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
    except urllib.error.HTTPError as e:
        try:msg=json.load(e).get('error','飞行进程拒绝请求')
        except Exception:msg=str(e)
        raise ValueError(msg) from e
    except urllib.error.URLError:raise ConnectionError('独立飞行进程未运行，请先启动飞行服务')

def command(cmd,data=None,owner='desktop'):return rpc('/command',{'command':cmd,'data':data or {},'owner':owner},timeout=8 if cmd=='upload' else 3)
