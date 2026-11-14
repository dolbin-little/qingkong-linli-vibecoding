from pathlib import Path
import json,hashlib,re,ast,zipfile,time
R=Path(__file__).resolve().parents[1]
def read(name):return json.loads((R/name).read_text(encoding='utf-8'))
legacy=(R/'reports/legacy-tests.txt').read_text(encoding='utf-8-sig');unit=(R/'reports/autonomy-tests.txt').read_text(encoding='utf-8-sig')
counts={'原平台回归':int(re.search(r'(\d+) passed',legacy)[1]),'新增自动测试':int(re.search(r'(\d+) passed',unit)[1])}
for title,p in [('MAVLink集成','reports/integration-results.json'),('网关与独立进程','reports/gateway-results.json'),('人工控制与只读保护','reports/control-results.json')]:
    rows=read(p)['results']
    if not all(x['passed'] for x in rows):raise RuntimeError(title+'仍有未通过检查')
    counts[title]=len(rows)
normal=read('reports/scenario-neighborhood-42.json');dynamic=read('reports/scenario-crossing-42.json')
if normal['phase']!='COMPLETED' or normal['truth']['collision']:raise RuntimeError('默认配送未通过')
text='''晴空邻里自主飞行协同版：验收记录（2026-11-05）

一、验证环境
Windows本机；便携Python与Tk；FastAPI/SQLite网页服务；独立飞行服务；独立自建MAVLink模拟飞控。
模拟器不是ArduPilot/PX4官方SITL，没有真实无人机参与。
'''
text+='\n'.join(k+'：'+str(v)+'项通过' for k,v in counts.items())
text+='''

二、默认完整场景
场景neighborhood、种子42；实际结果COMPLETED。
爬升→航点跟踪→交付点悬停→自主返航→降落，保护介入0次。
模拟器评价里程 %.2f米，模型能耗 %.3fWh，碰撞标志false。
这些是合成模型的评价值，不是实机测量。
记录：reports/scenario-neighborhood-42.json；完整轨迹见对应flight报告及logs/trace-*.jsonl。

三、复杂动态场景（保留局限）
场景crossing、种子42，动态障碍位于原巡航走廊。
当前最终记录进行了%d次动态重规划，随后因%s进入保护，落地状态%s，未完成配送。
模拟碰撞标志false。这个案例不计为配送成功，也不能用它声称全场景自主避障可靠。
早期的动态缓冲/网格连接失败及低电量返航冲突记录也已保留在reports。

四、已修正的问题
低电量返航指令曾被同一电量条件重复拦截：已修正，并加入回归。
安全点四舍五入落进建筑缓冲网格：增加可达网格锚点并加入双向回归。
在航点处过早转向：改为接近目标且速度收敛后换点。
模式确认超时、保护中止后待解锁、意外解除电机、无效重连破坏旧连接均已补保护与回归。
Windows UDP客户端改用临时源端口；本机目标只绑定回环，不占用模拟飞控目标端口。
增加电量与GPS各自的时效校验、未知卫星数保护和外部设备默认只读。

五、界面核验
网页完成实际登录、连接模拟器、操控权、载入、解锁、执行、页面切换、来源查看及轨迹回放。
最终网页连接按钮已核对指向UDP18751，控制服务及原社区接口可访问。
Three.js实际渲染并保存预览；最终浏览器错误/警告日志为空。
独立桌面窗口已实际启动并显示遥测，Tk便携环境可运行。
Windows网络访问询问遮挡了部分桌面点击核验；没有授权公共网络访问。
桌面全部按钮的逐一鼠标操作未作为通过项计入上述测试。
人工操控、指令超时归零、限幅、落地及外部只读通过同一控制服务的MAVLink实联调核验。
关闭网页服务后，飞行进程的周期和遥测继续增长；该记录见gateway-results.json。

六、尚待完成的验证
具体飞控及传感器接入、官方SITL/HIL、真实场地地图与坐标标定、实际动力与补能测量、
精确着陆、实物交付、独立硬件急停、遥控接管与全场景压力测试。
20Hz是软件外环目标频率，非硬实时保证；运行报告保留周期波动。
不报告跨场景成功率、视觉识别准确率、商业运营效果或安全认证结论。
'''%(normal['truth']['distance'],normal['truth']['energy_wh'],dynamic['stats']['replans'],dynamic['fault'],dynamic['phase'])
(R/'docs/验收结果与已知限制.txt').write_text(text,encoding='utf-8-sig')
summary={'environment':'Windows custom MAVLink simulator; no physical aircraft or official SITL','counts':counts,'default_scene':normal,'dynamic_scene':dynamic,'gui_note':'Native window rendered; system network prompt prevented complete click coverage; no public network permission granted.'}
(R/'reports/验收汇总.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
manifest=[]
for folder in ['autonomy','desktop','backend','tools','tests_autonomy']:
    for p in (R/folder).glob('*.py'):
        ast.parse(p.read_text(encoding='utf-8-sig'));manifest.append({'file':p.relative_to(R).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
for name in ['sky_platform.py','frontend/sky.html','frontend/sky.css','frontend/sky.js','frontend/sky-scene.mjs','config/project.json','requirements-lock.txt']:
    p=R/name;manifest.append({'file':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(R/'docs/源码校验清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
svg='''<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="580" viewBox="0 0 1500 580"><defs><marker id="a" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0 0L10 5L0 10" fill="#2a8274"/></marker></defs><rect width="1500" height="580" rx="24" fill="#f3f7ec"/><g font-family="Microsoft YaHei, sans-serif" fill="#214d47"><text x="65" y="75" font-size="32" font-weight="bold">晴空邻里 · 网页与软件协同架构</text><g fill="white" stroke="#cbdccf" stroke-width="2"><rect x="65" y="135" width="390" height="145" rx="18"/><rect x="65" y="320" width="390" height="145" rx="18"/><rect x="590" y="180" width="370" height="240" rx="18"/><rect x="1090" y="135" width="345" height="145" rx="18"/><rect x="1090" y="320" width="345" height="145" rx="18"/></g><g font-size="24" font-weight="bold"><text x="95" y="180">网页服务交互平台</text><text x="95" y="365">Windows独立飞行软件</text><text x="620" y="230">独立飞行服务 · 20Hz外环</text><text x="1120" y="180">独立MAVLink模拟飞控</text><text x="1120" y="365">外部无人机协议适配</text></g><g font-size="19" fill="#6a897c"><text x="95" y="222">城市共享订单 / 三维遥测 / 测试回放</text><text x="95" y="407">接入 / 控制 / 人工接管 / 航点上传</text><text x="620" y="275">感知时效 → 规划 → 控制 → 保护</text><text x="620" y="315">本机认证 · 操控权租约 · 独立记录</text><text x="620" y="365">网页或窗口退出，服务仍独立运行</text><text x="1120" y="222">独立动力学 / 遥测 / 回执 / 故障</text><text x="1120" y="407">串口与UDP / 默认只读 / 实机待验</text></g><g stroke="#2a8274" stroke-width="3" fill="none" marker-end="url(#a)"><path d="M455 208L520 208L520 260L580 260"/><path d="M455 390L520 390L520 340L580 340"/><path d="M960 260L1020 260L1020 208L1080 208"/><path d="M960 340L1020 340L1020 390L1080 390"/></g><text x="65" y="535" font-size="19" fill="#8b9e8b">当前验证：Windows与自建MAVLink模拟飞控；真实飞控、官方SITL及硬件在环尚待验证。</text></g></svg>'''
(R/'docs/系统架构图.svg').write_text(svg,encoding='utf-8')
print('验收文档、架构图和源码清单已生成',counts)
