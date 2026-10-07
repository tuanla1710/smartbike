"""Bàn thử giả. Số ở đây là thế giới vật lý, chưa qua debounce hay inject."""

from __future__ import annotations


SWITCHES = ("left", "right", "horn", "light", "brake", "hazard")
LOADS = ("head", "tail", "left", "right", "brake", "horn", "aux")
I2C_ORDER = (0x40, 0x23, 0x29, 0x68)


class Plant:
    def __init__(self) -> None:
        self.pressed = {name: False for name in SWITCHES}
        self.lux = 500
        self.range_mm: int | None = None
        self.motion = False
        self.gpio38 = False
        self.bus_mv = 4700
        self.power_alive = True
        self.i2c = set(I2C_ORDER)
        self.loads_ma = {
            "head": 200,
            "tail": 80,
            "left": 80,
            "right": 80,
            "brake": 80,
            "horn": 400,
            "aux": 0,
        }
        self.gps_mode = "none"  # none | fix | bad
        self.gps_lat = 0.0
        self.gps_lon = 0.0

    def switch_closed(self, name: str) -> bool:
        if name in ("left", "right") and self.pressed["hazard"]:
            return True
        return self.pressed[name]

    def current_ma(self, duty: dict[str, int], on: dict[str, bool]) -> int:
        total = 0
        for name in ("head", "tail", "left", "right"):
            span = self.loads_ma[name] * duty[name]
            total += span // 1023
        for name in ("brake", "horn", "aux"):
            if on[name]:
                total += self.loads_ma[name]
        return total
