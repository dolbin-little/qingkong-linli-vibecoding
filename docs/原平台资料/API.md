# API 与数据接口

交互式接口说明由 FastAPI 自动生成，服务启动后访问 `/docs`。根目录之外的文件不作为静态资源暴露。前端通过同源 API 访问。

## 身份

`POST /api/login` 接收 username/password，设置 12 小时 HttpOnly、SameSite=Strict 会话 Cookie。密码为随机盐 PBKDF2-SHA256（200000 次）散列。`POST /api/logout` 注销数据库会话。`POST /api/register` 创建居民账号，不能自选管理员角色。

管理员可操作设备、调度、仿真与导出。居民只能读取自己的订单并操作自己的配送/回收请求。变更请求拒绝跨域 Origin。默认只绑定 loopback；对外部署前必须设置 TLS、正式账号管理、受信代理和部署配置。

## 常用接口

| 方法与地址 | 用途 |
| --- | --- |
| GET /api/health | 健康检查 |
| GET /api/state | 当前状态、订单、地图、设备、指标、当前用户 |
| GET /api/pickup-points | 六处公共取件点及当前禁飞区下的 available 状态（需登录） |
| POST /api/orders | 模拟支付并创建配送订单 |
| POST /api/orders/{id}/cancel | 取消待调度配送订单并模拟退款 |
| POST /api/orders/{id}/return | 创建回收子订单 |
| POST /api/dispatch | method 为 vns / greedy / dqn / aco |
| POST /api/simulation | start / pause / advance / cloud / auto |
| POST /api/weather | 更新模拟天气，无在途航班时允许 |
| PATCH /api/stations/{id} | 在线状态或库存补充 |
| PATCH /api/drones/{id} | 待命/维护状态切换 |
| POST /api/zones | 添加矩形禁飞区 |
| DELETE /api/zones/{id} | 移除禁飞区 |
| GET /api/energy | 实时计算 MPC 充电计划 |
| GET /api/learning | DQN 与光照预测模型训练信息 |
| POST /api/scenarios | 随机种子生成订单 |
| POST /api/experiments | 独立同场景三算法实验 |
| GET /api/export/orders | 订单 CSV（UTF-8 BOM，防公式注入） |
| GET /api/export/experiments | 实验 JSON |
| POST /api/reset | confirmation=RESET_DEMO，备份后重置仿真 |

创建订单示例：

```json
{"product":"powerbank","quantity":1,"pickup_point_id":"P01","priority":1,"deadline_minutes":6}
```

`GET /api/state` 同时返回 `pickup_points`。预设地点提交编号即可，服务端统一确定名称和坐标；即使请求额外携带不同的地址或坐标，也以编号对应的数据为准。未知编号、缺少位置、禁飞区内或越界坐标返回 422。

网页地图自定义位置及旧客户端仍可提交 `x`、`y`、`address`，例如 `{"product":"powerbank","quantity":1,"x":280,"y":250,"address":"地图取件点（280, 250）"}`。此时不提供 `pickup_point_id`。预设地点编号为 P01 至 P06；可用性随当前禁飞区计算，不代表真实空域许可。

数据库采用 SQLite 单状态快照事务，进程内锁与 `BEGIN IMMEDIATE` 保证一个服务进程中的操作原子性。当前只支持单 uvicorn worker；不要启用多个 worker，因为每个进程都会启动仿真时钟。生产规模应将状态拆分规范化表并使用独立任务调度器。

## MQTT 只读遥测

```powershell
$env:GREENFLIGHT_MQTT_HOST = '你的测试 broker'
$env:GREENFLIGHT_MQTT_PORT = '8883'
$env:GREENFLIGHT_MQTT_TLS = '1'
# 用户名密码通过环境变量 GREENFLIGHT_MQTT_USERNAME / PASSWORD 提供
.\.venv\Scripts\python.exe -m backend.mqtt_bridge
```

订阅主题：`greenflight/设备编号/telemetry`。

```json
{"device_id":"LH-001","battery":82.5,"x":160.0,"y":170.0}
```

设备编号必须与主题一致，数值必须有限，电量为 0–100。包体限 8192 字节。遥测独立写入 `data/telemetry.db`。当前不把遥测导入地图、不会发布飞控指令。
