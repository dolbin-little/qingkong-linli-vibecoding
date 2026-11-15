"""Local flight daemon; independent of the web server and desktop window."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import json,time,secrets,threading,signal,argparse
from .engine import FlightEngine,ROOT

def key(root=ROOT):
    p=Path(root)/'config/local-control.key'
    if not p.exists():p.write_text(secrets.token_hex(32),encoding='ascii')
    return p.read_text(encoding='ascii').strip()

def serve(port=19052):
    from backend.flight_orders import FlightOrders
    business=FlightOrders();business.recover_after_restart()
    engine=FlightEngine(business=business);token=key();thread=threading.Thread(target=engine.loop,daemon=True);thread.start()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,code,obj):
            data=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode('utf-8');self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        def authenticated(self):return secrets.compare_digest(self.headers.get('X-Sky-Key',''),token)
        def do_GET(self):
            if self.path=='/health':return self.reply(200,{'status':'ok','role':'flight-worker','real_control_default':False})
            if not self.authenticated():return self.reply(401,{'error':'需要本机控制凭据'})
            if self.path=='/state':return self.reply(200,engine.snapshot())
            if self.path=='/record':return self.reply(200,engine.record())
            if self.path=='/shutdown':return self.reply(405,{'error':'使用本项目停止脚本'})
            return self.reply(404,{'error':'不存在'})
        def do_POST(self):
            if not self.authenticated():return self.reply(401,{'error':'需要本机控制凭据'})
            origin=self.headers.get('Origin')
            if origin:return self.reply(403,{'error':'浏览器不得直连飞行进程控制接口'})
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=100000:raise ValueError('请求尺寸无效')
                b=json.loads(self.rfile.read(n));owner=b.get('owner','desktop')
                if owner not in ('web','desktop','test'):raise ValueError('控制端无效')
                if self.path!='/command':return self.reply(404,{'error':'不存在'})
                result=engine.action(b.get('command'),b.get('data'),owner);return self.reply(200,result)
            except (ValueError,TypeError,TimeoutError,OSError) as e:return self.reply(409,{'error':str(e)})
            except Exception as e:return self.reply(500,{'error':type(e).__name__+': '+str(e)})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    try:server.serve_forever(poll_interval=.2)
    finally:engine.running=False;server.server_close()

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--port',default=19052,type=int);serve(a.parse_args().port)
