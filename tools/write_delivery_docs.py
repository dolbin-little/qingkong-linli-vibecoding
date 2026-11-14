from pathlib import Path
import json,html,importlib.metadata as metadata
R=Path(__file__).resolve().parents[1]
docs={
'README.txt':'''晴空邻里——面向未来城市的绿色低空共享服务交互平台
自主飞行协同版 / 2026-11-05

这是在“绿航智递”基础上新建的独立版本。原项目文件未修改、未删除。
新增网页飞行任务舱、独立Windows飞行软件、独立飞行服务与MAVLink模拟飞控。
订单与共享物品、微站、机队、光储充、调度实验和精细产品模型继续保留。

【直接运行，Windows 10/11 64位】
1. 解压整个文件夹到有写权限的位置；不要直接在压缩包内启动。
2. 双击“启动全部.cmd”：打开独立飞行软件并启动网页服务。
3. 浏览器打开 http://127.0.0.1:19051/ 。管理员：admin / GreenFlight2026!
   也可双击“启动网页平台.cmd”直接打开浏览器。
4. 网页与桌面任选一个操控端：连接模拟飞控 → 获取操控权 → 载入任务/场景 →
   等待遥测刷新 → 飞前解锁 → 确认已解锁 → 开始执行。
   正常场景会爬升、跟踪航点、在交付点悬停、返航并降落，约需1至3分钟。
5. 首次运行如出现Windows防火墙网络询问，本机演示无需开放公共网络，选择取消即可。

【三个入口】
启动全部.cmd：网页服务 + 独立飞行服务 + 模拟飞控 + 桌面窗口。
启动网页平台.cmd：网页服务 + 独立飞行服务 + 模拟飞控。
启动独立飞行软件.cmd：独立飞行服务 + 模拟飞控 + 桌面窗口，不依赖网页。
重复启动会识别本项目已运行进程；不终止其他项目、浏览器或Python程序。
“停止本项目服务.cmd”仅停止本文件夹记录且路径匹配的进程。先完成降落再停止。

【运行条件】
已附便携Python、Tk/Tcl及依赖，无需另装Python或Node，也不需要联网下载网页库。
建议8GB内存；浏览器支持WebGL。3D不支持时会退回俯视图。
端口：19051网页、19052本机飞行服务、UDP18751模拟飞控。默认都只绑定本机。
运行记录保存在本项目data、logs、reports内。首次会生成本机控制密钥与演示数据库。
外部设备接入前请阅读“docs/无人机接入与验证边界.txt”。

【本次能力】
网页：飞行任务舱、感知时效、规划控制、保护与接管、云边成本比较、测试回放、技术溯源。
软件：独立窗口、MAVLink串口/UDP连接、遥测、GUIDED解锁/速度控制、返航/降落、
人工低速接管、全球航点上传握手、故障注入、回执和报告导出。
研究：2.5D A*与净空检查、位置/速度反馈外环、α–β跟踪、保护状态机、能源预算、
任务优先级成本选择、残差异常线索、分层哈希记录。

【验证层级】
已完成Windows便携环境、自建MAVLink模拟飞控与飞行服务联调。
未完成真实无人机、ArduPilot/PX4官方SITL、硬件在环、实地自动飞行或适航认证。
不是任意品牌无人机插上就能自主飞行的通用产品；DJI等闭源设备没有适配。
机载电池为主供能，太阳能为参数化的辅助补能；不宣称太阳能支撑多旋翼持续飞行。
论文与专利仅作明确记录的方法借鉴，不将导师既有成果列为本项目新发表或新授权成果。

详细操作、架构、来源和验收证据请见docs与reports。
''',
'docs/平台与飞行软件使用说明.txt':'''晴空邻里：平台与独立飞行软件使用说明

一、演示顺序
建议先用“邻里共享配送”，保持独立模拟任务和种子42。
连接模拟飞控后应出现新鲜心跳、定位、GPS、测距和电量。
获取操控权：网页和桌面之间同一时间只有一个端持有租约；持有端会自动续期。
切换操控端前先释放操控权，再从另一端获取。停止网页或关闭桌面不会停止飞行服务。
载入任务：在未解锁状态建立航线并复核净空，模拟器同步复位。
飞前解锁：检查传感器、定位质量、电量与往返预算，然后请求GUIDED模式和解锁。
飞控实际心跳确认解锁后才显示“已解锁”，不能把按钮点击当作已成功。
开始执行：依次跟踪三维航点；交付点悬停2秒后返航。未控制真实物品释放机构。
完成降落后会保存flight-*.json，控制轨迹同时写入trace-*.jsonl。
正常任务不改变原社区订单为真实送达；关联的是订单快照与模拟执行记录。

二、网页各页
1. 飞行任务舱
研究场景：配送、动态障碍、风扰、低电量、感知中断、链路中断、定位下降共7类。
故障类场景约在启动模拟后11秒自动注入故障，目的在于查看保护行为。
关联共享订单：将社区1000×700米平面订单归一映射到100×80米测试场景。
映射坐标只用于研究演示，不能直接解释成实际GPS坐标。
随机种子：保持相同输入以复现实验；当前只影响轻微风扰，不代表所有测量完全确定。
3D：拖动旋转、滚轮缩放，观察遥测驱动的概念无人机、微站和已知建筑。
俯视：同一飞行状态的二维地图。绿线为收到的轨迹，金线为规划航线。
飞行器放大显示；三维模型是产品结构概念，不是传感器重建或制造图。
导出本次运行记录：保存当前遥测快照与最近约60秒轨迹；完整JSONL在logs中。
2. 环境感知
显示心跳、局部位置和测距时效、GPS质量、跟踪目标与统计异常线索。
当前不执行摄像头神经网络识别。动态场景通过模拟MAVLink扩展传入含噪位置测量。
外部检测可调用本机飞行接口，由跟踪器融合；支持格式见架构说明。
3. 规划与控制
查看2.5D A*、位置外环及速度反馈的方法说明，当前航点和COMMAND_ACK。
接受回执表示飞控接受命令，不等于动作已经完成；飞行状态以遥测更新。
4. 安全与接管
安全悬停：发送零速度并暂停航点，不在空中切断电机。
自主返航：从当前位置重新规划回微站。走廊不可达时保护转降落。
受控降落：请求飞控LAND，持续检查遥测；地面确认后才记落地。
移交人工模式：暂停自动航点；方向操作由桌面W/S/A/D及R/F提供。
释放操控权：移交其他控制端；不会自动停止已运行的自主任务。
落地后故障复位：必须未解锁且故障条件已消失；随后重新载入任务。
模拟器故障注入：测距、定位、电量、遥测或ACK丢失，仅本机模拟器可用。
清除注入：恢复模拟遥测；不会自动恢复飞行。链路中断时先清除注入再确认落地。
5. 机载与云边协同
展示候选节点计算/传输时延及截止时间，关键控制固定本地。
勾选云资源只改变成本比较，不会将飞行控制发往公网，不是真实远程作业集群。
哈希链显示飞行记录与检查点；这是本机可校验日志，不是部署完成的区块链网络。
6. 测试评价与回放
读取记录后选择flight-*.json播放轨迹；测试JSON可显示原始数据。
回放不向飞控发送动作，点击“回到实时”恢复直播状态。
成功、保护中止和早期失败记录均保留，不将保护落地计作配送成功。
7. 技术来源与创新
逐项显示参考成果、实现文件、采用层级和未实现的部分。
8. 社区共享服务、精细产品模型、产品结构图册
分别打开保留的原平台业务副本、交互模型和结构展示。业务仿真与飞行服务是不同状态源。
社区演示账户resident的密码同管理员，但没有飞行控制权限。

三、独立桌面软件
上方按钮与网页的连接、租约、载入、解锁、开始、悬停、返航和降落对应。
人工接管：解锁且已取得桌面操控权后进入人工模式；W/S沿N正负方向，A/D沿E负正方向，
R/F上升下降，空格归零。松开后约0.35秒指令失效归零；速度限幅1.5m/s。
按键仅在窗口有焦点且处于人工模式时有效；不支持手柄或真实遥控器接管检测。
接入其他飞控：输入串口名或MAVLink UDP地址，波特率默认115200。
上传全球航点：选择包含lat、lon、alt的JSON数组，只上传，不自动解锁或进入AUTO。
允许真实写控制：本机配置开关与完整确认语句双条件，网页不能完成此操作。
保存运行报告：导出当前桌面快照，长期任务轨迹仍以logs内JSONL为准。
窗口关闭后服务继续运行；再次启动桌面会重新附着同一服务。

四、异常处理
连接拒绝：先启动本项目服务；检查logs/worker.log、simulator.log、web.log。
操控权占用：原端释放或关闭后等待最多20秒；不要重复强制解锁。
飞前检查失败：先看原因与时效，不能跳过定位、水平测距或电量校验。
故障注入后无法再次解锁：先清除注入、待落地，再重新载入场景；低电量需场景复位。
链路丢失后显示已解锁：这是最后一次已知状态，不代表仍在空中。恢复遥测后再核实。
模拟器独立兜底不等于真实设备兜底；真实飞控需自身配置失联、低电量和遥控保护。
3D空白：切俯视图，或使用支持WebGL的Edge/Chrome。
端口冲突：启动器会提示，不会终止其他项目；不要修改正在飞行的进程。
''',
'docs/无人机接入与验证边界.txt':'''无人机接入说明与验证边界

当前实现的是MAVLink地面站/伴随控制软件原型，含真实串口与UDP协议适配代码。
Windows便携环境已加入pymavlink和pyserial。不能据此声称已验证任何真实机型。

一、支持的接口
串口示例 COM5，115200波特；UDP示例 udpin:127.0.0.1:14550 或 udpout:设备IP:14550。
本机模拟器专用地址 udpout:127.0.0.1:18751，其他地址一律先进入真实设备只读路径。
连接后接收HEARTBEAT、LOCAL_POSITION_NED、SYS_STATUS、GPS_RAW_INT、DISTANCE_SENSOR、
ATTITUDE、COMMAND_ACK。外部连接会尝试协商相应消息频率，飞控可能拒绝未支持的消息。
设备必须确实提供有效定位、水平测距和剩余电量；不会用默认95%电量通过飞前检查。
GPS、位置、电量、测距各自有时效保护；卫星数量255表示未知，不能用于起飞确认。
当前写控制针对ArduCopter GUIDED设计，发送速度外环指令，让原飞控执行姿态和电机内环。
PX4的OFFBOARD建立、模式序列与起飞流程未适配；DJI等厂商SDK也未适配。

二、接入顺序
1. 先在无桨台架或合适的软件在环环境接入遥测，不启用真实写控制。
2. 在飞控地面站核对消息、飞行模式、电量、定位、水平测距、遥控器与链路失效参数。
3. 校准局部坐标与实际障碍地图。系统内部为N/E/U米，MAVLink为N/E/D，垂直轴转换符号。
   config/project.json的external_position_offset_neu仅平移局部位置，不改变速度。
   例如只有在确认EKF原点正好位于测试微站时，才可能使用[10,10,0]映射到示例场景。
   当前默认[0,0,0]，故不会假定任意EKF原点就是微站。示例建筑不能作为实地障碍地图。
   真实场地应替换autonomy/models.py中边界、微站、航点及障碍，并验证每段净空。
4. 经台架、官方SITL/硬件在环验证后，才考虑受控场地的低风险试验。
5. 如需写控制，在本机将real_control_enabled设为true，重连外部设备，再由桌面输入：
   确认场地安全并保留遥控接管
   保留原飞控飞前检查，不发送强制解锁，不实现空中强制断电。
6. 飞控必须具有实际的人工接管、失联保护、低电量保护与独立安全手段。
   本软件的“安全悬停/受控降落”是软件请求，不是独立硬件急停，也不是安全认证。

三、全球航点上传
JSON格式：[{"lat":24.966,"lon":102.866,"alt":12}, ...]。
以上坐标仅为协议示例；alt是GLOBAL_RELATIVE_ALT相对高度，范围1至35米。
实现COUNT→REQUEST_INT/REQUEST→ITEM_INT/ITEM→ACK握手及超时重传。
上传成功只代表飞控接受任务，不启用AUTO，不自动起飞，也不把全球航点变成局部场景航线。
不要把本地100×80米坐标当成经纬度。

四、验证层级与未完成事项
已验证：自建模拟飞控、标准MAVLink消息、Windows进程通信、保护状态与任务记录。
未验证：真实通信链路及射频干扰、真实推力/动力学、官方SITL/HIL、具体机型、实际传感器、
地图重建、视觉目标识别、精确着陆、实物投送、法定空域及运营流程。
自建模拟器没有飞控姿态内环、空气动力学、电机故障模型或真实传感器误差分布。
所以不能把模拟器的无碰撞、耗电和到达时间作为实机性能或商业服务承诺。
''',
'docs/系统架构与模块说明.txt':'''晴空邻里系统架构与模块说明

网页(FastAPI+HTML/CSS/JavaScript+Three.js)
       ↓ 管理员会话、同源校验、命令网关
独立飞行服务(Python/ThreadingHTTPServer，127.0.0.1:19052，20Hz外环)
       ↑ Tkinter桌面软件：与网页共用操控权租约，关闭网页仍能运行
       ↓ MAVLink UDP/串口；遥测上行、指令及ACK下行
模拟飞控(独立进程) 或 外部ArduCopter接口(默认只读)

一、模块
sky_platform.py：复用原社区FastAPI后端，增加管理员飞行接口、报告和技术来源。
frontend/sky.*：新任务舱与研究页面；sky-scene.mjs用遥测驱动已有精细产品几何。
desktop/console.py：Windows独立GUI，异步RPC、遥测、地图、接管、全球航点上传。
autonomy/worker.py：独立控制服务，随机本机密钥、请求体限制、拒绝浏览器跨源直连。
autonomy/engine.py：任务状态机、租约、航点跟踪、返航、保护、完成记录。
autonomy/mavlink_adapter.py：标准消息、目标系统锁定、NEU/NED转换、ACK和任务上传。
autonomy/simulator.py：独立一阶动力学、速度滞后、加速度限幅、风扰、电池与看门狗。
autonomy/planning.py：2.5D A*，0.5米采样逐段净空复核，位置P/速度反馈及加速度限幅。
autonomy/perception.py：输入原子校验、α–β跟踪、目标失效剔除、相对运动最近距离。
autonomy/safety.py：独立保护，不依赖残差统计分数或云端结果。
autonomy/research.py：优先级时限成本枚举、稳健残差线索、SHA-256事件链和检查点。
backend/*：保留原订单、库存、VNS–MILP调度、DQN候选排序及光储充LSTM/MPC研究。

二、坐标与数据边界
社区业务图为1000×700米，飞行测试场为100×80米，高度上限35米。
原业务订单经归一化成为研究目标点，仍须通过新地图净空检查；落在建筑缓冲区会拒绝。
飞行内部坐标[N,E,U]；Three场景[x,y,z]=[N,U,E]；MAVLink为[N,E,D]。
速度指令只使用LOCAL_NED的vx/vy/vz，type_mask=0x0DC7。
位置偏移只用于经标定的外部局部原点映射；地理经纬度上传与局部自主控制相互独立。

三、状态机
DISCONNECTED→CONNECTING→CONNECTED→READY→ARMING→ARMED→EXECUTING。
交付点悬停后RETURNING→LANDING→COMPLETED。
异常保护进入HOLD、RETURNING或LANDING；未完成配送的落地记STOPPED，保留原因。
模式/解锁确认超过5秒会取消待解锁流程；保护悬停也会取消排队中的解锁请求。
来自飞控的意外解除电机会终止活动任务，不继续假装执行。
租约过期禁止新的主动操作，但不终止已在运行的自主任务。
软件并非硬实时系统，20Hz是目标频率，真实周期与最坏周期保存在运行统计中。

四、安全监控
心跳>2秒请求LAND；局部位置>.8秒、水平测距>1秒先HOLD；GPS>2秒、电量>3秒陈旧也保护。
GPS等级不足、临界电量<=15%请求降落；电量<=25%请求返航；起飞电量必须>=45%。
已返航时允许在保留电量保护下继续返航指令，<=15%仍优先降落。
围栏、建筑缓冲、速度/停止距离和下一步走廊会独立复核。
保护悬停持续2.5秒未解除后转受控降落。
真实机上的LAND/RTL执行仍取决于飞控、传感器、场地与通信。

五、感知来源
模拟器的DISTANCE_SENSOR来自合成几何；动态物体通过DYN_N/E/U NAMED_VALUE_FLOAT发送
带噪位置样本，这是本模拟器扩展，不是通用无人机目标检测协议。
引擎只消费测量/检测输入，不读取data/simulator-truth.json进行规划。
truth文件仅供评价器判定碰撞、里程、能耗；与感知数据明确分离。
外部检测接口：POST本机19052/command，X-Sky-Key取自config/local-control.key。
示例JSON：{"command":"detections","owner":"desktop","data":{"detections":[
{"id":"target1","position":[40,30,12],"radius":2}]}}
输入坐标必须在与飞行场景相同的NEU参考系中；当前没有相机/雷达标定适配器。
跟踪预测风险触发动态A*绕行；无可行路径则保护悬停，不能保证任意动态障碍都可绕过。

六、记录
logs/flight-chain.jsonl：飞行事件哈希链；edge-checkpoints.jsonl：关键检查点。
logs/trace-*.jsonl：逐次记录任务轨迹；reports/flight-*.json：完成/终止快照与至多约600秒轨迹。
网页实时导出为近60秒快照；长任务完整轨迹以JSONL为准。
单机管理员可以同时改写链和检查点，本地哈希链不能抵抗这一攻击，不宣称分布式不可篡改。
''',
'docs/本次改进清单.txt':'''本次从绿航智递到晴空邻里的改进

1. 独立E盘副本：保留原D盘项目。新端口与已有环卫软件隔离，不结束其他项目进程。
2. 产品定位：将社区共享订单、微站、无人机和光储充串成未来城市绿色低空服务过程。
3. 新网页：7个飞行研究功能页、遥测驱动3D场景、2D切换、原社区服务/模型/图册入口。
4. 新Windows软件：可单独启动、接入串口/UDP、查看遥测和回执、人工接管及航点上传。
5. 独立飞行进程与模拟飞控：网页停止后控制服务继续运行，不把网页动画当作飞行执行。
6. 控制与规划：A*、起降走廊复核、速度反馈和限幅、任务与返航状态机。
7. 感知与避障：传感器时效、检测输入、跟踪与动态路径重规划，无法绕行时保护。
8. 保护：围栏、电量、定位/测距/心跳、人工移交、模式确认超时、取消待解锁、意外解除电机处理。
9. 真实协议适配：ArduCopter GUIDED、MAVLink遥测协商、串口/UDP、全球航点握手。
   接口已实现；真实机型、官方SITL和硬件在环尚未验证。
10. 论文/专利迁移：任务优先级成本模型、残差线索、双层日志，均记录原始来源和实现边界。
11. 评价：保留正常完成、保护中止、ACK丢失及早期低电量返航失败记录，增加回归测试。
12. 便携交付：附Python/Tk运行环境、启动/停止脚本、使用与接入说明、依赖来源和验收证据。

不把本次工程集成描述成原创A*、原创MAVLink、复现DR-GGAD或完成双层区块链专利。
当前系统仍需真实场地地图、具体飞控、传感器和安全配置后才能开展对应实机验证。
''',
}
for filename,content in docs.items():
    p=R/filename;p.parent.mkdir(exist_ok=True,parents=True);p.write_text(content,encoding='utf-8-sig')

sources=json.loads((R/'docs/技术来源与实现对照.json').read_text(encoding='utf-8'))
sources[1]['use']='从双残差信号融合获得启发，新增遥测特征稳健中心残差与偏差统计。当前未提供图邻居时以稳健中心代替邻域输入，仅提供异常线索。'
(R/'docs/技术来源与实现对照.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2),encoding='utf-8')
(R/'docs/技术来源与实现对照.txt').write_text('\n\n'.join('\n'.join(str(x.get(k,'')) for k in ['title','url','level','use','files','boundary']) for x in sources),encoding='utf-8-sig')

packages=[]
for name in ['fastapi','starlette','uvicorn','numpy','scipy','pydantic','httpx','pytest','paho-mqtt','pymavlink','pyserial','fastcrc','lxml']:
    d=metadata.distribution(name);packages.append({'name':name,'version':d.version,'license':d.metadata.get('License-Expression') or d.metadata.get('License') or '见对应dist-info许可文件','source':d.metadata.get('Home-page') or 'https://pypi.org/project/'+name+'/'})
(R/'docs/第三方依赖清单.json').write_text(json.dumps(packages,ensure_ascii=False,indent=2),encoding='utf-8')
notice='''第三方资源与版本说明
便携Python来自原平台交付包，新增Tk/Tcl运行库来自本机Codex配套Python；Python为PSF许可，Tk/Tcl保留原许可。
pymavlink、pyserial、lxml、fastcrc通过Python官方包索引安装；pymavlink为LGPL协议，pyserial为BSD许可；
完整依赖自身的LICENSE/COPYING等文件保留在runtime/python/Lib/site-packages的相应目录和dist-info内。
Three.js及OrbitControls沿用原项目本地vendor，保留其MIT许可。新增平台不依赖在线CDN。
原平台的产品/场景几何、设计图、模型参数与原程序一并作为既有工程基础保留。
本次未下载导师的训练权重或复制其论文源代码；来源链接与方法迁移另见技术来源对照。
论文与专利权利不因本项目引用而转移；文献中的实验结果不作为本项目实测。
本次新增工程代码、测试、文档由AI辅助开发与整理，参赛材料应如实记录实际采用部分。
以下版本根据本交付运行环境直接读取，不是宣称最新版本。
'''
notice+='\n'.join(x['name']+' '+x['version']+' / '+str(x['source']) for x in packages)
(R/'docs/第三方资源说明.txt').write_text(notice,encoding='utf-8-sig')
lock=R/'requirements-lock.txt';base=lock.read_text(encoding='utf-8').splitlines();base=[x for x in base if x and not any(x.startswith(n+'==') for n in ['pymavlink','pyserial','fastcrc','lxml'])];base += [n+'=='+metadata.version(n) for n in ['pymavlink','pyserial','fastcrc','lxml']];lock.write_text('\n'.join(base)+'\n',encoding='utf-8')
req=R/'requirements.txt';text=req.read_text(encoding='utf-8');text+='\n'.join(n+'=='+metadata.version(n) for n in ['pymavlink','pyserial'] if n not in text)+'\n';req.write_text(text,encoding='utf-8')
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>晴空邻里 · 开始使用</title><style>body{background:#f2f6ec;color:#234d48;font:17px/1.9 "Microsoft YaHei",sans-serif;margin:0;padding:8vw}main{max-width:1000px;margin:auto}small{color:#7f9783;letter-spacing:3px}h1{font-size:46px;line-height:1.3}h2{margin-top:45px}article{padding:30px 40px;border:1px solid #dfe8da;background:#fff;border-radius:18px;margin:25px 0}b{color:#297e6e}a{color:#2d8978}li{margin:13px 0}code{background:#edf3e6;padding:4px 10px;border-radius:5px}footer{font-size:14px;color:#829486;margin-top:50px}</style><main><small>SKY COMMONS / FUTURE NEIGHBORHOODS</small><h1>晴空邻里<br>让每一次抵达，都有依据。</h1><p>面向未来城市的绿色低空共享服务交互平台 · 自主飞行协同版</p><article><h2>开始演示</h2><ol><li>先解压完整文件夹，双击<b>启动全部.cmd</b>。</li><li>打开<a href="http://127.0.0.1:19051/">网页工作台</a>，账号<code>admin</code>，密码<code>GreenFlight2026!</code>。</li><li>任选网页或桌面，依次点击：<b>连接模拟飞控 → 获取操控权 → 载入任务 → 飞前解锁 → 开始执行</b>。</li><li>观察起飞、航点跟踪、交付点悬停、返航与受控降落；在评价页回放记录。</li></ol><p>默认只绑定本机，无需开放公共网络。若弹出防火墙访问询问，本机演示可选择取消。</p></article><article><h2>软件与平台各自负责什么</h2><p>网页负责城市服务、任务管理、三维监控和评价；独立桌面软件提供遥测、操控、接管与航点上传；飞行服务独立于二者运行，经MAVLink连接模拟飞控或外部设备。</p><p><a href="docs/平台与飞行软件使用说明.txt">详细使用说明</a>　·　<a href="docs/无人机接入与验证边界.txt">无人机接入</a>　·　<a href="docs/系统架构与模块说明.txt">系统架构</a>　·　<a href="docs/技术来源与实现对照.txt">论文与专利技术来源</a></p></article><article><h2>看到的结果，对应什么验证</h2><p>已验证Windows本机与自建MAVLink模拟飞控链路。真实ArduCopter接口默认只读，需校准地图与坐标并逐机验证。当前没有官方SITL、硬件在环或实地无人机飞行验收。</p><p>模型、光伏功率和耗电均为研究假设，实物投送机构未接入。成功、保护落地及失败记录分别保留。</p></article><footer>原D盘项目保持原样。新版全部位于E盘独立文件夹。请先降落，再运行“停止本项目服务.cmd”。</footer></main></html>'''
(R/'使用说明.html').write_text(page,encoding='utf-8')
print('delivery docs written',len(docs)+6)
