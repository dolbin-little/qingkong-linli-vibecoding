"""Record order, inventory and aircraft fields during a local ledger replay."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import gc
import json
import sys

sys.path.insert(0, str(Path.cwd()))

from backend import store
from backend.flight_orders import FlightOrders
from tests_autonomy.test_business_loop import snap


def snapshot(task):
    state = store.read_state()
    order = next(row for row in state["orders"] if row["id"] == task["order_id"])
    stored_task = next(row for row in state["flight_tasks"] if row["run_id"] == task["run_id"])
    station = next(row for row in state["stations"] if row["id"] == task["station_id"])
    aircraft = next(row for row in state["drones"] if row["id"] == task["drone_id"])
    return {
        "order": order["status"],
        "task": stored_task["phase"],
        "stock": stored_task["stock"],
        "available": station["inventory"][order["product"]],
        "aircraft": aircraft["status"],
        "delivered_at": order["delivered_wall_at"] if "delivered_wall_at" in order else None,
    }


def report(label, values):
    print(label, json.dumps(values, ensure_ascii=False), flush=True)


with TemporaryDirectory(prefix="business-replay-") as temp:
    base = Path(temp)
    store.DB_PATH = base / "delivered.sqlite"
    ledger = FlightOrders()
    before = store.read_state()
    task = ledger.reserve("LH-DEMO-001", "dup")
    reserved = snapshot(task)
    original = next(row for row in before["stations"] if row["id"] == task["station_id"])
    assert reserved["available"] == original["inventory"]["powerbank"] - 1
    assert reserved["stock"] == "reserved"
    ledger.sync(snap(task, "EXECUTING"))
    returning = snap(task, "RETURNING", True)
    ledger.sync(returning)
    first = snapshot(task)
    assert (first["order"], first["stock"], first["aircraft"]) == ("delivered", "consumed", "flight_active")
    assert first["available"] == reserved["available"]
    assert first["delivered_at"] is not None
    ledger.sync(returning)
    duplicate = snapshot(task)
    assert first == duplicate
    ledger.sync(snap(task, "COMPLETED", True))
    end = snapshot(task)
    assert (end["order"], end["stock"], end["aircraft"]) == ("delivered", "consumed", "idle")
    assert end["available"] == first["available"]
    report("预占后", reserved)
    report("首次同步送达", first)
    report("同阶段重复同步", duplicate)
    report("返航完成", end)

    for phase, expected_aircraft in (("READY", "flight_reserved"), ("EXECUTING", "flight_active")):
        store.DB_PATH = base / f"restart-{phase}.sqlite"
        ledger = FlightOrders()
        task = ledger.reserve("LH-DEMO-001", "interrupted-" + phase)
        if phase == "EXECUTING":
            ledger.sync(snap(task, phase))
        before_restart = snapshot(task)
        restarted = FlightOrders()
        restarted.recover_after_restart()
        after_restart = snapshot(task)
        assert after_restart["order"] == "flight_exception"
        assert after_restart["task"] == "INTERRUPTED"
        assert after_restart["stock"] == before_restart["stock"] == "reserved"
        assert after_restart["available"] == before_restart["available"]
        assert after_restart["aircraft"] == before_restart["aircraft"] == expected_aircraft
        assert after_restart["delivered_at"] is None
        state = deepcopy(store.read_state())
        order = next(row for row in state["orders"] if row["id"] == "LH-DEMO-002")
        assert order["status"] == "pending"
        try:
            restarted.reserve("LH-DEMO-002", "new-dispatch")
        except ValueError as err:
            assert "核对恢复后再载入" in str(err)
            report("尝试载入新任务被拒绝", {"order": order["id"], "status": order["status"], "reason": str(err)})
        else:
            raise AssertionError("A new task was accepted before reconciliation")
        assert state == store.read_state()
        report(f"{phase} 重启前", before_restart)
        report(f"{phase} 重启后", after_restart)
    gc.collect()

print("PASS | 同阶段重复同步、READY/EXECUTING 模拟重启及新任务阻断")
