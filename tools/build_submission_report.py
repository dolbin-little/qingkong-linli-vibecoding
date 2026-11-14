"""Build the technical report from verified project evidence (ReportLab)."""
from pathlib import Path
import json, subprocess, html, math
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor, Color, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Line, Circle, String, PolyLine, Rect
from reportlab.lib.enums import TA_CENTER

R=Path(__file__).resolve().parents[1];OUT=R/'output/pdf';OUT.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('CN','C:/Windows/Fonts/simsun.ttc',subfontIndex=0))
F='CN';GREEN=HexColor('#194f48');TEAL=HexColor('#398a79');GOLD=HexColor('#b58842');INK=HexColor('#263d38')
styles={
 'body':ParagraphStyle('body',fontName=F,fontSize=11,leading=18,textColor=INK,spaceAfter=12,wordWrap='CJK'),
 'small':ParagraphStyle('small',fontName=F,fontSize=9,leading=14,textColor=HexColor('#61756d'),spaceAfter=9,wordWrap='CJK'),
 'sub':ParagraphStyle('sub',fontName=F,fontSize=13,leading=20,textColor=GREEN,spaceBefore=6,spaceAfter=9,wordWrap='CJK'),
 'title':ParagraphStyle('title',fontName=F,fontSize=24,leading=34,textColor=GREEN,spaceAfter=18,wordWrap='CJK'),
 'hero':ParagraphStyle('hero',fontName=F,fontSize=44,leading=57,textColor=GREEN,spaceAfter=20),
}
story=[];pages=[]
def p(text,kind='body'):story.append(Paragraph(html.escape(text).replace('\n','<br/>'),styles[kind]))
def page(title,kicker):
 if pages:story.append(PageBreak())
 pages.append(title);p(kicker,'small');p(title,'title')
def sub(title,text):p(title,'sub');p(text)
def diagram(labels):
 d=Drawing(480,112);step=470/(len(labels)-1) if len(labels)>1 else 0
 for i,label in enumerate(labels):
  x=5+i*step
  if i<len(labels)-1:d.add(Line(x,67,x+step,67,strokeColor=TEAL,strokeWidth=2))
  d.add(Circle(x,67,5,fillColor=TEAL,strokeColor=white))
  for j,t in enumerate(label.split('|')):d.add(String(max(0,min(420,x-22)),42-j*16,t,fontName=F,fontSize=10,fillColor=INK))
 story.append(d)
def architecture():
 d=Drawing(480,255)
 items=[(70,210,'社区网页'),(395,210,'桌面控制台'),(70,115,'FastAPI / SQLite'),(315,115,'独立飞行服务'),(315,20,'MAVLink模拟飞控')]
 for x,y,t in items:
  d.add(Circle(x,y,7,fillColor=TEAL,strokeColor=white))
  tx,ty=(x+16,y+4) if x==315 else (x-50,y+18)
  d.add(String(tx,ty,t,fontName=F,fontSize=12,fillColor=GREEN))
 for a,b in [((70,200),(70,130)),((80,207),(300,125)),((390,200),(325,130)),((95,115),(299,115)),((315,100),(315,35))]:d.add(Line(*a,*b,strokeColor=GOLD,strokeWidth=2))
 d.add(String(155,78,'命令 / 状态 / 业务同步',fontName=F,fontSize=10,fillColor=INK))
 d.add(String(330,62,'遥测与回执',fontName=F,fontSize=10,fillColor=INK))
 story.append(d)
def routeplot(row):
 d=Drawing(480,285)
 def tr(v):return (30+v[0]*4.1,15+v[1]*3.05)
 for o in row['scene']['obstacles']:
  x,y=tr([o['x'],o['y']]);d.add(Circle(x,y,o['r']*3.3,fillColor=HexColor('#e0e9df'),strokeColor=TEAL));d.add(String(x-10,y,o['id'],fontName=F,fontSize=10))
 for points,color in [(row['raw_route'],GOLD),(row['route'],HexColor('#7984b4')),([t['p'] for t in row['trace']],TEAL)]:
  d.add(PolyLine([v for pt in points for v in tr(pt)],strokeColor=color,strokeWidth=1.4))
 story.append(d)
def bars(values):
 d=Drawing(480,135)
 for i,(label,a,total) in enumerate(values):
  y=105-i*38;d.add(String(0,y,label,fontName=F,fontSize=11,fillColor=INK));d.add(Rect(140,y-4,230,15,fillColor=HexColor('#e9eeea'),strokeColor=None));d.add(Rect(140,y-4,230*a/total,15,fillColor=TEAL,strokeColor=None));d.add(String(385,y,f'{a}/{total}',fontName=F,fontSize=11,fillColor=GREEN))
 story.append(d)

fixed=json.loads((R/'reports/fixed-benchmark.json').read_text(encoding='utf8'))
official=json.loads((R/'reports/official-sitl-acceptance.json').read_text(encoding='utf8'))
business=json.loads((R/'reports/business-acceptance.json').read_text(encoding='utf8'))
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()

page('晴空邻里','SOFTWARE INNOVATION / TECHNICAL REPORT / 2026-11-14')
p('面向未来城市的绿色低空共享服务交互平台','title')
p('软件创新参赛技术文档','sub')
p('社区服务网页 · 独立飞行控制软件 · 可复验的软件仿真')
diagram(['服务需求','订单预检','自主执行','交付确认','异常核对'])
sub('摘要','项目以城市社区共享物品配送为场景，将业务订单、库存、无人机资源与飞行任务状态关联。网页承担管理、三维展示和运行解释，桌面提供飞控连接与接管入口，独立Python服务执行规划、外环控制及安全检查。系统通过MAVLink与模拟飞控形成持续反馈，并保留命令回执、轨迹和异常处置证据。')
p('本报告说明真实实现、人工意图与AI协同方法、测试条件及复现步骤。官方飞控验证为软件在环，现有结果不等同于真实无人机飞行和实物交付。','small')
p('版本依据：本轮2026-11-14工程改进；报告生成前代码HEAD '+head[:12]+'。三条协作原文与Git证据随包提供。','small')

page('01 作品定位与人工设计意图','PROBLEM / SCOPE / CONTRIBUTION')
sub('从社区需求出发','居民需要的是一次可解释的服务：物品从哪里来、什么时候可执行、由哪架飞机运输、是否真正交付，以及失败后由谁核对。单独展示地图或飞行轨迹无法证明业务完成，因此我们将订单、库存、飞机与任务记录贯通。')
sub('我的总体设计与要求','我提出总体架构、技术与算法方向、功能范围和界面要求，确定“社区服务网页＋独立飞行软件”的组合，并根据实际体验持续反馈改进。例如，指出到达交付点后直接返航不符合交付过程，要求飞机下降放货；要求保留原项目、独立目录迭代，并建立真实开发记录。')
sub('AI参与与实现责任','AI依据这些方向参与代码生成、模块修改、问题检查、测试执行和材料整理。具体回执时间戳排错、安全只读边界修复等，由AI在代码检查和联调中完成；不把这些实现细节改写为人工独立编程。功能及界面取舍由参赛者持续引导。')
sub('已有基础与新增部分','已有版本包含社区服务、三维模型、规划控制及交付逻辑。本轮新增可持久化业务台账、两端订单联动、安全边界修正、官方SITL验收与固定评测。Git基线保存已有成果，后续提交记录真实修改，不代表恢复了全部早期开发历史。')
p('依据：docs/AI协作记录；Git f04b4d8及其后提交；docs/AI协作与版本记录_20261114.txt。','small')

page('02 系统架构与软件分工','ARCHITECTURE / SHARED STATE')
architecture()
sub('展示、业务与持续计算分离','HTML/CSS/JavaScript与Three.js构成网页；FastAPI提供业务接口，SQLite保存业务台账；Tkinter提供独立桌面操作窗口；Python飞行服务持续处理状态机、安全检查和速度外环。pymavlink完成遥测与控制消息转换。')
p('网页和桌面通过同一飞行服务读取状态，并不分别运行两套飞行算法。操控权租约限制并发指令。关闭网页后，已经运行的飞行服务能够继续计算和回写业务记录，但电脑关机或飞行进程退出会中断本机外环。')
p('官方ArduCopter SITL使用独立验收脚本，复用本项目适配器和位置控制器；现有业务演示仍连接自建模拟器。两种环境分别计数，不把独立协议验收表述为完整订单链在官方飞控上已全部验证。')
p('代码入口：sky_platform.py、backend/flight_orders.py、autonomy/worker.py、autonomy/engine.py、desktop/console.py、frontend/sky.*。','small')

page('03 从订单到飞行任务','BUSINESS CLOSURE / RESERVATION')
diagram(['居民下单','候选预检','资源预占','任务执行','结果回写'])
sub('先验证可行性，再占用资源','预检读取订单和站点数据，依次检查订单状态、公共取件点映射、禁飞区、天气、站点在线状态、物品库存、飞机载荷和电量。分别规划去程与返程，估算往返能耗后选择可行候选。预检不修改库存。')
p('当前飞行联调支持四个微站、六个已配置公共取件点与一个独立模拟飞行通道。八架业务飞机是候选资源，不等于八机同时自主飞行。地图自选点未配置局部着陆映射时会拒绝载入。')
sub('载入幂等与资源一致性','SQLite事务一次性预占库存和飞机，建立订单与run_id映射。重复载入同一活动任务返回已有记录，不再次扣库存；另一任务占用单飞行通道时明确拒绝。预检与预占之间重新检查，避免读取后资源已变化。')
sub('交付与返航分别确认','货物反馈确认后订单变为送达，库存由预占转为消耗；飞机返航落地后才释放运力。卸货失败或未知中断保留资源等待人工核对，不能自动返库并立即再次派送。')
p('依据：backend/flight_orders.py；tools/business_acceptance.py；reports/business-acceptance.json。候选以参数化往返能耗选择，不声称是VNS全局最优。','small')

page('04 数据、坐标与目标跟踪','COORDINATES / PERCEPTION INPUT')
diagram(['社区点位','局部NEU','协议NED','三维显示'])
p('内部采用米制NEU：北、东、向上。MAVLink局部控制采用NED，向下为正，因此垂直位置与速度在适配层转换符号。Three.js显示再按视图坐标排列。社区业务地图与飞行研究场有明确点位映射，尚不是实际经纬度导航。')
sub('输入验证与时效','遥测记录位置、速度、电量、解锁状态、定位质量及各类更新时间。目标列表检查ID、三维有限数值、半径和列表规模；过期目标退出跟踪。模拟输入与外部输入保留来源标签。')
sub('α–β跟踪','预测位置 = 上次位置 + 上次速度 × Δt；测量残差 = 本次测量 - 预测位置。用α修正位置，用β乘残差/Δt修正速度。当前α=0.7、β=0.15；无更新超过1.5秒的目标被剔除。该模型平滑目标测量并估计运动，不负责从相机图像识别目标。')
p('风险计算基于双方相对位置与相对速度，在未来两秒窗口估计最近接近距离。此方法采用简化匀速假设；快速机动、遮挡和误检下的可靠性尚需额外验证。当前未部署真实摄像头检测与激光雷达融合。')
p('依据：autonomy/models.py、autonomy/perception.py、autonomy/mavlink_adapter.py。','small')

page('05 2.5D A*与净空复核','PLANNING / CLEARANCE')
routeplot(fixed['results'][0])
p('上图来自固定场景：金色为原始网格航线，蓝色为简化航线，绿色为实际模拟轨迹；建筑以俯视圆表示，并保留高度约束。','small')
p('在选定巡航高度建立约2米水平网格，依据建筑高度与安全缓冲标记可行节点。A*以f(n)=g(n)+h(n)选择搜索方向，其中g是累计代价、h是目标距离估计。水平路线与爬升、交付下降连接，形成2.5D航线。')
p('简化航点时仅在较远航点可安全直连的情况下跳过中间点；对整条航段按不超过0.5米采样复核越界与建筑净空。业务与正式评测使用4米场景缓冲。原始场景默认值与业务载入值需区分。')
p(f'本例航点{fixed["results"][0]["raw_points"]}→{fixed["results"][0]["simplified_points"]}，长度{fixed["results"][0]["route_raw_m"]}m→{fixed["results"][0]["route_simplified_m"]}m。这是单一固定场景的路径简化结果，不用于外推所有城市地图。','small')

page('06 外环控制与运行时序','CONTROL / TIMING')
diagram(['当前位置','位置误差','目标速度','飞控响应','新遥测'])
sub('控制量与飞控责任','控制程序采用位置比例反馈与速度反馈，简式为v_cmd=Kp×位置误差−Kd×当前速度，再施加最大速度、垂直速度与变化幅度限制。程序输出位置/速度外环指令，姿态稳定和电机内环由飞控负责。')
p('目标更新频率20Hz，即约50ms一次。Windows与Python不提供硬实时保证，界面展示实际周期均值、P95、最大值及150ms超时次数。连续三次超时且已解锁会进入保护降落，避免悄悄丢失控制周期。')
sub('命令不是执行结果','模式切换、解锁、卸货等动作需要检查命令回执和遥测状态。实际发出解锁指令前再次飞前复检，避免模式等待期间定位或感知数据已经过期。官方飞控拒绝无效模式的测试也保留。')
sub('控制周期与计算耗时分开','离线评测tick_compute_p95_ms是本机单步计算耗时，不能当成在线控制周期。在线周期还受调度、协议处理与记录写入影响。进一步将持久化和较重规划计算移出关键循环是后续工程任务。')
p('依据：autonomy/engine.py、autonomy/safety_status.py；外环代码位于autonomy/planning.py的PositionController。','small')

page('07 着陆交付状态机','DELIVERY / ACKNOWLEDGEMENT')
diagram(['交付点上方','下降着陆','停桨确认','卸货反馈','再起飞返航'])
sub('由使用反馈改变任务语义','参赛者明确指出“飞机要飞下去放东西”。原来仅到达目标后返航的行为不满足服务场景，修改后以着陆交付为默认流程，把“到达航点”“货物送达”“飞机返航”作为不同事实记录。')
p('进入卸货前检查低高度、低速度、新鲜遥测以及飞控未解锁状态。发送模拟机构释放指令后，同时等待命令接受回执与货物释放反馈；反馈时间必须晚于本次释放请求，且满足有效期。')
p('确认成功后才允许再次检查、解锁、爬升及返航。机构拒绝或等待超时进入停止状态，留在地面，不记录送达，也不自动起飞。当前反馈来自自建模拟机构；尚未适配实物门锁、舵机或重量传感器。')
sub('时序问题的实际修复','联调曾出现“场景实际载入但解锁仍提示未确认”，检查发现事件请求与回执时间基准存在先后误差。本轮修正时间戳采样位置，并将场景回执、状态确认纳入验收。该排错由AI执行检查，不补写成参赛者的历史独立操作。')
p('原文：docs/AI协作记录/01_着陆交付流程.txt；当前证据：reports/business-acceptance.json。','small')

page('08 独立安全监控与接管','SAFETY / FAILURES / OWNERSHIP')
sub('保护检查优先于航线执行','检查心跳、位置、GPS、感知及电池时效，定位质量，围栏，近障距离与运动走廊。起飞电量至少45%；电量≤25%请求返航，≤15%请求降落。参数属于本研究场景，不是通用实机标准。')
sub('断链不能假定已经降落','心跳超过阈值进入LINK_LOST，软件可尝试发送降落，但不假定飞控已收到或执行。恢复后保持降落流程，不自动恢复航线；完成判断还要求新鲜心跳、定位、低高度、低速度和未解锁。')
sub('人工操控权与只读模式','网页与桌面共享20秒操控权租约，人工模式下过期或释放会清零速度并锁止保护。正常自主任务不依赖网页持续续租。外部飞控只读时，监控循环不发送解锁、速度和降落等运动命令。')
p('降落一旦开始，较低优先级异常不能将系统切回速度控制。返航规划无可行走廊时降落并提示落点尚未验证；软件保护并不能证明该落点适合实机。硬件急停、飞控失效保护和真实落点感知仍需独立验证。')
p('依据：autonomy/safety.py、autonomy/safety_status.py；tests_autonomy/test_safety_operations.py的12项专项测试。','small')

page('09 持久化、并发与故障恢复','DATA / TRANSACTIONS / RECOVERY')
diagram(['预占资源','保存任务','阶段同步','完成或异常','核对恢复'])
p('SQLite的业务事务串行处理预占与状态修改。FlightOrders保存订单ID、run_id、站点、飞机、货物状态、阶段及历史记录。飞行服务负责同步，网页关闭不会使业务回写依赖浏览器。')
sub('阶段与业务库存的对应','READY为待执行；交付确认后stock由reserved变consumed；COMPLETED释放飞机；STOPPED转recovery_required。起飞前取消可恢复库存；已经执行或状态不明时必须填写核对说明，避免重复发货。')
sub('重启与异常事实保留','重启发现未终结任务会标为INTERRUPTED，保留货物与飞机占用等待核对，不自动把未知任务视为已交付或未出库。台账记录是恢复依据，不能仅凭界面某个数字重置资源。')
p('目前仍是本机数据库与单执行通道，未实现跨服务器事务、分布式一致性或生产级账号体系。默认演示密码仅用于本地验收。运行包不携带原机控制密钥和进程PID，解压后生成本副本的密钥。')
p('依据：backend/store.py、backend/flight_orders.py、autonomy/worker.py、tools/business_acceptance.py。','small')

page('10 算法研究模块与使用边界','RESEARCH / ENERGY / ATTRIBUTION')
sub('调度与能源保留为研究功能','原平台保留VNS–MILP调度、DQN候选排序、LSTM合成条件预测与MPC滚动补能等模块；SciPy/HiGHS用于相关优化。DQN排序不能绕过硬约束；模型训练与合成数据不能替代真实运营数据验证。')
p('本轮订单飞行预检按可行性和参数化往返耗能选择候选，与原有全局调度研究模块分工不同。能耗模型尚未由真实飞机标定，太阳能属于辅助补能参数，并非多旋翼持续飞行的供能证明。')
sub('导师成果仅作方法参考','优先级卸载研究启发本机候选计算成本比较；DR-GGAD残差信号思路启发稳健统计异常线索；分层留痕思路启发SHA-256事件连接与检查点。实现对照见docs/技术来源与实现对照.txt/json。')
p('当前没有真正将任务分发到机载、边缘和云端多台服务器，也未复现DR-GGAD或IA-GGAD原模型。哈希记录有助于发现内容变化，但没有独立可信锚点时不能宣称具有不可伪造审计能力。导师已有论文专利不作为本项目新增发表或授权成果。')
p('资源来源、用途和许可见docs/第三方资源说明.txt、第三方依赖清单.json、third_party/ardupilot_sitl/SOURCE.txt。','small')

page('11 Prompt、上下文与修改约束','HUMAN INTENT / AI COLLABORATION')
sub('人工把目标与边界表达清楚','我提出“网页＋独立软件”“智能自主飞行与共享服务”的总体方向，并对技术算法、功能和界面提出要求。实际使用中的下降交付反馈，将笼统的配送目标转为能够验收的行为。AI把这些意图拆为数据、接口、状态与测试。')
sub('上下文以证据为主','AI先读取现有代码、目录和验收报告，保持原有界面与项目范围；每次修改关联具体模块与运行结果。会话较长时用当前代码、Git提交和报告重新确认现状，避免凭早期口头描述宣布功能完成。')
sub('约束修改范围','保留原目录，在E盘独立版本迭代；不删除无关材料；外部写控制默认关闭；只终止自己启动且路径匹配的进程；业务与安全修改需要针对性回归。界面保持原风格并补充可解释反馈。')
sub('将完成标准写成可检查条件','例如“预检不能扣库存”“重复载入不再次预占”“断链不能当作已落地”“卸货失败不自动再起飞”。这些条件约束AI实现，也使人工判断不只依赖截图。以下三条协作链引用实际历史，分析文字均为事后整理。')

page('12 协作链一：修正交付语义','ORIGINAL FEEDBACK / DELIVERY ITERATION')
p('参赛者原文：“问题还是很大，你到达了交付点怎么就直接返回了，飞机要飞下去放东西啊”。','sub')
p('这是实际使用反馈。它指出了业务语义与动画表现之间的缺口：抵达水平坐标不是完成交付。AI随后解释缺失步骤，并将默认执行流程改为下降着陆、停桨、卸货确认、再次起飞及返航。')
sub('迭代约束如何落到代码','任务状态机新增/完善交付下降、地面确认、释放等待、再次解锁等阶段；只有收到符合时序的反馈才推进。故障场景必须停留地面，避免“释放命令发出”等于“释放成功”的错误。')
sub('验证与人的作用','参赛者提出服务过程的核心纠正，AI修改状态机、机构反馈和测试并报告结果。相应原文完整导出保留AI进度与答复，不补写参赛者未说过的追问。后续业务台账联调继续验证该流程。')
p('来源：01_着陆交付流程.txt/json。该功能早于新Git基线；不是2026-11-14首次实现。当前业务联调同时验证正常交付与卸货失败。')
diagram(['发现语义缺口','明确下降交付','修改状态机','正反用例','反馈结果'])

page('13 协作链二：打通订单与资源','ORIGINAL DIRECTION / BUSINESS ITERATION')
p('参赛者原文：“我觉得这个项目，目前还是很像玩具项目，该怎么改进呢”；在AI给出建议后，参赛者批准：“你说的很有道理，开始改进吧”。','sub')
p('AI复查发现网页传递坐标后，飞行结果没有回写订单、库存和运力。于是实施台账、预占、取消、失败核对恢复，并将同一流程接入网页与桌面。总体服务目标由人提出，模块拆解和代码细节由AI辅助实现。')
sub('实际问题与反馈','联调中场景载入回执时间戳导致解锁检查失败，AI定位并修复。正常交付后核对订单送达与运力释放；卸货拒绝时确认库存继续预占，并验证人工恢复仅返库一次。原始对话中15项和105项是当时进度，最终17项业务检查和123项自动测试为后续结果。')
p('Git对应：5427ac5（业务台账联动）、04ca099（网页和桌面订单入口）。源码：backend/flight_orders.py、autonomy/engine.py。证据：reports/business-acceptance.json。')
p('来源：02_订单库存与执行闭环.txt/json，包含问题、建议、批准、进度与最终回复。完整工具日志未全部导出；对应实现可通过Git差异与验收脚本复核。','small')

page('14 协作链三：外部验证与失败分析','ORIGINAL APPROVAL / SAFETY ITERATION')
p('参赛者原文：“haiyou还有什么可以改进”；AI建议独立飞控仿真、安全解释、固定对比后，参赛者批准：“好的，你做吧”。','sub')
p('AI检查代码时发现只读模式仍可能发保护控制，以及断链后的落地判断不够严格。按真实代码边界修正后加入专项测试，再使用官方ArduCopter SITL检验协议与外环控制。')
sub('保留失败，不用故事代替验证','普通与风扰场景完成，但动态障碍6例均保护停止。初版固定测试使用3米缓冲，与业务4米不一致；统一后仍保留初始文件。这属于评测参数纠正，不包装为算法性能提升。')
sub('过程与结果如何对应','Git f1e1cb3记录安全修改，f373ba9记录SITL验收，111ab3e记录固定场景与图文证据。报告保存种子、步长、源码哈希、路径与失败原因；网页提供相同证据入口。')
p('来源：03_安全保护与官方飞控评测.txt/json；reports/official-sitl-acceptance.json、fixed-benchmark.json。该链是在一次持续批准任务内完成多个技术环节，没有伪造额外的人工中途追问。','small')

page('15 测试设计与本轮结果','EVIDENCE / SAMPLES / LIMITS')
bars([('普通配送与风扰',12,12),('动态障碍完成',0,6),('故障预期状态',4,4)])
p('固定评测三个种子17、42、89；三个场景；启用/关闭跟踪配对，共18次正常任务。另加入感知中断、定位质量下降、断链、低电量4次故障任务，共22次；步长0.05秒，单次上限240模拟秒。')
p('12次普通与风扰任务完成；6次动态障碍保护停止；4次故障案例进入预期状态。22次简化模型未记录碰撞。动态障碍保护停止不能计作配送成功；启用跟踪尚未证明完成率优势。')
p('自动测试123项通过、1条警告；自建MAVLink业务联调17项通过；网页专项5项通过。自动测试覆盖状态、资源、协议和边界，不等同于123次飞行。官方SITL另有18项检查，在下一页说明。')
p('路径误差相对当前规划航线计算；能耗为未标定模型；离线计算耗时不等于在线控制周期。固定种子回归集与实际城市场景存在分布差异，应保留失败作为后续改进目标。')
p('证据：reports/fixed-benchmark.json、business-acceptance.json、safety-ui-check.json；完整复现实验入口见README.md。','small')

page('16 官方飞控软件在环验证','ARDUCOPTER SITL / INDEPENDENT CHECK')
diagram(['官方飞控启动','GUIDED与解锁','5米起飞','速度目标','降落返航'])
p('程序来自ArduPilot官方Windows SITL发布目录，下载清单逐文件记录URL、字节数和SHA256。验收脚本只启动自己的本机ArduCopter子进程，不使用任意外部飞控地址，不绕过飞控解锁检查或强制解锁。')
p('等待GPS与EKF准备，验证心跳定位、无效模式被拒绝、GUIDED模式、解锁回执、5米起飞、速度外环目标跟踪；停止速度指令但保持心跳后检查自动减速，再落地停桨，地面停留、再次起飞与返航落地。')
p(f'本轮{len(official["checks"])}项验收通过。地面停留只代表流程等待，不代表真实货物释放；官方SITL没有验证完整订单台账与投放机构。相应业务流程由自建模拟器联调单独验证。')
p('官方二进制指纹：'+official['firmware_sha256'],'small')
p('来源：https://firmware.ardupilot.org/Tools/MissionPlanner/sitl/Stable/；参数与许可证来源github.com/ArduPilot/ardupilot。详见third_party/ardupilot_sitl/manifest.json、SOURCE.txt及官方GPL许可。','small')
p('证据：tools/sitl_acceptance.py；reports/official-sitl-acceptance.json。重新运行前确保TCP15770及RC15779空闲。','small')

page('17 十分钟启动与演示路径','REPRODUCTION / LOCAL DEMO')
sub('评审使用完整运行包','Windows 10/11 64位，建议8GB内存，Edge/Chrome支持WebGL。完整包包含Python/Tk与静态资源；解压后可独立运行。工作目录原有联接不直接作为便携交付。')
p('步骤一：完整解压至可写目录，确保没有其他副本占用19051、19052及UDP18751。步骤二：运行“启动网页平台.cmd”，用admin与演示密码GreenFlight2026!登录；运行“启动独立飞行软件.cmd”可打开桌面。')
p('步骤三：连接模拟器、获取操控权，选择待调度订单并预检，载入任务、等待遥测、解锁、开始。没有待调度订单时先创建公共取件点订单。步骤四：观察着陆卸货与返航，核对订单、库存和飞机状态。')
p('停止前确认落地；使用“停止本项目服务.cmd”。十分钟范围为解压、启动与基本演示，不包括全部测试和重新训练。独立新解压验收记录见reports/clean-start-verification.json；其中记录实际耗时、环境和检查结果。')
p('本机新解压验证已通过：解压12.94秒、启动网页健康21.72秒；连同桌面启动与17项业务联调总计180.05秒。该耗时来自本机一次运行，不保证所有电脑相同。','small')
p('正式说明与命令：README.md；环境变量参考.env.example。程序不会自动加载.env；启动脚本将数据库固定到本副本data/community.db。演示账号初次建库时生成，修改环境密码不会自动重置既有账号。')

page('18 复现性、版本与依赖','REPRODUCIBILITY / TRACEABILITY')
sub('代码状态可定位','f04b4d8是已有平台基线；之后按业务闭环、交互、安全、SITL与固定评测提交。本轮没有补造早期提交。完整包保留本地Git，尚未发布远程仓库。复核可使用git log与git show指定提交。')
sub('场景输入与源码指纹','固定评测记录种子、步长、版本和关键源码SHA256。相同输入可回归确定性飞行指标；计算耗时随机器负载变化。源文件哈希比只有Git标题更适合确认运行的具体内容。')
sub('模型生成不保证逐字一致','对话记录说明意图控制与改进过程；同一Prompt重新调用大模型可能得到不同代码。可复现性在此区分为：检出已保存代码、固定输入重跑功能、检查真实对话证据，不能声称大模型生成过程具有逐字确定性。')
p('requirements-lock.txt保留当前Python依赖，vendor提供静态库，SITL恢复脚本校验下载哈希。运行包不含原控制密钥、旧PID或缓存，首次启动按新目录创建本地配置。第三方许可需随分发保留，导师素材来源另行说明。')
p('依赖与来源：requirements.txt/requirements-lock.txt、docs/第三方资源说明.txt、third_party/ardupilot_sitl/manifest.json。','small')

page('19 原创贡献、局限与改进计划','CONTRIBUTION / NEXT STEPS')
sub('本项目的工程贡献','将社区业务预检和资源台账、飞行状态机、MAVLink通信、网页桌面共同状态、完整交付和故障处置组织为可运行系统；加入分层验证与失败证据。A*、α–β跟踪、反馈控制等采用已有方法，不宣称提出全新基础算法。')
sub('参赛者与AI的实际贡献','参赛者负责总体方案、技术与算法方向、功能目标、界面要求、反馈与迭代取舍。AI辅助实现代码、集成与修复、编写运行检查并整理证据。已有团队成果应按真实来源说明，个人赛贡献与授权需据实际确认。')
sub('尚未解决的问题','动态障碍任务需要等待、重规划和恢复策略；真实地面交付区感知与机构回执尚缺；多机并发和更复杂地图未完成；持久化与较重计算仍需进一步从控制循环隔离。官方SITL与完整业务链还需进一步集成。')
p('真实传感器、硬件在环与实机飞行尚未验证。当前落点、动力学与能耗模型均有简化，软件急停不替代独立硬件安全保障。后续改进应在可审查的代码与试验中记录，不通过增加算法名称扩大能力表述。')
p('本报告引用的源代码、JSON报告与原始对话随包提供。三条协作链是所选回合的可见文本导出，不代表全部项目历史；阅读顺序：README → 技术报告 → 对话与Git → 运行评测。','small')

def decorate(c,doc):
 w,h=doc.pagesize;c.setFillColor(GREEN);c.rect(0,h-14,w,14,fill=1,stroke=0)
 c.setFont(F,9);c.setFillColor(TEAL);c.drawString(48,h-38,'晴空邻里 / 软件创新技术报告')
 c.setStrokeColor(HexColor('#dce6df'));c.line(48,38,w-48,38)
 c.setFont(F,8);c.setFillColor(INK);c.drawString(48,24,'2026-11-14  |  软件仿真研究原型  |  真实协作与运行证据')
 c.drawRightString(w-48,24,str(doc.page))

dest=OUT/'晴空邻里_软件创新参赛技术文档_20261114.pdf'
doc=SimpleDocTemplate(str(dest),pagesize=(595.28,841.89),rightMargin=52,leftMargin=52,topMargin=60,bottomMargin=53,title='晴空邻里 软件创新参赛技术文档',author='晴空邻里项目')
doc.build(story,onFirstPage=decorate,onLaterPages=decorate)
print(dest)
(OUT/'技术文档章节索引.txt').write_text('\n'.join(pages),encoding='utf8')
