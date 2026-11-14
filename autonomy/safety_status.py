"""Operator explanations describe requested protection, never assumed aircraft outcome."""
from collections import deque
import math

POLICIES = {
    'LINK_LOSS': ('遥测链路中断', '请求飞控降落，等待链路恢复确认', '检查链路和遥控器；依靠飞控自身失联保护。当前不能确认降落命令是否到达。'),
    'POSITION_STALE': ('位置数据过期', '暂停航线，短时悬停后请求降落', '检查定位源；落地确认后核查任务，禁止自动恢复原航线。'),
    'POSITION_QUALITY': ('定位质量不足', '请求受控降落', '检查定位与卫星状态，完成地面检查后重新载入。'),
    'PERCEPTION_STALE': ('测距输入中断', '暂停航线，短时悬停后请求降落', '检查测距连接；不能把没有障碍数据解释为没有障碍。'),
    'BATTERY_RESERVE': ('达到返航电量阈值', '尝试规划安全返航', '监控返航；无安全航线时停止平移并请求降落，落点尚未经过真实地面感知验证。'),
    'BATTERY_CRITICAL': ('达到紧急电量阈值', '请求受控降落', '检查实际落点，落地后补能并核查货物。'),
    'RETURN_ROUTE_BLOCKED': ('未找到安全返航走廊', '停止平移并请求降落', '当前未实现真实备降点识别，需要人工确认落点。'),
    'CONTROL_LEASE_EXPIRED': ('人工操控端已离线或释放控制权', '清零人工速度，保护悬停后请求降落', '重新获取操控权；保护触发后须落地核查，不能直接恢复自动任务。'),
    'CONTROL_LOOP_LATE': ('控制循环连续超时', '停止任务并请求降落', '检查计算负载和日志；目标20Hz不是硬实时保证。'),
    'LOOP_ERROR': ('控制循环发生异常', '请求受控降落', '保留日志，确认飞机落地并核查任务。'),
}

def describe(fault, phase, readonly=False):
    if readonly:
        return {'code': fault, 'title': '外部飞控只读监控', 'action': '不发送解锁、速度或保护控制指令',
                'next': '飞行控制与失效保护由外部飞控及其操作员负责。', 'level': 'info'}
    if fault:
        title, action, next_step = POLICIES.get(fault, (fault, '保护状态已锁止', '检查遥测、运行记录及飞机实际状态，落地后核查恢复。'))
        return {'code': fault, 'title': title, 'action': action, 'next': next_step, 'level': 'warning'}
    return {'code': None, 'title': '未触发保护', 'action': '持续监测遥测、路径和控制时序',
            'next': '人工接管将暂停航线；自主任务可在操作界面关闭后继续。', 'level': 'info'}

class LoopTiming:
    """Bounded measurement window; first observation never counts as a deadline miss."""
    def __init__(self):
        self.samples = deque(maxlen=1200)
        self.last = None
        self.consecutive = 0
        self.misses = 0

    def observe(self, now):
        if self.last is None:
            self.last = now
            return False
        delta = now - self.last
        self.last = now
        if delta <= 0 or not math.isfinite(delta):
            return False
        ms = delta * 1000
        self.samples.append(ms)
        self.consecutive = self.consecutive + 1 if ms > 150 else 0
        self.misses += int(ms > 150)
        return self.consecutive >= 3

    def dump(self):
        values = sorted(self.samples)
        return {'window_samples': len(values), 'target_hz': 20,
                'mean_period_ms': round(sum(values)/len(values), 2) if values else 0,
                'p95_period_ms': round(values[max(0, math.ceil(len(values)*.95)-1)], 2) if values else 0,
                'max_period_ms': round(max(values), 2) if values else 0,
                'deadline_ms': 150, 'deadline_misses': self.misses, 'consecutive_misses': self.consecutive}
