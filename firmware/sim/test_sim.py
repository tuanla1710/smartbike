"""Ca tự động trên giả lập. Chạy từ thư mục firmware: python -m unittest sim.test_sim"""

from __future__ import annotations

import unittest
from pathlib import Path

from sim.runner import SCENARIOS, run_file
from sim.session import Session


def lines_of(session: Session, text: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        found.extend(session.exec(line))
    return found


class ScenarioFiles(unittest.TestCase):
    def test_all_files(self) -> None:
        paths = sorted(Path(SCENARIOS).rglob("*.txt"))
        self.assertGreaterEqual(len(paths), 7)
        for path in paths:
            failures = run_file(Session(), path)
            self.assertEqual(failures, [], msg="\n".join(failures))


class ControlCases(unittest.TestCase):
    def test_tail_only_while_riding(self) -> None:
        session = Session()
        session.exec("arm")
        session.exec("tick 10")
        gates = session.exec("gates")[0]
        self.assertIn("out_tail=0", gates)
        session.exec("ride start")
        session.exec("tick 10")
        gates = session.exec("gates")[0]
        self.assertIn("out_tail=1023", gates)
        self.assertIn("mode=riding", session.exec("status")[0])

    def test_riding_motion_does_not_alarm(self) -> None:
        session = Session()
        script = """
        debug on
        config set alarm_motion_ms 50
        ride start
        tick 10
        inject motion on
        tick 200
        """
        lines_of(session, script)
        self.assertIn("mode=riding", session.exec("status")[0])

    def test_lidar_does_not_touch_brake(self) -> None:
        session = Session()
        lines_of(session, "debug on\narm\ntick 10\ninject range 3999\ntick 10")
        flags = bytes.fromhex(session.exec("snapshot")[0].split("hex=")[1])[1]
        self.assertTrue(flags & 0x02)
        self.assertIn("out_brake=0", session.exec("gates")[0])
        session.exec("inject range 4000")
        session.exec("tick 10")
        flags = bytes.fromhex(session.exec("snapshot")[0].split("hex=")[1])[1]
        self.assertFalse(flags & 0x02)

    def test_snapshot_is_32_bytes(self) -> None:
        raw = bytes.fromhex(Session().exec("snapshot")[0].split("hex=")[1])
        self.assertEqual(len(raw), 32)
        self.assertEqual(raw[25:], b"\x00" * 7)

    def test_horn_lockout_then_release(self) -> None:
        session = Session()
        session.dev.cfg["horn_max_on_s"] = 1
        session.exec("hw press horn")
        session.exec("tick 40")
        session.exec("tick 1000")
        session.exec("arm")
        session.exec("tick 10")
        self.assertIn("horn_lockout=1", session.exec("faults")[0])
        self.assertIn("out_horn=0", session.exec("gates")[0])
        session.exec("hw release horn")
        session.exec("tick 40")
        session.exec("hw press horn")
        session.exec("tick 40")
        self.assertIn("out_horn=1", session.exec("gates")[0])

    def test_overcurrent_latches(self) -> None:
        session = Session()
        lines_of(
            session,
            """
            debug on
            config set oc_ma 100
            hw load head 300
            arm
            tick 10
            hold head on
            tick 120
            """,
        )
        self.assertIn("fault=1", session.exec("status")[0])
        self.assertIn("out_head=0", session.exec("gates")[0])
        session.exec("hold head on")
        session.exec("tick 10")
        self.assertIn("out_head=0", session.exec("gates")[0])
        session.exec("arm")
        session.exec("tick 10")
        self.assertIn("out_head=1023", session.exec("gates")[0])

    def test_uvlo_three_trips_latch(self) -> None:
        session = Session()
        session.exec("debug on")
        session.exec("arm")
        session.exec("tick 10")
        for _ in range(3):
            session.exec("hw power 4000")
            session.exec("tick 80")
            self.assertIn("uvlo=1", session.exec("status")[0])
            session.exec("hw power 4700")
            session.exec("tick 250")
        self.assertIn("fault=1", session.exec("status")[0])
        session.exec("hw power 4700")
        session.exec("tick 300")
        self.assertIn("fault=1", session.exec("status")[0])

    def test_sleep_abort_keeps_queued_arm(self) -> None:
        session = Session()
        session.exec("debug on")
        session.exec("sleep")
        started = session.exec("tick 10")
        self.assertTrue(any("evt sleep=start" in line for line in started))
        session.exec("arm")
        aborted = session.exec("tick 10")
        self.assertTrue(any("evt sleep=abort" in line for line in aborted))
        armed = session.exec("tick 10")
        self.assertTrue(any("evt arm=1" in line for line in armed))

    def test_deepsleep_keeps_arm_power_reset_clears_it(self) -> None:
        session = Session()
        session.exec("arm")
        session.exec("tick 10")
        session.exec("debug on")
        session.exec("sleep")
        session.exec("tick 10")
        entered = session.exec("tick 10")
        self.assertTrue(any("evt sleep=enter" in line for line in entered))
        self.assertIn("armed=1", session.exec("status")[0])
        self.assertIn("mode=parking", session.exec("status")[0])
        session.exec("hw wake")
        woke = session.exec("tick 10")
        self.assertTrue(any("evt wake=imu" in line for line in woke))
        session.exec("hw reset power")
        self.assertIn("armed=0", session.exec("status")[0])

    def test_gps_rejects_origin(self) -> None:
        session = Session()
        session.exec("hw gps 10.5 106.7")
        session.exec("tick 10")
        self.assertIn("gps_fix=1", session.exec("sense")[0])
        session.exec("hw gps 0 0")
        session.exec("tick 10")
        sense = session.exec("sense")[0]
        self.assertIn("gps_fix=0", sense)
        raw = bytes.fromhex(session.exec("snapshot")[0].split("hex=")[1])
        lat = int.from_bytes(raw[6:10], "little", signed=True)
        self.assertEqual(lat, 105000000)

    def test_failsafe_stall(self) -> None:
        session = Session()
        session.exec("arm")
        session.exec("tick 10")
        session.exec("debug on")
        session.exec("hold head on")
        session.exec("tick 10")
        self.assertIn("out_head=1023", session.exec("gates")[0])
        session.exec("hw stall on")
        session.exec("tick 50")
        self.assertIn("out_head=0", session.exec("gates")[0])
        self.assertIn("failsafe_count=1", session.exec("faults")[0])

    def test_inject_does_not_change_bus_voltage(self) -> None:
        session = Session()
        session.exec("debug on")
        session.exec("inject lux 10")
        session.exec("tick 10")
        self.assertIn("v=4700", session.exec("status")[0])

    def test_config_rejects_oc_above_cap(self) -> None:
        session = Session()
        session.exec("debug on")
        self.assertEqual(session.exec("config set oc_ma 3000"), ["err range"])
        self.assertIn("oc_ma=2500", session.exec("config")[0])

    def test_hold_without_debug_is_refused(self) -> None:
        session = Session()
        self.assertEqual(session.exec("hold head on"), ["err debug"])


if __name__ == "__main__":
    unittest.main()
