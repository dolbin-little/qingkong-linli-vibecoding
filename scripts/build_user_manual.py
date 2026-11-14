from pathlib import Path
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(r"D:\比赛\大创平台")
OUT = ROOT / "绿航智递平台使用说明书.docx"
SCREENSHOTS = ROOT / "docs" / "使用说明截图"
IMG_OVERVIEW = SCREENSHOTS / "01_运行总览.png"
IMG_ORDERS = SCREENSHOTS / "02_订单管理.png"
IMG_MAP = SCREENSHOTS / "03_航线地图.png"
IMG_STATIONS = SCREENSHOTS / "04_共享站点.png"
IMG_DRONES = SCREENSHOTS / "05_无人机队.png"
IMG_ENERGY = SCREENSHOTS / "06_能源中心.png"
IMG_ALGO = SCREENSHOTS / "07_算法实验室.png"

GREEN = "214B3D"
LIGHT_GREEN = "EAF1DE"
PALE = "F5F7F1"
GRAY = "D9D9D9"
TEXT = RGBColor(31, 45, 39)
MUTED = RGBColor(91, 105, 96)


def set_cell_shading(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_border(cell, color=GRAY, size="6"):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = tcPr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcPr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        el = borders.find(qn(tag))
        if el is None:
            el = OxmlElement(tag)
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:color"), color)


def set_repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    tblHeader = OxmlElement("w:tblHeader")
    tblHeader.set(qn("w:val"), "true")
    trPr.append(tblHeader)


def set_cell_margins(cell, top=110, start=120, bottom=110, end=120):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcMar = tcPr.first_child_found_in("w:tcMar")
    if tcMar is None:
        tcMar = OxmlElement("w:tcMar")
        tcPr.append(tcMar)
    for m, v in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tcMar.find(qn("w:" + m))
        if node is None:
            node = OxmlElement("w:" + m)
            tcMar.append(node)
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")


def font(run, name="Microsoft YaHei", size=None, bold=None, color=None):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def add_text(doc, text, bold_lead=None, style=None, space_after=5, keep=False):
    p = doc.add_paragraph(style=style)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.35
    p.paragraph_format.keep_together = keep
    if bold_lead and text.startswith(bold_lead):
        r = p.add_run(bold_lead)
        font(r, bold=True, color=TEXT)
        r2 = p.add_run(text[len(bold_lead):])
        font(r2, color=TEXT)
    else:
        r = p.add_run(text)
        font(r, color=TEXT)
    return p


def add_bullets(doc, items, level=0):
    for item in items:
        p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
        p.paragraph_format.left_indent = Cm(0.55 + 0.5 * level)
        p.paragraph_format.first_line_indent = Cm(-0.25)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.25
        font(p.add_run(item), size=10.2, color=TEXT)


def add_steps(doc, items):
    for i, item in enumerate(items, 1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.55)
        p.paragraph_format.first_line_indent = Cm(-0.55)
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.line_spacing = 1.3
        font(p.add_run(f"{i}. "), bold=True, color=RGBColor(58, 96, 70))
        font(p.add_run(item), color=TEXT)


def add_table(doc, headers, rows, widths=None, font_size=9.2):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.style = "Table Grid"
    hdr = table.rows[0]
    set_repeat_header(hdr)
    for j, h in enumerate(headers):
        c = hdr.cells[j]
        set_cell_shading(c, GREEN)
        set_cell_border(c)
        set_cell_margins(c)
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        if widths:
            c.width = Cm(widths[j])
        p = c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        font(p.add_run(h), size=9.3, bold=True, color=RGBColor(255, 255, 255))
    for i, row in enumerate(rows):
        cells = table.add_row().cells
        for j, value in enumerate(row):
            c = cells[j]
            if widths:
                c.width = Cm(widths[j])
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_border(c)
            set_cell_margins(c)
            if i % 2 == 1:
                set_cell_shading(c, PALE)
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.15
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j else WD_ALIGN_PARAGRAPH.CENTER
            font(p.add_run(str(value)), size=font_size, color=TEXT)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


def add_heading(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before = Pt(12 if level == 1 else 8)
    p.paragraph_format.space_after = Pt(6)
    for r in p.runs:
        font(r, size=16 if level == 1 else 12, bold=True, color=RGBColor(0, 0, 0))
    return p


def add_caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    font(p.add_run(text), size=8.5, color=MUTED)


def add_page_field(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("第 ")
    font(run, size=8.5, color=MUTED)
    fldChar1 = OxmlElement("w:fldChar")
    fldChar1.set(qn("w:fldCharType"), "begin")
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = " PAGE "
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)
    run2 = paragraph.add_run(" 页")
    font(run2, size=8.5, color=MUTED)


doc = Document()
sec = doc.sections[0]
sec.page_width = Cm(21.0)
sec.page_height = Cm(29.7)
sec.top_margin = Cm(2.0)
sec.bottom_margin = Cm(1.8)
sec.left_margin = Cm(2.2)
sec.right_margin = Cm(2.2)

styles = doc.styles
styles["Normal"].font.name = "Microsoft YaHei"
styles["Normal"]._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
styles["Normal"].font.size = Pt(10.5)
styles["Normal"].font.color.rgb = TEXT
for sname in ["Title", "Heading 1", "Heading 2", "Heading 3"]:
    s = styles[sname]
    s.font.name = "Microsoft YaHei"
    s._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    s.font.color.rgb = RGBColor(0, 0, 0)

# Header and footer
header = sec.header
hp = header.paragraphs[0]
hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
font(hp.add_run("绿航智递社区低空物流平台  使用说明书"), size=8.5, color=MUTED)
add_page_field(sec.footer.paragraphs[0])

# Cover
p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(45)
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
font(p.add_run("绿航智递平台使用说明书"), size=28, bold=True, color=RGBColor(0, 0, 0))
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(22)
font(p.add_run("社区绿色低空物流协同科研仿真平台 V1.0"), size=13, color=MUTED)
if IMG_OVERVIEW.exists():
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(IMG_OVERVIEW), width=Cm(15.8))
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(16)
font(p.add_run("适用对象  项目管理员  演示人员  社区居民测试用户"), size=10.5, color=MUTED)
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
font(p.add_run("版本日期  2026 年 10 月"), size=10, color=MUTED)

doc.add_page_break()
add_heading(doc, "使用前说明", 1)
add_text(doc, "本说明书用于指导客户完成平台启动、登录、下单、智能调度、仿真推进、订单跟踪、站点和无人机管理、能源计划计算、算法实验及数据备份。管理员可以使用全部管理功能；居民账号仅能进入居民服务和订单管理，并且只能查看和操作本人订单。")
add_text(doc, "平台当前为本地科研仿真系统。页面中的地图、天气、支付、订单、飞行、光伏和能耗均为模拟数据；平台不会产生真实扣款，也不会向无人机发送真实飞控指令。", bold_lead="平台当前为本地科研仿真系统。")
add_heading(doc, "快速开始", 1)
add_steps(doc, [
    "打开 D:\\比赛\\大创平台 文件夹，双击 start.bat。等待浏览器打开；如果没有自动打开，请手动访问 http://127.0.0.1:8765。",
    "管理员演示使用账号 admin；居民演示使用账号 resident。两个初始账号的密码均为 GreenFlight2026!。",
    "管理员首次进入后，建议先查看运行总览，再点击“运行智能调度”，随后用“推进 1 分钟”观察订单和航线状态变化。",
    "演示结束后可运行 stop.ps1 停止服务。为了保留当前演示状态，建议先暂停仿真再停止服务。",
])
add_table(doc, ["入口", "地址或文件", "用途"], [
    ["网页平台", "http://127.0.0.1:8765", "管理员端和居民端入口"],
    ["API 文档", "http://127.0.0.1:8765/docs", "查看接口定义和调试接口"],
    ["启动", "start.bat", "启动本地服务并打开平台"],
    ["停止", "stop.ps1", "停止本项目启动的服务"],
], [3.0, 6.5, 7.0])

add_heading(doc, "账号和权限", 1)
add_table(doc, ["功能", "管理员", "居民"], [
    ["浏览居民商品并下单", "可以", "可以"],
    ["查看订单", "全部订单", "仅本人订单"],
    ["取消待调度订单和申请回收", "可以", "仅本人订单"],
    ["调度 仿真 地图 站点 无人机 能源 算法 设置", "可以", "不可见"],
    ["导出订单和实验数据", "可以", "不可以"],
], [6.5, 4.8, 4.8])
add_heading(doc, "登录页按钮", 2)
add_table(doc, ["按钮或字段", "功能", "使用方法和结果"], [
    ["账号", "输入登录账号", "管理员填 admin；居民填 resident 或自行注册的账号。"],
    ["密码", "输入账号密码", "密码输入错误会提示“账号或密码错误”；一分钟内尝试过多会被暂时限制。"],
    ["登录平台", "提交登录", "验证成功后进入对应角色的工作空间。"],
    ["本地演示账号", "展开账号提示", "显示管理员、居民演示账号及初始密码。"],
    ["创建居民账号", "注册新居民账号", "账号限英文字母、数字和下划线，长度 3 至 30；密码至少 10 位。创建成功后自动登录。"],
], [3.8, 4.5, 7.8])

add_heading(doc, "界面通用区域", 1)
add_bullets(doc, [
    "左侧导航栏：切换运行总览、订单管理、航线地图、共享站点、无人机队、能源中心、算法实验室、居民服务和系统设置。居民只显示居民服务与订单管理。",
    "顶部面包屑：显示当前位置，例如“工作空间 / 订单管理”。",
    "仿真环境：表明当前运行的是模拟系统。",
    "T 加时间：显示仿真时钟，不是现实时间。例如 T+01:30 表示仿真开始后 1 分 30 秒。",
    "刷新按钮：立即重新读取数据库状态。平台通常每 3 秒自动刷新一次。",
    "左下角云边状态：在线时显示“云边协同在线”；启用断连模拟后显示“边缘节点接管”。",
    "头像或退出：结束当前登录会话并返回登录页。移动端顶部另有“退出”按钮。",
])

add_heading(doc, "运行总览", 1)
add_text(doc, "运行总览是管理员进入平台后的首页，用于集中查看订单、飞行、站点、天气和能源状态，并执行最常用的调度和仿真操作。")
if IMG_OVERVIEW.exists():
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(IMG_OVERVIEW), width=Cm(16.2))
    add_caption(doc, "图 1 运行总览页面")
add_heading(doc, "页面数据", 2)
add_table(doc, ["区域", "显示内容", "怎么看"], [
    ["累计配送订单", "总订单数 已完成数 待调度数", "待调度数量大于 0 时应执行智能调度。"],
    ["平均送达时长", "已完成配送的平均耗时", "这是仿真结果；页面同时提示 3 分钟目标仍需真实实验验证。"],
    ["无人机实时运力", "在途数量 总机队数量 在线站点数", "在途为正在执行任务的无人机。"],
    ["站点累计光伏发电", "按模拟光照和面板面积累计的发电量", "单位为 kWh。"],
    ["社区配送网络", "站点 订单 禁飞区 航线 飞行中的无人机", "点击“全屏地图”进入航线地图。"],
    ["飞行环境", "温度 天气 风速 光照 可飞状态", "风速超过 10 m/s 或降雨超过 5 mm/h 时显示暂停起飞。"],
    ["绿色能源概览", "站点总储能 近期充电分配 航班净能耗", "运行仿真后曲线逐步积累。"],
    ["最近配送订单", "最近 5 笔订单", "点击“查看”打开订单时间线。"],
], [4.0, 6.0, 6.1])
add_heading(doc, "页面按钮", 2)
add_table(doc, ["按钮", "作用", "操作结果"], [
    ["新建订单", "打开订单表单", "完成模拟支付后，订单进入待调度队列。"],
    ["推进 1 分钟", "手动推进仿真时钟", "更新飞行位置、电量、订单状态、光伏和充电记录。适合逐步演示。"],
    ["启动仿真", "按 6 倍速连续运行", "按钮变成“暂停仿真”；每秒推进约 0.1 个仿真分钟。"],
    ["暂停仿真", "停止自动推进", "保留当前状态，可以继续手动推进或稍后恢复。"],
    ["运行智能调度", "使用 VNS 与 MILP 进行任务分配和路线求解", "符合库存、载重、电量、时间窗和禁飞区约束的任务生成航班；不可行任务保留为待分配。"],
    ["全屏地图", "进入航线地图", "查看完整地图并选择取件点、管理禁飞区。"],
    ["全部订单", "进入订单管理", "查看、搜索、筛选和导出全部订单。"],
    ["查看", "打开指定订单详情", "显示金额、站点、无人机、截止时间和完整事件时间线。"],
], [3.7, 5.0, 7.4])

add_heading(doc, "新建订单", 1)
add_text(doc, "“新建订单”“立即租借”“立即下单”以及航线地图中的“在此创建订单”都会打开同一张订单表单。")
add_table(doc, ["字段", "填写说明", "限制"], [
    ["配送物品", "共享充电宝 共享雨伞 瓶装饮用水 便携急救包", "库存和载重会影响能否调度。"],
    ["数量", "输入本次需要的件数", "1 至 3 件。"],
    ["公共取件点", "从六处公共取件点下拉选择，地址与坐标自动关联", "禁飞区内地点暂不可选；无需手填地址或坐标。"],
    ["在地图上选择取件位置", "在下单窗口直接展开地图，点蓝色标记或空白处", "自定义位置不能在禁飞区内；管理员可查看自动关联坐标。"],
    ["任务优先级", "普通 优先 紧急", "优先级越高，未服务时的调度惩罚越大。"],
    ["送达时间窗", "3 分钟 6 分钟或 15 分钟", "算法必须在截止时间内到达，否则不会生成不合规航班。"],
    ["确认模拟支付并下单", "提交订单", "金额由商品费用加 1.50 元模拟配送费组成，不会真实扣款。"],
    ["取消", "关闭表单", "不保存已填信息。"],
], [3.7, 7.0, 5.4])
add_text(doc, "下单后若系统设置已开启自动调度，平台会立即尝试派单；否则需要管理员点击“智能调度”或“运行智能调度”。")

add_heading(doc, "订单管理", 1)
add_text(doc, "管理员在此管理全部订单；居民看到的标题为“我的订单”，只能查看本人订单。")
if IMG_ORDERS.exists():
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(IMG_ORDERS), width=Cm(16.2))
    add_caption(doc, "图 2 订单管理页面")
add_table(doc, ["按钮或控件", "功能", "详细说明"], [
    ["导出 CSV", "下载订单明细", "仅管理员可见。导出编号、物品、数量、地址、状态、任务类型、时间、无人机、站点、金额和来源。"],
    ["新建订单", "创建配送订单", "打开订单表单。"],
    ["搜索框", "搜索记录", "按订单编号、物品名称或地址实时匹配。"],
    ["状态筛选", "筛选订单", "可选全部、待调度、配送中、已送达、待回收、已归还、已取消。"],
    ["智能调度", "分配待调度任务", "仅管理员可见，默认使用 VNS-MILP。"],
    ["查看", "打开订单详情", "查看任务类型、模拟金额、站点、无人机、截止时间、来源和事件时间线。"],
    ["取消订单并模拟退款", "取消订单", "只在待调度的配送订单上出现；已起飞、回收任务和已完成订单不能取消。"],
    ["申请无人机上门回收", "创建回收子订单", "只在已送达的共享充电宝或共享雨伞订单上出现。创建后需再次调度。"],
    ["关闭", "关闭详情窗口", "返回订单列表。"],
], [4.0, 4.5, 7.6])
add_heading(doc, "订单状态说明", 2)
add_table(doc, ["状态", "含义", "后续操作"], [
    ["待调度", "订单已创建，尚未分配无人机", "管理员运行调度；配送订单可取消。"],
    ["配送中", "已生成航班并正在执行", "推进或启动仿真，等待送达。"],
    ["已送达", "配送物品到达取件点", "共享物品可以申请回收。"],
    ["待回收", "原配送订单已申请回收", "对应的回收子订单等待或正在执行。"],
    ["回收返站", "无人机已取回共享物品并返站", "继续推进仿真。"],
    ["已归还", "共享物品已回到原站点", "库存回补并完成模拟结算。"],
    ["已取消", "待调度配送订单已取消", "模拟退款已记录。"],
], [3.2, 7.0, 5.9])

add_heading(doc, "航线地图", 1)
add_text(doc, "航线地图展示 1000 米乘 700 米的二维仿真社区。绿色圆点为共享站点，金色圆点为配送需求，虚线为计算航线，斜纹矩形为禁飞区域，深色无人机符号表示在途飞行器。地图不代表真实空域。")
if IMG_MAP.exists():
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(IMG_MAP), width=Cm(16.2))
    add_caption(doc, "图 3 航线地图页面")
add_table(doc, ["操作", "功能", "注意事项"], [
    ["加号", "放大地图", "最大放大倍数为 2 倍。"],
    ["减号", "缩小地图", "最小为原始比例。"],
    ["点击地图空白处", "选择公共取件点", "右侧显示选中的 X Y 坐标；随后可点击“在此创建订单”。"],
    ["在此创建订单", "用选中坐标创建订单", "表单会自动填入地图坐标和“地图选定公共取件点”。"],
    ["点击订单金色圆点", "查看订单详情", "可查看订单状态和时间线。"],
    ["点击绿色站点", "进入共享站点页", "查看站点库存和设备。"],
    ["添加", "新增矩形禁飞区", "所有航班必须已返站；最多 10 个区域；不能覆盖站点或有效订单点。"],
    ["移除", "删除禁飞区域", "所有航班必须已返站。删除后新路线使用更新后的地图。"],
    ["推进 1 分钟 启动仿真 暂停仿真", "控制仿真", "与运行总览中的同名按钮完全相同。"],
], [4.2, 5.5, 6.4])
add_heading(doc, "添加禁飞区字段", 2)
add_bullets(doc, [
    "区域名称：2 至 40 个字符。",
    "左上角 X：5 至 900；左上角 Y：5 至 600。",
    "宽度和高度：各 10 至 200 米，且矩形不能超出地图边界。",
    "保存区域：校验通过后立即绘制，之后生成的航线会绕开该区域。",
])

add_heading(doc, "共享站点", 1)
add_text(doc, "共享站点承担库存、无人机归属、起降、光伏发电、储能和充电位管理。每张站点卡显示站点编号、区域、坐标、在线状态、各类库存、储能、光伏面积、充电位和归属无人机数量。")
if IMG_STATIONS.exists():
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(IMG_STATIONS), width=Cm(16.2))
    add_caption(doc, "图 4 共享站点页面")
add_table(doc, ["按钮", "作用", "限制和结果"], [
    ["补充库存", "给指定站点增加物品", "选择物品并输入 1 至 100 件，点击“确认入库”后库存立即增加。"],
    ["暂停服务", "将在线站点设为停用", "站点有尚未返站的航班时不能停用；停用站点不参与新任务分配。"],
    ["恢复服务", "将停用站点重新上线", "恢复后可以参与调度和 MPC 补能计划。"],
], [4.0, 5.0, 7.1])
add_text(doc, "库存补充仅表示仿真入库，不连接真实仓储设备。配送订单出库后会扣减对应库存；共享物品完成回收返站后回补原站库存。")

add_heading(doc, "无人机队", 1)
add_text(doc, "每张无人机卡显示归属站点、当前状态、剩余电量、最大载重、累计飞行时间、累计里程、电池容量和 20% 安全电量余量。")
if IMG_DRONES.exists():
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(IMG_DRONES), width=Cm(16.2))
    add_caption(doc, "图 5 无人机队页面")
add_table(doc, ["状态或按钮", "含义", "操作规则"], [
    ["待命", "无人机可以参与调度", "必须同时满足电量、载重、时间窗和返航约束。"],
    ["配送中", "正在执行航班", "“设为维护”按钮被禁用，需先等无人机返站。"],
    ["充电中", "站点正在为无人机补能", "补能由仿真步和 MPC 首时段计划执行。"],
    ["维护中", "无人机暂不参与调度", "点击“恢复待命”后重新加入可用机队。"],
    ["设为维护", "把待命或充电设备标记为维护", "用于演示设备检修和运力下降。"],
    ["恢复待命", "结束维护状态", "设备可在下一轮调度中被选择。"],
    ["推进 启动 暂停", "控制仿真时间", "用于观察在途无人机、累计里程和电量变化。"],
], [4.0, 5.2, 6.9])

add_heading(doc, "能源中心", 1)
add_text(doc, "能源中心使用 60 分钟滚动时域的 MPC 模型，为各在线站点规划光伏、储能、充电位和无人机补能。计划分为 6 个时段，每段 10 分钟；仿真只执行当前首时段动作，然后重新滚动计算。")
if IMG_ENERGY.exists():
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(IMG_ENERGY), width=Cm(16.2))
    add_caption(doc, "图 6 能源中心页面")
add_table(doc, ["按钮或区域", "功能", "说明"], [
    ["模拟天气", "打开天气设置", "可选择晴天、阴天、强风降雨预设，也可自定义天气名称、光照、风速和降水。"],
    ["应用天气", "保存天气参数", "只影响后续新航班和能源预测；有在途航班时不能修改。"],
    ["取消", "放弃天气修改", "关闭窗口并保留原参数。"],
    ["重新计算 MPC", "计算未来 1 小时充电计划", "按在线站点分别生成光伏预测、计划总分配量和首段充电动作。"],
    ["当前站点光伏功率", "显示即时估算功率", "按在线站点光伏面积乘光照强度乘 20% 效率计算。"],
    ["站点总储能", "显示所有站点储能合计", "模型不使用隐含市电，不能消耗尚未产生的未来能量。"],
    ["首段补能", "当前 10 分钟计划充入的电量", "“优先充电”表示占用充电位；“等待充电位”表示本时段不充。"],
], [4.3, 5.0, 6.8])
add_heading(doc, "天气预设", 2)
add_table(doc, ["预设", "光照", "风速", "降水", "典型结果"], [
    ["晴天", "720 W/m²", "2.4 m/s", "0", "光伏功率较高，通常可飞。"],
    ["阴天", "180 W/m²", "4 m/s", "0", "光伏补能下降，净能耗上升。"],
    ["强风降雨", "60 W/m²", "12 m/s", "8 mm/h", "超过起飞阈值，新任务可能无法生成航班。"],
], [2.7, 3.0, 3.0, 3.0, 4.4])
add_text(doc, "当光照历史少于 12 个十分钟样本时，页面会显示短时衰减基线；历史满足条件时才使用 LSTM 进行 6 步预测。所有功率、效率和模型参数仍是待标定的仿真假设。")

add_heading(doc, "算法实验室", 1)
add_text(doc, "算法实验室用于展示调度算法的实际求解过程、DQN 模型状态以及同场景对比实验。实验数据来自本地求解器，不代表真实运营效果。")
if IMG_ALGO.exists():
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(IMG_ALGO), width=Cm(16.2))
    add_caption(doc, "图 7 算法实验室页面")
add_table(doc, ["按钮", "功能", "输入和结果"], [
    ["生成场景", "向当前运营场景添加随机订单", "输入订单数量 1 至 24 和随机种子 0 至 99999。生成的订单会进入当前待调度队列。"],
    ["运行智能调度", "对当前运营订单执行 VNS-MILP", "显示求解耗时、MILP 子问题数、派出无人机数和目标收敛记录。"],
    ["用 DQN 排序候选", "使用 DQN 对硬约束合格的候选排序", "DQN 不绕过库存、载重、电量、时间窗和 MILP 检查；模型缺失时回退为代价排序。"],
    ["运行对比实验", "比较三种算法", "在独立合成场景上比较最近邻+MILP、VNS-MILP、DQN+MILP，不修改当前运营订单。"],
    ["开始计算", "提交对比实验", "计算可能持续数秒，完成后显示分配数、里程、净能耗、平均到达时间和耗时。"],
    ["导出 JSON", "下载全部实验报告", "仅管理员可用，适合后续论文制图和结果复核。"],
], [4.2, 5.0, 6.9])
add_heading(doc, "随机种子的作用", 2)
add_text(doc, "订单数量相同且随机种子相同时，生成的位置、品类和优先级保持一致，便于复现实验。运行毫秒数仍可能受电脑负载影响。对比实验使用同一份场景和同一套约束，避免把输入差异误当作算法差异。")

add_heading(doc, "居民服务", 1)
add_text(doc, "居民服务是居民账号登录后的默认首页，管理员也可以进入。页面显示商品价格、重量、在线站点总库存以及最近服务记录。")
add_table(doc, ["商品", "模拟价格", "重量", "按钮和后续流程"], [
    ["共享充电宝", "2 元每小时", "0.28 kg", "点击“立即租借”；送达后可申请上门回收。"],
    ["共享雨伞", "2 元每次", "0.35 kg", "点击“立即租借”；送达后可申请上门回收。"],
    ["瓶装饮用水", "2 元每瓶", "0.55 kg", "点击“立即下单”；为消耗品，无回收按钮。"],
    ["便携急救包", "8 元每份", "0.20 kg", "点击“立即下单”；为消耗品，无回收按钮。"],
], [4.0, 3.4, 3.0, 6.0])
add_bullets(doc, [
    "立即租借或立即下单：打开订单表单，并自动选中对应商品。",
    "查看订单：进入订单管理，查看本人全部订单。",
    "我的近期服务：列出当前登录账号最近 4 笔服务记录；点击“查看”打开详情。",
    "居民账号不能执行调度。下单后需要管理员调度，或由管理员提前开启自动调度。",
])

add_heading(doc, "系统设置", 1)
add_table(doc, ["按钮", "作用", "详细说明"], [
    ["开启或关闭自动调度", "控制自动派单", "开启后，新订单创建或仿真步推进时自动尝试分配；关闭后由管理员手动点击调度。"],
    ["模拟云断连", "切换到边缘接管状态", "同一台电脑、同一进程内模拟断连；状态栏变为“边缘节点接管”，事件日志记录切换。"],
    ["恢复连接", "恢复云边在线状态", "仅恢复仿真标志，不代表真实分布式云服务。"],
    ["启动或暂停", "控制仿真连续运行", "显示当前 T 加时间和 6 倍运行倍率。"],
    ["编辑", "设置气象条件", "功能与能源中心“模拟天气”一致。"],
    ["备份并重置", "恢复初始演示数据", "先弹出确认窗口；确认后将当前订单、航班和实验写入 data/backup-时间戳.json，再恢复种子场景。账号不变。"],
    ["保留当前数据", "取消重置", "关闭确认窗口，不写入备份、不修改数据。"],
    ["确认备份并重置", "执行重置", "会替换当前仿真状态。操作前应确认不再需要当前演示进度。"],
    ["API 文档", "打开 FastAPI 接口文档", "用于开发和联调，普通客户无需操作。"],
], [4.5, 4.8, 6.8])
add_heading(doc, "系统事件", 2)
add_text(doc, "系统设置底部保留最近 200 条事件，按 T 加时间显示订单创建、调度、天气切换、站点配置、云边状态等操作。客户遇到状态不一致时，可以先检查这里是否记录了相应操作。")

add_heading(doc, "推荐的完整演示流程", 1)
add_steps(doc, [
    "以管理员账号登录，在运行总览确认 4 个站点、8 架无人机和待调度演示订单。",
    "点击“运行智能调度”，确认地图出现虚线航线，订单状态变为配送中。",
    "点击“推进 1 分钟”逐步演示，或点击“启动仿真”连续运行；观察订单、飞行位置、电量和能源指标更新。",
    "打开订单管理，选择已送达的共享充电宝或共享雨伞订单，点击“申请无人机上门回收”。",
    "再次运行智能调度并推进仿真，直到回收任务返站，检查原站库存回补和订单时间线。",
    "进入能源中心，点击“重新计算 MPC”；等所有航班返站后切换晴天、阴天和强风降雨，比较光伏和可飞状态。",
    "进入算法实验室，先运行对比实验，再用相同数量和随机种子复算，核对结果可复现性。",
    "进入系统设置，演示自动调度和云断连接管；需要重新开始时使用“备份并重置”。",
])

add_heading(doc, "居民下单和归还流程", 1)
add_steps(doc, [
    "使用 resident 或新注册的居民账号登录。",
    "在居民服务选择商品，点击“立即租借”或“立即下单”。",
    "填写数量，选择公共取件点（或在下单窗口地图上选点），确认优先级和时间窗后点击“确认模拟支付并下单”。",
    "进入订单管理查看待调度状态。管理员手动调度，或系统自动调度后，状态变为配送中。",
    "订单送达后，共享充电宝和共享雨伞的详情页会出现“申请无人机上门回收”。",
    "提交回收请求后会生成新的回收任务；管理员再次调度并推进仿真，完成返站和模拟结算。",
])

add_heading(doc, "常见提示和处理方法", 1)
add_table(doc, ["提示或现象", "原因", "处理方法"], [
    ["无法访问 127.0.0.1:8765", "服务未启动或已退出", "重新双击 start.bat；仍失败时查看 data/server-error.log。"],
    ["账号或密码错误", "凭据不正确", "检查大小写；演示密码为 GreenFlight2026!。"],
    ["尝试过于频繁", "一分钟内失败登录超过限制", "等待一分钟后再试。"],
    ["取件点位于禁飞区", "坐标落入斜纹区域", "在下单窗口地图或公共取件点列表中重新选择有效位置。"],
    ["调度后仍有订单待分配", "可能无库存、低电量、超载、时间窗过紧、恶劣天气或批量上限", "检查站点库存、无人机电量、天气和订单截止时间；补库存、充电或稍后分批调度。"],
    ["请等待当前航班返站后切换天气", "在途航班未完成", "推进仿真，所有航班返站后再改天气。"],
    ["有航班待返站，不能停用", "该站点仍有出发航班", "等待该站点航班全部返站。"],
    ["飞行中不能切换维护状态", "无人机正在执行任务", "等待返站后再设为维护。"],
    ["请等待所有航班返站", "正在编辑禁飞区但仍有在途航班", "暂停编辑并先完成航班。"],
    ["当前站点无需分配充电任务", "没有需要充电的可用无人机", "属于正常结果，可继续运行仿真或查看其他站点。"],
    ["运行仿真后显示真实记录", "图表历史样本不足", "推进仿真若干步后重新查看。这里的“真实记录”指平台实际运行日志，不代表真实无人机数据。"],
], [5.2, 5.2, 5.7], font_size=8.8)

add_heading(doc, "数据保存和恢复", 1)
add_bullets(doc, [
    "平台状态保存在 data/greenflight.db，正常关闭并再次启动后会保留订单和仿真进度。",
    "系统设置中的“备份并重置”会在 data 文件夹生成 backup-时间戳.json。",
    "服务运行日志位于 data/server.log，错误日志位于 data/server-error.log。",
    "订单 CSV 和实验 JSON 由浏览器下载，保存位置由浏览器下载设置决定。",
    "重置只恢复演示状态，不删除已创建的本地账号。",
])

add_heading(doc, "使用边界", 1)
add_bullets(doc, [
    "平台不接收真实微信支付，所有支付、退款和结算均为模拟。",
    "地图是二维固定高度仿真，不代表批准空域，也不能用于真实飞行规划。",
    "云断连接管在同一进程内模拟，不能视为真实分布式容灾验证。",
    "MQTT 适配器只保存经过校验的遥测，不会向真实设备发送起飞或控制命令。",
    "DWA 局部避障函数没有连接网页航线执行和真实飞控；当前网页也不模拟多机空中碰撞规避。",
    "光伏、能耗、飞行、算法和 3 分钟送达指标都需要真实设备、天气、社区环境和安全审批进一步验证。",
])

add_heading(doc, "按钮总索引", 1)
add_table(doc, ["页面", "按钮或操作", "一句话说明"], [
    ["全局", "刷新 退出", "刷新状态；结束登录。"],
    ["登录", "登录平台 创建居民账号", "登录现有账号；注册并自动登录居民账号。"],
    ["运行总览", "新建订单 推进 1 分钟 启动或暂停 运行智能调度 全屏地图 全部订单 查看", "常用运营控制和详情入口。"],
    ["订单管理", "导出 CSV 新建订单 搜索 状态筛选 智能调度 查看 取消订单 申请回收", "订单全生命周期管理。"],
    ["航线地图", "加号 减号 点击地图 在此创建订单 添加 移除 推进 启动或暂停", "地图取点、禁飞区和仿真控制。"],
    ["共享站点", "补充库存 暂停服务 恢复服务", "调整库存和站点在线状态。"],
    ["无人机队", "设为维护 恢复待命 推进 启动或暂停", "控制设备可用性和仿真。"],
    ["能源中心", "模拟天气 晴天 阴天 强风降雨 应用天气 重新计算 MPC", "设置环境并生成补能计划。"],
    ["算法实验室", "生成场景 运行智能调度 用 DQN 排序候选 运行对比实验 开始计算 导出 JSON", "生成数据、求解和比较算法。"],
    ["居民服务", "立即租借 立即下单 查看订单 查看", "居民下单和查询入口。"],
    ["系统设置", "自动调度 云断连 恢复连接 启动或暂停 编辑 备份并重置 API 文档", "控制仿真环境、连接和数据。"],
], [3.3, 7.2, 5.6], font_size=8.6)

add_heading(doc, "技术支持信息", 1)
add_text(doc, "客户反馈问题时，建议同时提供：当前登录角色、所在页面、点击的按钮、页面提示文字、订单编号、仿真时间以及 data/server-error.log 中的最新错误。这样可以快速定位是权限、业务状态、约束不可行还是服务启动问题。")

doc.core_properties.title = "绿航智递平台使用说明书"
doc.core_properties.subject = "社区绿色低空物流协同科研仿真平台操作说明"
doc.core_properties.keywords = "绿航智递, 使用说明, 无人机, 云边协同, 仿真平台"
doc.save(OUT)
print(OUT)
