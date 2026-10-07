"""Ghép bàn thử với console. `hw` và `tick` không đi vào firmware."""

from __future__ import annotations

import time

from sim.device import Device
from sim.plant import LOADS, SWITCHES, Plant

HW_HELP = (
    "press/release <left|right|horn|light|brake|hazard>",
    "lux <0..65535>",
    "range <0..65534>|none",
    "motion on|off",
    "pin high|low",
    "power <mV>|dead|auto",
    "load <kênh> <mA>",
    "i2c <40|23|29|68> on|off",
    "gps <lat> <lon>|bad|none",
    "stall on|off",
    "reset power|wdt|deepsleep",
    "wake",
    "status",
)


class Session:
    def __init__(self) -> None:
        self.plant = Plant()
        self.dev = Device(self.plant)

    def exec(self, line: str) -> list[str]:
        text = line.strip()
        if not text or text.startswith("#"):
            return []
        if text == "hw help":
            return [f"ok hw={item}" for item in HW_HELP]
        if text == "hw" or text.startswith("hw "):
            return self._hw(text.split(" "))
        if text == "tick" or text.startswith("tick "):
            return self._tick(text.split(" "))
        return self.dev.handle(text)

    def _tick(self, parts: list[str]) -> list[str]:
        if len(parts) != 2 or not parts[1].isdigit():
            return ["err syntax"]
        return self.dev.advance(int(parts[1]))

    def _hw(self, parts: list[str]) -> list[str]:
        if len(parts) < 2:
            return ["err syntax"]
        cmd = parts[1:]
        plant = self.plant
        if cmd[0] == "status" and len(cmd) == 1:
            pressed = ",".join(name for name in SWITCHES if plant.pressed[name]) or "-"
            rng = "none" if plant.range_mm is None else str(plant.range_mm)
            return [
                "ok "
                f"lux={plant.lux} range={rng} motion={int(plant.motion)} "
                f"pin={int(plant.gpio38)} bus_mv={plant.bus_mv} "
                f"power={int(plant.power_alive)} pressed={pressed}"
            ]
        if cmd[0] == "press" and len(cmd) == 2 and cmd[1] in SWITCHES:
            plant.pressed[cmd[1]] = True
            return ["ok"]
        if cmd[0] == "release" and len(cmd) == 2 and cmd[1] in SWITCHES:
            plant.pressed[cmd[1]] = False
            return ["ok"]
        if cmd[0] == "lux" and len(cmd) == 2 and cmd[1].isdigit():
            value = int(cmd[1])
            if value > 65535:
                return ["err range"]
            plant.lux = value
            return ["ok"]
        if cmd[0] == "range" and len(cmd) == 2 and cmd[1] == "none":
            plant.range_mm = None
            return ["ok"]
        if cmd[0] == "range" and len(cmd) == 2 and cmd[1].isdigit():
            value = int(cmd[1])
            if value > 65534:
                return ["err range"]
            plant.range_mm = value
            return ["ok"]
        if cmd[0] == "motion" and len(cmd) == 2 and cmd[1] in ("on", "off"):
            plant.motion = cmd[1] == "on"
            return ["ok"]
        if cmd[0] == "pin" and len(cmd) == 2 and cmd[1] in ("high", "low"):
            plant.gpio38 = cmd[1] == "high"
            return ["ok"]
        if cmd[0] == "power" and len(cmd) == 2 and cmd[1] == "dead":
            plant.power_alive = False
            return ["ok"]
        if cmd[0] == "power" and len(cmd) == 2 and cmd[1] == "auto":
            plant.power_alive = True
            plant.bus_mv = 4700
            return ["ok"]
        if cmd[0] == "power" and len(cmd) == 2 and cmd[1].isdigit():
            plant.power_alive = True
            plant.bus_mv = int(cmd[1])
            return ["ok"]
        if cmd[0] == "load" and len(cmd) == 3 and cmd[1] in LOADS and cmd[2].isdigit():
            plant.loads_ma[cmd[1]] = int(cmd[2])
            return ["ok"]
        if cmd[0] == "i2c" and len(cmd) == 3 and cmd[1] in ("40", "23", "29", "68") and cmd[2] in ("on", "off"):
            addr = int(cmd[1], 16)
            if cmd[2] == "on":
                plant.i2c.add(addr)
            else:
                plant.i2c.discard(addr)
            return ["ok"]
        if cmd[0] == "gps" and len(cmd) == 2 and cmd[1] in ("bad", "none"):
            plant.gps_mode = cmd[1]
            return ["ok"]
        if cmd[0] == "gps" and len(cmd) == 3:
            try:
                plant.gps_lat = float(cmd[1])
                plant.gps_lon = float(cmd[2])
            except ValueError:
                return ["err syntax"]
            plant.gps_mode = "fix"
            return ["ok"]
        if cmd[0] == "stall" and len(cmd) == 2 and cmd[1] in ("on", "off"):
            self.dev.stalled = cmd[1] == "on"
            if not self.dev.stalled:
                self.dev.failsafe_tripped = False
                self.dev.last_kick = self.dev.now
            return ["ok"]
        if cmd[0] == "reset" and len(cmd) == 2 and cmd[1] in ("power", "wdt", "deepsleep"):
            return self.dev.reset(cmd[1])
        if cmd[0] == "wake" and len(cmd) == 1:
            plant.gpio38 = True
            return ["ok"]
        return ["err syntax"]


class SerialSession:
    """Cùng runner, nói với firmware thật qua USB Serial/JTAG."""

    def __init__(self, port: str, baud: int = 115200) -> None:
        import serial

        self.ser = serial.Serial(port, baud, timeout=0.2)

    def exec(self, line: str) -> list[str]:
        text = line.strip()
        if not text or text.startswith("#"):
            return []
        if text.startswith("hw"):
            return ["err sim-only"]
        if text.startswith("tick"):
            parts = text.split(" ")
            if len(parts) != 2 or not parts[1].isdigit():
                return ["err syntax"]
            time.sleep(int(parts[1]) / 1000)
            return self._drain(0.05)
        self.ser.write((text + "\n").encode())
        self.ser.flush()
        return self._drain(0.2)

    def _drain(self, wait_s: float) -> list[str]:
        deadline = time.monotonic() + wait_s
        lines: list[str] = []
        while time.monotonic() < deadline:
            raw = self.ser.readline()
            if not raw:
                if lines:
                    break
                continue
            lines.append(raw.decode("utf-8", errors="replace").strip())
        return lines
