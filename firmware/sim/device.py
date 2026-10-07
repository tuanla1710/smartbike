"""Luật điều khiển V1 chạy trên bàn thử, cùng câu trả lời console với firmware."""

from __future__ import annotations

import struct

from sim.plant import I2C_ORDER, Plant

MASK = 0xFFFFFFFF


def elapsed(now: int, since: int) -> int:
    return (now - since) & MASK


def u32(value: int) -> int:
    return value & MASK


DEFAULTS: dict[str, int] = {
    "debounce_ms": 30,
    "lux_on": 100,
    "lux_off": 200,
    "lux_stale_ms": 1000,
    "on_duty": 1023,
    "blink_period_ms": 800,
    "blink_on_ms": 400,
    "stop_idle_s": 180,
    "sleep_after_s": 600,
    "alarm_motion_ms": 400,
    "alarm_s": 30,
    "alarm_gap_s": 5,
    "alarm_period_ms": 1000,
    "alarm_horn_ms": 200,
    "alarm_lamp_ms": 500,
    "motion_hold_ms": 250,
    "motion_stuck_s": 120,
    "horn_max_on_s": 30,
    "range_warn_mm": 4000,
    "range_stale_ms": 500,
    "power_stale_ms": 200,
    "uvlo_mv": 4200,
    "uvlo_recover_mv": 4600,
    "uvlo_enter_ms": 50,
    "uvlo_exit_ms": 200,
    "uvlo_trip_count": 3,
    "uvlo_window_ms": 10000,
    "oc_ma": 2500,
    "oc_ms": 100,
    "oc_immediate_ma": 3000,
    "failsafe_ms": 50,
    "sleep_ack_ms": 200,
    "horn_current_ma": 0,
    "shunt_cal": 1250,
}

SETTABLE: dict[str, tuple[int, int, bool, bool]] = {
    # name: min, max, needs_debug, saveable
    "horn_current_ma": (0, 5000, False, True),
    "shunt_cal": (1, 65535, False, True),
    "stop_idle_s": (5, 3600, True, False),
    "sleep_after_s": (5, 3600, True, False),
    "alarm_s": (1, 120, True, False),
    "alarm_gap_s": (0, 60, True, False),
    "alarm_motion_ms": (50, 5000, True, False),
    "debounce_ms": (0, 500, True, False),
    "oc_ma": (100, 2500, True, False),
    "uvlo_mv": (3000, 4500, True, False),
}

HELP = (
    "help",
    "status",
    "inputs",
    "sense",
    "power",
    "gates",
    "faults",
    "config",
    "snapshot",
    "watch <ms>",
    "watch off",
    "arm",
    "disarm",
    "ride start",
    "ride stop",
    "dismiss",
    "aux on",
    "aux off",
    "debug on",
    "debug off",
    "hold <kênh> on|off|<duty>",
    "hold off",
    "inject lux <n>|off",
    "inject motion on|off",
    "inject clear motion",
    "inject range <mm>|off",
    "inject pin low|high|off",
    "inject off",
    "config set <tên> <số>",
    "config save horn_current_ma|shunt_cal",
    "sleep",
    "i2c",
)

HOLD_PWM = ("head", "tail", "left", "right")
HOLD_GPIO = ("brake", "horn", "aux")


def crc8(payload: bytes) -> int:
    crc = 0
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


class _Switch:
    def __init__(self) -> None:
        self.candidate = False
        self.candidate_since = 0
        self.stable = False


class _Hold:
    def __init__(self, kind: str, duty: int, since: int) -> None:
        self.kind = kind  # on | off | duty
        self.duty = duty
        self.since = since


class Device:
    def __init__(self, plant: Plant, nvs: dict[str, int] | None = None, armed: bool = False) -> None:
        self.plant = plant
        self.nvs = dict(nvs or {"horn_current_ma": 0, "shunt_cal": 1250})
        self.cfg = dict(DEFAULTS)
        self.cfg["horn_current_ma"] = self.nvs["horn_current_ma"]
        self.cfg["shunt_cal"] = self.nvs["shunt_cal"]
        self.now = 0
        self.mode = "parking"
        self.armed = armed
        self._store_rtc()
        self.fault_latch = False
        self.debug = False
        self.aux_latch = False
        self.head_on = False
        self.switches = {name: _Switch() for name in ("left", "right", "horn", "light", "brake")}
        self.queue: list[tuple[str, str]] = []
        self.cmd_dropped = 0
        self.holds: dict[str, _Hold] = {}
        self.inj_lux: int | None = None
        self.inj_motion: bool | None = None
        self.inj_range: int | None = None
        self.inj_pin: bool | None = None
        self.motion_since: int | None = None
        self.quiet_since: int | None = 0
        self.alarm_since = 0
        self.alarm_ready_at = 0
        self.motion_deadline: int | None = None
        self.pin_high_since: int | None = None
        self.motion_fault = False
        self.horn_lockout = False
        self.horn_since: int | None = None
        self.uvlo = False
        self.uvlo_low_since: int | None = None
        self.uvlo_high_since: int | None = None
        self.uvlo_trips: list[int] = []
        self.uvlo_count = 0
        self.oc_since: int | None = None
        self.failsafe_count = 0
        self.stalled = False
        self.failsafe_tripped = False
        self.last_kick = 0
        self.sleep_phase = "run"  # run | wait
        self.sleep_since = 0
        self.xshut_high = False
        self.sensors_saw_prepare = False
        self.lux_sample: int | None = 500
        self.lux_ms = 0
        self.range_sample: int | None = None
        self.range_ms = 0
        self.power_ms = 0
        self.bus_mv = 4700
        self.current_ma = 0
        self.energy_mwh = 0
        self.lat_e7 = 0
        self.lon_e7 = 0
        self.gps_fix = False
        self.gps_ms: int | None = None
        self.scan_pending = False
        self.asleep = False
        self.want = self._blank_act()
        self.out = self._blank_act()
        self.inhibit = "disarmed"
        self.motion = False
        self.obstacle = False
        self.eff_lux = 500
        self.eff_range = 0xFFFF
        self.events: list[str] = []

    def reset(self, reason: str) -> list[str]:
        armed = self.armed if reason == "deepsleep" and self._rtc_ok() else False
        nvs = dict(self.nvs)
        plant = self.plant
        self.__init__(plant, nvs=nvs, armed=armed)
        self.asleep = False
        return ["ok"]

    def handle(self, line: str) -> list[str]:
        if len(line.encode("utf-8")) > 80 or "  " in line:
            return ["err syntax"]
        parts = line.split(" ")
        if any(part == "" for part in parts):
            return ["err syntax"]
        verb = parts[0]
        if verb == "help" and len(parts) == 1:
            return [f"ok cmd={item}" for item in HELP]
        if verb == "status" and len(parts) == 1:
            return [self._status_line()]
        if verb == "inputs" and len(parts) == 1:
            return [self._inputs_line()]
        if verb == "sense" and len(parts) == 1:
            return [self._sense_line()]
        if verb == "power" and len(parts) == 1:
            return [self._power_line()]
        if verb == "gates" and len(parts) == 1:
            return [self._gates_line()]
        if verb == "faults" and len(parts) == 1:
            return [self._faults_line()]
        if verb == "config" and len(parts) == 1:
            return [self._config_line()]
        if verb == "snapshot" and len(parts) == 1:
            return [f"ok hex={self.snapshot_hex()}"]
        if verb == "watch" and len(parts) == 2 and parts[1] == "off":
            return ["ok"]
        if verb == "watch" and len(parts) == 2 and parts[1].isdigit():
            ms = int(parts[1])
            if ms < 100 or ms > 5000:
                return ["err range"]
            return ["ok"]
        if verb == "debug" and len(parts) == 2 and parts[1] in ("on", "off"):
            self.debug = parts[1] == "on"
            if not self.debug:
                self.holds.clear()
                self._clear_inject()
            return ["ok"]
        if verb == "hold":
            return self._hold(parts)
        if verb == "inject":
            return self._inject(parts)
        if verb == "config" and len(parts) >= 2:
            return self._config_cmd(parts)
        if verb == "i2c" and len(parts) == 1:
            self.scan_pending = True
            return ["ok queued"]
        if verb == "sleep" and len(parts) == 1:
            if not self.debug:
                return ["err debug"]
            return self._enqueue("sleep", "")
        queued = {
            ("arm",): ("arm", ""),
            ("disarm",): ("disarm", ""),
            ("ride", "start"): ("ride_start", ""),
            ("ride", "stop"): ("ride_stop", ""),
            ("dismiss",): ("dismiss", ""),
            ("aux", "on"): ("aux_on", ""),
            ("aux", "off"): ("aux_off", ""),
        }
        key = tuple(parts)
        if key in queued:
            name, arg = queued[key]
            return self._enqueue(name, arg)
        return ["err syntax"]

    def advance(self, ms: int) -> list[str]:
        if ms < 0 or ms > 3_600_000:
            return ["err range"]
        lines: list[str] = []
        steps = ms // 10
        for _ in range(steps):
            self.now = u32(self.now + 10)
            if self.asleep:
                if not self.plant.gpio38:
                    continue
                self.asleep = False
                lines.append("evt wake=imu")
            if self.stalled:
                if not self.failsafe_tripped and elapsed(self.now, self.last_kick) >= self.cfg["failsafe_ms"]:
                    self.failsafe_tripped = True
                    self.failsafe_count += 1
                    self.out = self._blank_act()
                    self.inhibit = "fault"
                continue
            lines.extend(self._tick())
            self.last_kick = self.now
            self.failsafe_tripped = False
        return lines

    def snapshot_hex(self) -> str:
        mode = {"parking": 1, "riding": 2, "alarm": 3}[self.mode]
        flags = 0
        if self.gps_fix:
            flags |= 1 << 0
        if self.obstacle:
            flags |= 1 << 1
        if self.motion:
            flags |= 1 << 2
        if self.armed:
            flags |= 1 << 3
        if len(self.plant.i2c) < 4:
            flags |= 1 << 4
        if self.fault_latch:
            flags |= 1 << 5
        if self.inhibit != "none":
            flags |= 1 << 6
        if self.motion_fault:
            flags |= 1 << 7
        lamps = 0
        if self.out["head"]:
            lamps |= 1 << 0
        if self.out["tail"]:
            lamps |= 1 << 1
        if self.out["brake"]:
            lamps |= 1 << 2
        if self.out["left"]:
            lamps |= 1 << 3
        if self.out["right"]:
            lamps |= 1 << 4
        if self.switches["left"].stable and self.switches["right"].stable:
            lamps |= 1 << 5
        if self.out["horn"]:
            lamps |= 1 << 6
        if self.out["aux"]:
            lamps |= 1 << 7
        power_dw = (self.bus_mv * self.current_ma) // 100_000
        raw = struct.pack(
            "<BBHHiiHhhIB7s",
            mode,
            flags,
            self.eff_lux & 0xFFFF,
            self.eff_range & 0xFFFF,
            self.lat_e7,
            self.lon_e7,
            self.bus_mv & 0xFFFF,
            max(-32768, min(32767, self.current_ma)),
            max(-32768, min(32767, power_dw)),
            self.energy_mwh & 0xFFFFFFFF,
            lamps,
            b"\x00" * 7,
        )
        if len(raw) != 32:
            raise RuntimeError(f"snapshot length {len(raw)}")
        return raw.hex()

    def _tick(self) -> list[str]:
        self.events = []
        self._sample_world()
        if self.sleep_phase == "wait":
            self._sleep_slice()
            return list(self.events)
        self._sample_switches()
        cmd = self._pop()
        self._apply_side(cmd)
        self._mode_step(cmd)
        if self.sleep_phase == "wait":
            self._zero_outputs_for_sleep()
            return list(self.events)
        self._actuate()
        self._observe_power()
        if self.scan_pending:
            self.scan_pending = False
            present = [f"{addr:02x}" for addr in I2C_ORDER if addr in self.plant.i2c]
            self.events.append("ok addr=" + ",".join(present))
        return list(self.events)

    def _sample_world(self) -> None:
        now = self.now
        plant = self.plant
        if plant.power_alive and 0x40 in plant.i2c:
            self.power_ms = now
            self.bus_mv = plant.bus_mv
        if 0x23 in plant.i2c:
            self.lux_sample = plant.lux
            self.lux_ms = now
        if 0x29 in plant.i2c and plant.range_mm is not None:
            self.range_sample = plant.range_mm
            self.range_ms = now
        elif 0x29 not in plant.i2c:
            pass
        source = plant.motion
        if self.inj_motion is True:
            source = True
        elif self.inj_motion is False:
            source = False
        if source:
            self.motion_deadline = u32(now + self.cfg["motion_hold_ms"])
        self.motion = self._before(self.motion_deadline, self.cfg["motion_hold_ms"])
        if plant.gpio38:
            if self.pin_high_since is None:
                self.pin_high_since = now
            if elapsed(now, self.pin_high_since) >= self.cfg["motion_stuck_s"] * 1000:
                self.motion_fault = True
        else:
            self.pin_high_since = None
            self.motion_fault = False
        self._sample_gps()

    def _sample_gps(self) -> None:
        mode = self.plant.gps_mode
        if mode == "fix":
            lat = self.plant.gps_lat
            lon = self.plant.gps_lon
            if abs(lat) <= 90 and abs(lon) <= 180 and not (lat == 0 and lon == 0):
                self.lat_e7 = int(round(lat * 1e7))
                self.lon_e7 = int(round(lon * 1e7))
                self.gps_fix = True
                self.gps_ms = self.now
            else:
                self.gps_fix = False
        elif mode == "bad":
            self.gps_fix = False
        if self.gps_ms is None or elapsed(self.now, self.gps_ms) >= 5000:
            self.gps_fix = False

    def _sample_switches(self) -> None:
        limit = self.cfg["debounce_ms"]
        for name, sw in self.switches.items():
            raw = self.plant.switch_closed(name)
            if raw != sw.candidate:
                sw.candidate = raw
                sw.candidate_since = self.now
            elif elapsed(self.now, sw.candidate_since) >= limit:
                sw.stable = sw.candidate

    def _apply_side(self, cmd: tuple[str, str] | None) -> None:
        if cmd is None:
            return
        name = cmd[0]
        if name == "arm":
            self._set_armed(True)
            self._set_fault(False)
        elif name == "disarm":
            self._set_armed(False)
            self._set_fault(False)
            self.aux_latch = False
            self.horn_lockout = False
            self.horn_since = None
        elif name == "aux_on":
            self.aux_latch = True
        elif name == "aux_off":
            self.aux_latch = False
        elif name == "dismiss" and self.mode != "alarm":
            self._set_fault(False)

    def _mode_step(self, cmd: tuple[str, str] | None) -> None:
        name = cmd[0] if cmd else ""
        self._update_motion_marks()
        if name == "sleep":
            self._manual_sleep()
            if self.sleep_phase == "wait":
                return
        if self.mode == "riding":
            quiet = self._mark_age(self.quiet_since)
            if name == "ride_stop" or (quiet is not None and quiet >= self.cfg["stop_idle_s"] * 1000):
                self._enter_parking()
                return
            if name == "ride_start":
                self._reject("ride_start")
            return
        if self.mode == "alarm":
            age = elapsed(self.now, self.alarm_since)
            if name == "dismiss" or age >= self.cfg["alarm_s"] * 1000:
                self._set_fault(False)
                self._enter_parking()
                return
            if name == "ride_start":
                self._reject("ride_start")
            if name == "ride_stop":
                self._reject("ride_stop")
            return
        if name == "ride_start":
            self._set_mode("riding")
            return
        if name == "ride_stop":
            self._reject("ride_stop")
            return
        if (
            not self.motion_fault
            and self.now >= self.alarm_ready_at
            and self.motion_since is not None
            and elapsed(self.now, self.motion_since) >= self.cfg["alarm_motion_ms"]
        ):
            self.alarm_since = self.now
            self._set_mode("alarm")
            return
        quiet = self._mark_age(self.quiet_since)
        if quiet is not None and quiet >= self.cfg["sleep_after_s"] * 1000 and self._pin_low():
            self._begin_sleep()

    def _manual_sleep(self) -> None:
        if self.mode != "parking":
            self.events.append("evt sleep=abort mode")
            return
        if self.motion:
            self.events.append("evt sleep=abort motion")
            return
        if not self._pin_low():
            self.events.append("evt sleep=abort pin")
            return
        self._begin_sleep()

    def _begin_sleep(self) -> None:
        self.sleep_phase = "wait"
        self.sleep_since = self.now
        self.sensors_saw_prepare = False
        self.xshut_high = False
        self.events.append("evt sleep=start")

    def _sleep_slice(self) -> None:
        self._sample_switches()
        if self.queue or self.motion or not self._pin_low():
            self.sleep_phase = "run"
            self.events.append("evt sleep=abort")
            return
        if not self.sensors_saw_prepare:
            self.sensors_saw_prepare = True
            self.xshut_high = False
        if elapsed(self.now, self.sleep_since) >= 10 or elapsed(self.now, self.sleep_since) >= self.cfg["sleep_ack_ms"]:
            self._enter_deep_sleep()

    def _enter_deep_sleep(self) -> None:
        self.xshut_high = False
        armed = self.armed
        nvs = dict(self.nvs)
        plant = self.plant
        self.__init__(plant, nvs=nvs, armed=armed)
        self.asleep = True
        self.events = ["evt sleep=enter"]

    def _zero_outputs_for_sleep(self) -> None:
        self.want = self._blank_act()
        self.out = self._blank_act()
        self._set_inhibit("none")

    def _actuate(self) -> None:
        if self.mode == "alarm":
            want = self._alarm_policy()
        else:
            want = self._ride_policy()
        if "aux" not in self.holds:
            want["aux"] = self.aux_latch
        self._apply_holds(want)
        self.want = {key: want[key] for key in want}
        self._horn_budget(want)
        reason = self._inhibit_reason()
        if reason != "none":
            self.out = self._blank_act()
        else:
            self.out = {key: want[key] for key in want}
        self._set_inhibit(reason)
        self._integrate_energy()

    def _ride_policy(self) -> dict:
        act = self._blank_act()
        lux, lux_ok = self._effective_lux()
        light = self.switches["light"].stable
        if light:
            act["head"] = self.cfg["on_duty"]
        else:
            if lux_ok:
                if lux < self.cfg["lux_on"]:
                    self.head_on = True
                elif lux > self.cfg["lux_off"]:
                    self.head_on = False
            act["head"] = self.cfg["on_duty"] if self.head_on else 0
        self.eff_lux = lux if lux_ok else self.eff_lux
        if not lux_ok and self.inj_lux is None and self.lux_sample is not None:
            self.eff_lux = self.lux_sample
        act["tail"] = self.cfg["on_duty"] if self.mode == "riding" else 0
        act["brake"] = self.switches["brake"].stable
        self._fill_turn(act)
        self._fill_horn(act)
        self._fill_range()
        return act

    def _alarm_policy(self) -> dict:
        act = self._blank_act()
        period = self.cfg["alarm_period_ms"]
        age = elapsed(self.now, self.alarm_since) % period
        if age < self.cfg["alarm_horn_ms"]:
            act["horn"] = True
            act["horn_from_alarm"] = True
        if age < self.cfg["alarm_lamp_ms"]:
            duty = self.cfg["on_duty"]
            act["head"] = act["tail"] = act["left"] = act["right"] = duty
            act["left_lit"] = act["right_lit"] = True
            act["brake"] = True
        self._fill_range()
        _, lux_ok = self._effective_lux()
        if lux_ok and self.inj_lux is not None:
            self.eff_lux = self.inj_lux
        return act

    def _fill_turn(self, act: dict) -> None:
        phase_on = (self.now % self.cfg["blink_period_ms"]) < self.cfg["blink_on_ms"]
        left = self.switches["left"].stable
        right = self.switches["right"].stable
        if left and right:
            act["left_lit"] = act["right_lit"] = True
        elif left:
            act["left_lit"] = True
        elif right:
            act["right_lit"] = True
        duty = self.cfg["on_duty"]
        act["left"] = duty if act["left_lit"] and phase_on else 0
        act["right"] = duty if act["right_lit"] and phase_on else 0

    def _fill_horn(self, act: dict) -> None:
        held = self.switches["horn"].stable
        if not held:
            act["horn"] = False
            self.horn_lockout = False
            self.horn_since = None
            return
        if self.horn_lockout:
            act["horn"] = False
            return
        if self.horn_since is None:
            self.horn_since = self.now
        if elapsed(self.now, self.horn_since) >= self.cfg["horn_max_on_s"] * 1000:
            self.horn_lockout = True
            act["horn"] = False
            return
        act["horn"] = True

    def _fill_range(self) -> None:
        value, ok = self._effective_range()
        if not ok:
            self.obstacle = False
            self.eff_range = 0xFFFF
            return
        self.eff_range = value
        self.obstacle = value < self.cfg["range_warn_mm"]

    def _apply_holds(self, act: dict) -> None:
        expired = False
        for name in list(self.holds):
            hold = self.holds[name]
            if elapsed(self.now, hold.since) >= 30_000:
                del self.holds[name]
                expired = True
                continue
            if name in ("left", "right"):
                self._apply_turn_hold(act, name, hold)
            elif name in ("head", "tail"):
                if hold.kind == "on":
                    act[name] = self.cfg["on_duty"]
                elif hold.kind == "off":
                    act[name] = 0
                else:
                    act[name] = hold.duty
            elif hold.kind == "on":
                act[name] = True
                act["horn_from_alarm"] = False if name == "horn" else act["horn_from_alarm"]
            else:
                act[name] = False
        if expired:
            self.events.append("evt hold=off")

    def _apply_turn_hold(self, act: dict, name: str, hold: _Hold) -> None:
        phase_on = (self.now % self.cfg["blink_period_ms"]) < self.cfg["blink_on_ms"]
        lit_key = "left_lit" if name == "left" else "right_lit"
        if hold.kind == "on":
            act[lit_key] = True
            act[name] = self.cfg["on_duty"] if phase_on else 0
        elif hold.kind == "off":
            act[lit_key] = False
            act[name] = 0
        else:
            act[name] = hold.duty
            act[lit_key] = hold.duty != 0

    def _horn_budget(self, act: dict) -> None:
        if act["horn_from_alarm"] or self.cfg["horn_current_ma"] != 0:
            return
        if act["head"] and act["tail"] and (act["left_lit"] or act["right_lit"]):
            act["horn"] = False

    def _inhibit_reason(self) -> str:
        if not self._power_valid():
            return "power"
        if self.fault_latch:
            return "fault"
        if self.uvlo:
            return "uvlo"
        if not self.armed:
            return "disarmed"
        return "none"

    def _observe_power(self) -> None:
        if not self._power_valid():
            self.current_ma = 0
            return
        duty = {name: int(self.out[name]) for name in ("head", "tail", "left", "right")}
        on = {name: bool(self.out[name]) for name in ("brake", "horn", "aux")}
        self.current_ma = self.plant.current_ma(duty, on)
        self.bus_mv = self.plant.bus_mv
        now = self.now
        if self.current_ma >= self.cfg["oc_immediate_ma"] or (
            self.current_ma > self.cfg["oc_ma"]
            and self.oc_since is not None
            and elapsed(now, self.oc_since) >= self.cfg["oc_ms"]
        ):
            self._set_fault(True)
            self.out = self._blank_act()
            self.current_ma = 0
            self._set_inhibit("fault")
        if self._power_valid() and self.current_ma > self.cfg["oc_ma"]:
            if self.oc_since is None:
                self.oc_since = now
        else:
            self.oc_since = None
        self._update_uvlo()

    def _update_uvlo(self) -> None:
        if not self._power_valid():
            self.uvlo_low_since = None
            self.uvlo_high_since = None
            return
        bus = self.bus_mv
        now = self.now
        if bus < self.cfg["uvlo_mv"]:
            self.uvlo_high_since = None
            if self.uvlo_low_since is None:
                self.uvlo_low_since = now
            if not self.uvlo and elapsed(now, self.uvlo_low_since) >= self.cfg["uvlo_enter_ms"]:
                self.uvlo = True
                self.uvlo_count += 1
                self.uvlo_trips.append(now)
                window = self.cfg["uvlo_window_ms"]
                self.uvlo_trips = [stamp for stamp in self.uvlo_trips if elapsed(now, stamp) <= window]
                if len(self.uvlo_trips) >= self.cfg["uvlo_trip_count"]:
                    self._set_fault(True)
        elif bus >= self.cfg["uvlo_recover_mv"]:
            self.uvlo_low_since = None
            if self.uvlo_high_since is None:
                self.uvlo_high_since = now
            if self.uvlo and not self.fault_latch and elapsed(now, self.uvlo_high_since) >= self.cfg["uvlo_exit_ms"]:
                self.uvlo = False
        else:
            self.uvlo_low_since = None
            self.uvlo_high_since = None

    def _integrate_energy(self) -> None:
        # mWh += mV * mA * ms / 3.6e12
        delta = self.bus_mv * self.current_ma * 10
        self.energy_mwh += delta // 3_600_000_000_000

    def _effective_lux(self) -> tuple[int, bool]:
        if self.inj_lux is not None:
            return self.inj_lux, True
        if self.lux_sample is None:
            return 0, False
        if elapsed(self.now, self.lux_ms) >= self.cfg["lux_stale_ms"]:
            return self.lux_sample, False
        return self.lux_sample, True

    def _effective_range(self) -> tuple[int, bool]:
        if self.inj_range is not None:
            return self.inj_range, True
        if self.range_sample is None:
            return 0, False
        if elapsed(self.now, self.range_ms) >= self.cfg["range_stale_ms"]:
            return 0, False
        return self.range_sample, True

    def _power_valid(self) -> bool:
        return elapsed(self.now, self.power_ms) < self.cfg["power_stale_ms"]

    def _pin_low(self) -> bool:
        if self.inj_pin is not None:
            return not self.inj_pin
        return not self.plant.gpio38

    def _before(self, deadline: int | None, span: int) -> bool:
        if deadline is None:
            return False
        remain = elapsed(deadline, self.now)
        return 0 < remain <= span

    def _update_motion_marks(self) -> None:
        if self.motion:
            self.quiet_since = None
            if self.motion_since is None:
                self.motion_since = self.now
        else:
            self.motion_since = None
            if self.quiet_since is None:
                self.quiet_since = self.now

    def _mark_age(self, mark: int | None) -> int | None:
        if mark is None:
            return None
        return elapsed(self.now, mark)

    def _enter_parking(self) -> None:
        self.alarm_ready_at = u32(self.now + self.cfg["alarm_gap_s"] * 1000)
        if self.motion:
            self.motion_since = self.now
            self.quiet_since = None
        else:
            self.motion_since = None
            self.quiet_since = self.now
        self._set_mode("parking")

    def _pop(self) -> tuple[str, str] | None:
        if not self.queue:
            return None
        return self.queue.pop(0)

    def _enqueue(self, name: str, arg: str) -> list[str]:
        if len(self.queue) >= 4:
            self.cmd_dropped += 1
            return ["err queue"]
        self.queue.append((name, arg))
        return ["ok queued"]

    def _hold(self, parts: list[str]) -> list[str]:
        if not self.debug:
            return ["err debug"]
        if parts == ["hold", "off"]:
            self.holds.clear()
            return ["ok"]
        if len(parts) != 3:
            return ["err syntax"]
        name, how = parts[1], parts[2]
        if name not in HOLD_PWM and name not in HOLD_GPIO:
            return ["err syntax"]
        if name in HOLD_GPIO and how not in ("on", "off"):
            return ["err syntax"]
        if how == "on":
            self.holds[name] = _Hold("on", self.cfg["on_duty"], self.now)
        elif how == "off":
            self.holds[name] = _Hold("off", 0, self.now)
        elif how.isdigit() and name in HOLD_PWM:
            duty = int(how)
            if duty > 1023:
                return ["err range"]
            self.holds[name] = _Hold("duty", duty, self.now)
        else:
            return ["err syntax"]
        return ["ok"]

    def _inject(self, parts: list[str]) -> list[str]:
        if not self.debug:
            return ["err debug"]
        if parts == ["inject", "off"]:
            self._clear_inject()
            return ["ok"]
        if parts == ["inject", "clear", "motion"]:
            self.inj_motion = None
            return ["ok"]
        if len(parts) != 3:
            return ["err syntax"]
        kind, value = parts[1], parts[2]
        if kind == "lux" and value == "off":
            self.inj_lux = None
            return ["ok"]
        if kind == "lux" and value.isdigit():
            number = int(value)
            if number > 65535:
                return ["err range"]
            self.inj_lux = number
            return ["ok"]
        if kind == "motion" and value in ("on", "off"):
            self.inj_motion = value == "on"
            return ["ok"]
        if kind == "range" and value == "off":
            self.inj_range = None
            return ["ok"]
        if kind == "range" and value.isdigit():
            number = int(value)
            if number > 65534:
                return ["err range"]
            self.inj_range = number
            return ["ok"]
        if kind == "pin" and value in ("low", "high", "off"):
            self.inj_pin = None if value == "off" else value == "high"
            return ["ok"]
        return ["err syntax"]

    def _config_cmd(self, parts: list[str]) -> list[str]:
        if parts[1] == "set" and len(parts) == 4 and parts[3].isdigit():
            name = parts[2]
            if name not in SETTABLE:
                return ["err syntax"]
            lo, hi, needs_debug, _save = SETTABLE[name]
            if needs_debug and not self.debug:
                return ["err debug"]
            number = int(parts[3])
            if number < lo or number > hi:
                return ["err range"]
            self.cfg[name] = number
            return ["ok"]
        if parts[1] == "save" and len(parts) == 3:
            name = parts[2]
            if name not in ("horn_current_ma", "shunt_cal"):
                return ["err syntax"]
            self.nvs[name] = self.cfg[name]
            return ["ok"]
        return ["err syntax"]

    def _clear_inject(self) -> None:
        self.inj_lux = None
        self.inj_motion = None
        self.inj_range = None
        self.inj_pin = None

    def _set_mode(self, mode: str) -> None:
        if self.mode != mode:
            self.mode = mode
            self.events.append(f"evt mode={mode}")
        else:
            self.mode = mode

    def _set_armed(self, armed: bool) -> None:
        if self.armed != armed:
            self.armed = armed
            self._store_rtc()
            self.events.append(f"evt arm={1 if armed else 0}")
        else:
            self.armed = armed
            self._store_rtc()

    def _set_fault(self, fault: bool) -> None:
        if self.fault_latch != fault:
            self.fault_latch = fault
            self.events.append(f"evt fault={1 if fault else 0}")
        else:
            self.fault_latch = fault
        if not fault:
            self.uvlo_trips.clear()
            self.oc_since = None

    def _set_inhibit(self, reason: str) -> None:
        if self.inhibit != reason:
            self.inhibit = reason
            self.events.append(f"evt inhibit={reason}")
        else:
            self.inhibit = reason

    def _reject(self, name: str) -> None:
        self.events.append(f"evt reject={name} mode")

    def _store_rtc(self) -> None:
        self._rtc_flag = self.armed
        self._rtc_crc = crc8(bytes([1 if self.armed else 0]))

    def _rtc_ok(self) -> bool:
        return self._rtc_crc == crc8(bytes([1 if self._rtc_flag else 0]))

    def _blank_act(self) -> dict:
        return {
            "head": 0,
            "tail": 0,
            "left": 0,
            "right": 0,
            "left_lit": False,
            "right_lit": False,
            "brake": False,
            "horn": False,
            "aux": False,
            "horn_from_alarm": False,
        }

    def _status_line(self) -> str:
        return (
            "ok "
            f"mode={self.mode} armed={int(self.armed)} fault={int(self.fault_latch)} "
            f"uvlo={int(self.uvlo)} inhibit={self.inhibit} debug={int(self.debug)} "
            f"v={self.bus_mv} i={self.current_ma} lux={self.eff_lux} "
            f"range={self.eff_range} motion={int(self.motion)}"
        )

    def _inputs_line(self) -> str:
        bits = []
        for name, sw in self.switches.items():
            raw = self.plant.switch_closed(name)
            bits.append(f"raw_{name}={int(raw)} stable_{name}={int(sw.stable)}")
        hazard = self.switches["left"].stable and self.switches["right"].stable
        bits.append(f"hazard={int(hazard)}")
        return "ok " + " ".join(bits)

    def _sense_line(self) -> str:
        present = ",".join(f"{addr:02x}" for addr in I2C_ORDER if addr in self.plant.i2c)
        lux_age = elapsed(self.now, self.lux_ms) if self.lux_sample is not None else -1
        range_age = elapsed(self.now, self.range_ms) if self.range_sample is not None else -1
        power_age = elapsed(self.now, self.power_ms)
        inj = []
        if self.inj_lux is not None:
            inj.append("lux")
        if self.inj_motion is not None:
            inj.append("motion")
        if self.inj_range is not None:
            inj.append("range")
        if self.inj_pin is not None:
            inj.append("pin")
        sensor_range = 0xFFFF if self.range_sample is None else self.range_sample
        sensor_lux = 0 if self.lux_sample is None else self.lux_sample
        return (
            f"ok addr={present} lux={sensor_lux} lux_eff={self.eff_lux} "
            f"range={sensor_range} range_eff={self.eff_range} "
            f"lux_age={lux_age} range_age={range_age} power_age={power_age} "
            f"gps_fix={int(self.gps_fix)} inj={','.join(inj)}"
        )

    def _power_line(self) -> str:
        power_dw = (self.bus_mv * self.current_ma) // 100_000
        return (
            f"ok bus_mv={self.bus_mv} current_ma={self.current_ma} "
            f"power_dw={power_dw} energy_mwh={self.energy_mwh} "
            f"power_valid={int(self._power_valid())}"
        )

    def _gates_line(self) -> str:
        names = ("head", "tail", "left", "right", "brake", "horn", "aux")
        parts = []
        for name in names:
            parts.append(f"want_{name}={int(self.want[name])}")
        for name in names:
            parts.append(f"out_{name}={int(self.out[name])}")
        return "ok " + " ".join(parts)

    def _faults_line(self) -> str:
        return (
            "ok "
            f"fault_latch={int(self.fault_latch)} uvlo_count={self.uvlo_count} "
            f"cmd_dropped={self.cmd_dropped} failsafe_count={self.failsafe_count} "
            f"motion_fault={int(self.motion_fault)} horn_lockout={int(self.horn_lockout)}"
        )

    def _config_line(self) -> str:
        items = [f"{key}={self.cfg[key]}" for key in DEFAULTS]
        return "ok " + " ".join(items)
