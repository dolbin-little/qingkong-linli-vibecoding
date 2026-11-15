"""Independent local ground-control application. Window closure does not kill the flight daemon."""
import tkinter as tk
from tkinter import ttk,messagebox,simpledialog,filedialog
import threading,time,json,math,sys
from pathlib import Path
from autonomy.client import rpc,command
from autonomy.models import SCENARIOS

class Console:
    def __init__(self):
        self.root=tk.Tk();self.root.title('晴空邻里 · 独立飞行控制软件（订单协同版）');self.root.geometry('1320x860');self.root.minsize(1050,700);self.root.configure(bg='#edf4f2');self.state=None;self.busy=False;self.closing=False;self.notifications=[];self.task_data={'orders':[],'tasks':[]};self.tasks_at=0.;self.task_signature=None
        style=ttk.Style();style.theme_use('clam');style.configure('TButton',font=('Microsoft YaHei',11),padding=6);style.configure('TCombobox',font=('Microsoft YaHei',11),padding=5)
        head=tk.Frame(self.root,bg='#143e43',height=95);head.pack(fill='x');tk.Label(head,text='晴空邻里   独立飞行控制',bg='#143e43',fg='white',font=('Microsoft YaHei',25,'bold')).pack(anchor='w',padx=25,pady=(15,4));tk.Label(head,text='MAVLink遥测与回执   /   20Hz外环控制   /   飞行服务独立进程',bg='#143e43',fg='#9fc3be',font=('Microsoft YaHei',11)).pack(anchor='w',padx=28,pady=(0,14))
        bar=tk.Frame(self.root,bg='#edf4f2');bar.pack(fill='x',padx=20,pady=12)
        self.scenario=ttk.Combobox(bar,values=[s['name'] for s in SCENARIOS.values()],width=17,state='readonly');self.scenario.set(SCENARIOS['neighborhood']['name']);self.scenario.grid(row=0,column=0,rowspan=2,padx=4)
        for i,(text,cmd) in enumerate([('连接模拟飞控','connect'),('获取操控权','lease'),('载入场景','load'),('飞前解锁','arm'),('开始/继续','start'),('安全悬停','hold'),('自主返航','rtl'),('受控降落','land')]):
            ttk.Button(bar,text=text,command=lambda c=cmd:self.act(c)).grid(row=i//4,column=i%4+1,sticky='ew',padx=3,pady=2)
        for col in range(1,5):bar.columnconfigure(col,weight=1)
        orders_bar=tk.Frame(self.root,bg='#edf4f2');orders_bar.pack(fill='x',padx=24,pady=(0,10))
        tk.Label(orders_bar,text='关联共享订单',bg='#edf4f2',font=('Microsoft YaHei',11)).pack(side='left')
        self.order=ttk.Combobox(orders_bar,values=['独立模拟任务'],state='readonly',width=38);self.order.set('独立模拟任务');self.order.pack(side='left',padx=8)
        for label,cmd in [('预检订单方案','preview_order'),('取消准备任务','cancel_task'),('异常核对恢复','recover_task')]:
            ttk.Button(orders_bar,text=label,command=lambda c=cmd:self.act(c)).pack(side='left',padx=4)
        body=tk.Frame(self.root,bg='#edf4f2');body.pack(fill='both',expand=True,padx=20)
        left_shell=tk.Frame(body,bg='white',width=340);left_shell.pack(side='left',fill='y',padx=(0,14));left_shell.pack_propagate(False)
        scroll=tk.Canvas(left_shell,bg='white',highlightthickness=0,width=320)
        scrollbar=ttk.Scrollbar(left_shell,orient='vertical',command=scroll.yview);scrollbar.pack(side='right',fill='y');scroll.pack(side='left',fill='both',expand=True);scroll.configure(yscrollcommand=scrollbar.set)
        left=tk.Frame(scroll,bg='white');left_window=scroll.create_window((0,0),window=left,anchor='nw')
        left.bind('<Configure>',lambda e:scroll.configure(scrollregion=scroll.bbox('all')))
        scroll.bind('<Configure>',lambda e:scroll.itemconfigure(left_window,width=e.width))
        self.phase=tk.Label(left,text='等待连接',font=('Microsoft YaHei',20,'bold'),bg='#e3efeb',fg='#1c7167',wraplength=300);self.phase.pack(fill='x',padx=14,pady=14)
        self.metrics=tk.Label(left,text='',font=('Consolas',11),justify='left',anchor='nw',bg='white',fg='#28505b');self.metrics.pack(fill='x',padx=16,pady=6)
        controls=tk.Frame(left,bg='white');controls.pack(fill='x',padx=12,pady=10)
        for index,(text,cmd) in enumerate([('人工接管','manual'),('释放操控权','release'),('故障复位','reset_fault'),('接入其他飞控','real'),('上传全球航点','upload'),('允许真实写控制','confirm_real'),('保存运行报告','export'),('使用说明','help')]):ttk.Button(controls,text=text,command=lambda c=cmd:self.act(c)).grid(row=index//2,column=index%2,sticky='ew',padx=2,pady=3)
        controls.columnconfigure(0,weight=1);controls.columnconfigure(1,weight=1)
        self.fault=ttk.Combobox(controls,values=['clear','sensor','link','gps','battery','ack_loss','payload'],state='readonly');self.fault.set('sensor');self.fault.grid(row=4,column=0,columnspan=2,sticky='ew',pady=(8,3));ttk.Button(controls,text='模拟器故障注入',command=lambda:self.act('inject')).grid(row=5,column=0,columnspan=2,sticky='ew')
        self.canvas=tk.Canvas(body,bg='#f7faf7',highlightthickness=0);self.canvas.pack(side='left',fill='both',expand=True);self.canvas.bind('<Configure>',lambda e:self.draw())
        foot=tk.Frame(self.root,bg='#143e43');foot.pack(fill='x',padx=20,pady=14)
        self.message=tk.Label(foot,text='请启动独立飞行服务。关闭本窗口不终止飞行服务。',fg='#cbe2d9',bg='#143e43',font=('Microsoft YaHei',11),anchor='w',wraplength=1200);self.message.pack(fill='x',padx=12,pady=9)
        self.root.bind('<KeyPress>',self.jog);self.root.protocol('WM_DELETE_WINDOW',self.close);self.root.after(300,self.poll)
    def show(self,msg,keep_seconds=8):
        self.message.config(text=msg)
        if keep_seconds:self.message_until=time.monotonic()+keep_seconds
    def act(self,cmd):
        if self.busy and cmd not in ('hold','land','manual'):return self.show('正在处理上一个操作，请稍候。')
        data={}
        if cmd=='connect':data={'endpoint':'udpout:127.0.0.1:18751'}
        elif cmd in ('load','preview_order'):
            oid=None if self.order.get()=='独立模拟任务' else self.order.get().split(' · ')[0]
            if cmd=='preview_order' and not oid:return self.show('请在关联共享订单中选择订单。')
            data={'scenario':next(k for k,v in SCENARIOS.items() if v['name']==self.scenario.get()),'seed':42,'order_id':oid}
        elif cmd=='cancel_task':data={'run_id':self.state.get('run_id') if self.state else None}
        elif cmd=='recover_task':
            tasks=[t for t in self.task_data['tasks'] if t['phase'] in ('STOPPED','INTERRUPTED')]
            if not tasks:return self.show('没有需要恢复的停止或中断任务。')
            text=simpledialog.askstring('核对飞机与货物','任务 '+tasks[0]['order_id']+'：请先确认飞机返站及货物去向，再填写核对说明。\n未交付货物恢复库存；飞机转维护待检查。',parent=self.root)
            if not text:return
            data={'run_id':tasks[0]['run_id'],'note':text}

        elif cmd=='inject':data={'fault':self.fault.get()}
        elif cmd=='real':
            endpoint=simpledialog.askstring('飞控连接','输入MAVLink地址或串口，例如 udpin:0.0.0.0:14550 或 COM5\n默认只读，不自动解锁或起飞',parent=self.root)
            if not endpoint:return
            cmd='connect';data={'endpoint':endpoint,'baud':115200}
        elif cmd=='confirm_real':
            phrase=simpledialog.askstring('本机真实控制确认','需先在config/project.json启用real_control_enabled。\n确认飞控参数、坐标原点、净空、遥控接管及测试场地后输入：\n确认场地安全并保留遥控接管',parent=self.root)
            if phrase is None:return
            data={'phrase':phrase}
        elif cmd=='upload':
            path=filedialog.askopenfilename(title='选择全球航点JSON，字段lat/lon/alt',filetypes=[('JSON','*.json')])
            if not path:return
            try:data={'items':json.loads(Path(path).read_text(encoding='utf-8'))}
            except Exception as e:return self.show(str(e))
        elif cmd=='help':
            import webbrowser
            path=Path(__file__).resolve().parents[1]/'output/产品介绍与操作手册/晴空邻里_全界面与按钮使用说明_20261114.html'
            if path.is_file():webbrowser.open(path.as_uri())
            else:self.show('本副本缺少使用说明，请使用完整交付包。')
            return
        elif cmd=='export':
            path=filedialog.asksaveasfilename(defaultextension='.json',initialfile='晴空邻里飞行报告.json')
            if path:
                try:
                    record=rpc('/record');Path(path).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8');self.show('已保存完整保留窗口报告（最长约10分钟）')
                except Exception as e:self.show('报告未保存：'+str(e))
            return
        self.show('正在处理操作，等待服务回执…');self.busy=True
        def work():
            try:
                r=command(cmd,data)
                if cmd=='preview_order':
                    p=r['selected'];text=f"建议 {p['station_name']} / {p['drone_id']}，往返 {p['roundtrip_m']} m，估算 {p['estimated_wh']} Wh。仅预检，尚未占用库存。"
                elif cmd=='load':text=f"场景已载入，共 {len(r.get('route',[]))} 个航点。下一步：飞前解锁。"
                elif cmd=='lease':text='已获取桌面操控权。现在可以点击“载入场景”。'
                elif cmd=='release':text='已释放桌面操控权，可交由网页版操作。'
                elif cmd=='connect':text='连接请求已发出，正在等待飞控心跳。'
                else:text=str(r.get('reason',r))
            except Exception as e:
                text='操作未执行：'+str(e)
                if '请先获取操控权' in str(e):text+='。请先点击顶部“获取操控权”，再点击“载入场景”。'
            self.notifications.append(text);self.busy=False
        threading.Thread(target=work,daemon=True).start()
    def jog(self,e):
        if not self.state or self.state['phase']!='MANUAL':return
        mapping={'w':[1.,0.,0.],'s':[-1.,0.,0.],'a':[0.,-1.,0.],'d':[0.,1.,0.],'r':[0.,0.,.7],'f':[0.,0.,-.7],'space':[0.,0.,0.]}
        if e.keysym.lower() in mapping:
            threading.Thread(target=lambda:command('jog',{'velocity':mapping[e.keysym.lower()]}),daemon=True).start()
    def poll(self):
        if self.closing:return
        while self.notifications:self.show(self.notifications.pop(0))
        def work():
            try:
                s=rpc();self.state=s
                if time.monotonic()-self.tasks_at>3:
                    self.task_data=command('tasks');self.tasks_at=time.monotonic()
                if s.get('lease')=='desktop':command('lease')
            except Exception as e:self.notifications.append(str(e))
        if not getattr(self,'polling',False):
            self.polling=True
            def task():
                try:work()
                finally:self.polling=False
            threading.Thread(target=task,daemon=True).start()
        values=['独立模拟任务']+[o['id']+' · '+o['address'] for o in self.task_data['orders']]
        active=next((t for t in self.task_data['tasks'] if t['phase'] not in ('COMPLETED','CANCELLED','RECOVERED')),None)
        active_value=active['order_id']+' · 当前执行任务' if active else None
        if active_value:values.append(active_value)
        signature=tuple(values)
        if signature!=self.task_signature:
            current=self.order.get();self.order.config(values=values)
            if current not in values:self.order.set(active_value or '独立模拟任务')
            self.task_signature=signature
        s=self.state
        if s:
            self.phase.config(text={'LINK_LOST':'断链待确认','DISCONNECTED':'等待连接','CONNECTING':'连接中','CONNECTED':'连接已建立','READY':'任务已就绪','ARMING':'等待解锁确认','ARMED':'已解锁','EXECUTING':'前往交付点并下降','DELIVERY_LANDING':'交付点着陆停桨','DELIVERY_RELEASING':'卸货与回执确认','DELIVERY_WAIT':'等待实物交付','DEPARTURE_ARMING':'交付后起飞准备','HOLD':'安全悬停','RETURNING':'自主返航','LANDING':'受控降落','COMPLETED':'已完成','STOPPED':'已停止','MANUAL':'人工接管'}.get(s['phase'],s['phase']));t=s.get('telemetry') or {};p=t.get('position',[0,0,0]);v=t.get('velocity',[0,0,0]);ages=s.get('ages',{})
            self.metrics.config(text=f"订单 {s.get('order_id') or '独立模拟任务'}\n任务 {s.get('run_id') or '未载入'}\n连接 {'本机模拟飞控' if s['simulation'] else '外部飞控'}\n飞行器解锁 {t.get('armed',False)}\n电量 {t.get('battery',0):.1f}%\n位置 N/E/U\n{p[0]:7.2f} {p[1]:7.2f} {p[2]:7.2f} m\n速度 {math.sqrt(sum(x*x for x in v)):.2f} m/s\n心跳年龄 {ages.get('heartbeat',0):.2f} s\n定位年龄 {ages.get('position',0):.2f} s\n感知年龄 {ages.get('sensor',0):.2f} s\n航点 {s['waypoint']}/{len(s['route'])}\n交付 {s.get('delivery',{}).get('label','等待到达')}\n保护介入 {s['stats']['guard_interventions']}\n指令/消息 {s.get('traffic',{}).get('sent',0)}/{s.get('traffic',{}).get('received',0)}\n控制权 {s.get('lease') or '空闲'}")
            if not self.busy and (time.monotonic()>=getattr(self,'message_until',0) or s.get('fault')):self.show((s.get('safety_status',{}).get('title','')+'；'+s.get('safety_status',{}).get('next','') if s.get('fault') else s['reason'])+'   W/S/A/D平移，R/F升降，空格停止（仅人工模式）',keep_seconds=0)
            self.draw()
        self.root.after(250,self.poll)
    def draw(self):
        c=self.canvas;c.delete('all');w=c.winfo_width();h=c.winfo_height();s=self.state
        if not s:return
        sc=s['scenario'];scale=min((w-60)/100,(h-80)/80);x0=30;y0=45
        project=lambda p:(x0+p[0]*scale,y0+(80-p[1])*scale)
        c.create_text(24,20,text='局部场景俯视   ·   坐标N/E，单位m；高度独立显示',anchor='w',font=('Microsoft YaHei',12),fill='#52756b')
        for x in range(0,101,10):a,b=project([x,0]);aa,bb=project([x,80]);c.create_line(a,b,aa,bb,fill='#e4ece7')
        for y in range(0,81,10):a,b=project([0,y]);aa,bb=project([100,y]);c.create_line(a,b,aa,bb,fill='#e4ece7')
        for o in sc['obstacles']:
            x,y=project([o['x'],o['y']]);r=o['r']*scale;c.create_oval(x-r,y-r,x+r,y+r,fill='#c7d6cf',outline='#a6bdb3');c.create_text(x,y,text=o['id']+'\n'+str(o['h'])+'m',fill='#526f64')
        pts=[p for q in s['route'] for p in project(q)]
        if len(pts)>=4:c.create_line(*pts,fill='#d5a65d',width=3,dash=(5,4))
        tr=[p for q in s['trace'] for p in project(q['p'])]
        if len(tr)>=4:c.create_line(*tr,fill='#368b7c',width=2)
        for pos,label,color in [(sc['home'],'共享微站','#1b6e65'),(sc['goal'],'公共交付点','#bc8a38')]:
            x,y=project(pos);c.create_oval(x-7,y-7,x+7,y+7,fill=color,outline='white');c.create_text(x,y+19,text=label,fill=color,font=('Microsoft YaHei',10))
        if s.get('telemetry'):
            p=s['telemetry']['position'];x,y=project(p);c.create_line(x-11,y-11,x+11,y+11,fill='#1d6174',width=4);c.create_line(x-11,y+11,x+11,y-11,fill='#1d6174',width=4);c.create_text(x,y-23,text=f"无人机  高度{p[2]:.1f}m",fill='#1b5369',font=('Microsoft YaHei',11,'bold'))
    def close(self):
        self.closing=True
        try:command('release')
        except Exception:pass
        self.root.destroy()
    def run(self):self.root.mainloop()

if __name__=='__main__':Console().run()
