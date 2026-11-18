"""Replay a disconnected flight with cached and restored simulated telemetry."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

root = Path.cwd()
sys.path[:0] = [str(root), str(root / "tests_autonomy")]

from autonomy.models import norm
from test_safety_operations import engine


def observe(label, flight, now):
    telemetry = flight.adapter.t
    print(label, json.dumps({
        "phase": flight.phase,
        "fault": flight.fault,
        "armed": telemetry.armed,
        "height_m": telemetry.position[2],
        "speed_m_s": round(norm(telemetry.velocity), 3),
        "heartbeat_age_s": round(now - telemetry.heartbeat_at, 3),
        "position_age_s": round(now - telemetry.position_at, 3),
        "land_requests": flight.adapter.lands,
        "velocity_commands": len(flight.adapter.velocities),
        "delivered": flight.delivered,
    }, ensure_ascii=False), flush=True)


def disconnect(flight):
    flight.adapter.t.heartbeat_at = 997
    flight.adapter.t.position_at = 997
    flight.tick(1000)
    assert (flight.phase, flight.fault, flight.adapter.lands) == ("LINK_LOST", "LINK_LOSS", 1)


with TemporaryDirectory(prefix="flight-link-") as folder:
    test_directory = Path(folder)
    flight = engine(test_directory / "main")
    disconnect(flight)
    observe("断链触发", flight, 1000)

    flight.tick(1000.1)
    assert flight.phase == "LINK_LOST" and not flight.delivered
    assert flight.adapter.lands == 1 and not flight.adapter.velocities
    observe("① 没有新遥测", flight, 1000.1)

    flight.adapter.t.armed = False
    assert flight.adapter.t.position[2] == 12
    flight.tick(1000.2)
    assert flight.phase == "LINK_LOST" and not flight.delivered
    observe("② 缓存显示未解锁、高度 12 米", flight, 1000.2)

    flight.adapter.t.position[2] = 0
    flight.tick(1000.3)
    assert flight.phase == "LINK_LOST" and not flight.delivered
    observe("补验：缓存即使显示 0 米", flight, 1000.3)

    flight.adapter.t.heartbeat_at = flight.adapter.t.position_at = 1000.4
    flight.adapter.t.velocity = [0, 0, 0]
    flight.tick(1000.4)
    assert (flight.phase, flight.fault, flight.delivered) == ("STOPPED", "LINK_LOSS", False)
    assert flight.adapter.lands == 2 and not flight.adapter.velocities and not flight.adapter.arms
    observe("③ 新心跳、新位置、0 米、0 米/秒且未解锁", flight, 1000.4)

    moving = engine(test_directory / "moving")
    disconnect(moving)
    moving.adapter.t.armed = False
    moving.adapter.t.heartbeat_at = moving.adapter.t.position_at = 1000.1
    moving.tick(1000.1)
    assert moving.phase == "LANDING" and moving.adapter.lands == 2
    observe("补验：链路恢复但仍在 12 米", moving, 1000.1)
    moving.adapter.t.position[2] = 0
    moving.adapter.t.velocity = [0.21, 0, 0]
    moving.tick(1000.2)
    assert moving.phase == "LANDING"
    observe("补验：链路恢复，0 米但速度 0.21 米/秒", moving, 1000.2)

    armed = engine(test_directory / "armed")
    disconnect(armed)
    armed.adapter.t.heartbeat_at = armed.adapter.t.position_at = 1000.1
    armed.adapter.t.position[2] = 0
    armed.tick(1000.1)
    assert armed.phase == "LANDING"
    observe("补验：链路恢复，0 米但仍解锁", armed, 1000.1)

    already_unarmed = engine(test_directory / "already-unarmed")
    already_unarmed.adapter.t.armed = False
    already_unarmed.adapter.t.heartbeat_at = already_unarmed.adapter.t.position_at = 997
    already_unarmed.tick(1000)
    assert already_unarmed.phase == "LANDING" and already_unarmed.fault == "AUTOPILOT_DISARMED"
    assert not already_unarmed.delivered
    observe("补验：失联保护锁止前已看到未解锁旧数据", already_unarmed, 1000)

print("PASS | 3 项指定情景及 5 项补充边界", flush=True)
