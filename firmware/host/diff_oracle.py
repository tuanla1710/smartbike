"""Đối chiếu bike_host với oracle Python. Chạy từ thư mục firmware."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sim.session import Session

HOST = ROOT / "host" / "bike_host"
SCENARIOS = ROOT / "sim" / "scenarios"


class Host:
    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [str(HOST)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def exec(self, line: str) -> list[str]:
        assert self.proc.stdin is not None and self.proc.stdout is not None
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        found: list[str] = []
        while True:
            raw = self.proc.stdout.readline()
            if raw == "":
                raise RuntimeError("bike_host đóng stdout")
            text = raw.rstrip("\n")
            if text == ".":
                return found
            found.append(text)

    def close(self) -> None:
        if self.proc.stdin is not None:
            self.proc.stdin.close()
        self.proc.wait(timeout=2)


def compare(script: list[str]) -> list[str]:
    py = Session()
    host = Host()
    failures: list[str] = []
    try:
        for line in script:
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            want = py.exec(text)
            got = host.exec(text)
            if got != want:
                failures.append(f"{text}\n  python={want}\n  c={got}")
    finally:
        host.close()
    return failures


def main() -> int:
    failures: list[str] = []
    paths = sorted(SCENARIOS.rglob("*.txt"))
    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        # expect dòng không phải lệnh. Bỏ chúng khi so từng lệnh, rồi kiểm tra needle.
        commands = []
        expects: list[tuple[int, str]] = []
        produced_at: list[list[str]] = []
        for raw in lines:
            text = raw.strip()
            if not text or text.startswith("#"):
                continue
            if text.startswith("expect "):
                expects.append((len(commands) - 1, text[len("expect ") :]))
            else:
                commands.append(text)
        py = Session()
        host = Host()
        try:
            for command in commands:
                want = py.exec(command)
                got = host.exec(command)
                produced_at.append(got)
                if got != want:
                    failures.append(f"{path.name}: {command}\n  python={want}\n  c={got}")
        finally:
            host.close()
        for index, needle in expects:
            if index < 0 or not any(needle in line for line in produced_at[index]):
                failures.append(f"{path.name}: thiếu '{needle}'")

    scripts = {
        "tail": "arm\ntick 10\ngates\nride start\ntick 10\ngates\nstatus\n",
        "riding-motion": "debug on\nconfig set alarm_motion_ms 50\nride start\ntick 10\ninject motion on\ntick 200\nstatus\n",
        "lidar": "debug on\narm\ntick 10\ninject range 3999\ntick 10\nsnapshot\ngates\ninject range 4000\ntick 10\nsnapshot\n",
        "oc": "debug on\nconfig set oc_ma 100\nhw load head 300\narm\ntick 10\nhold head on\ntick 120\nstatus\ngates\nhold head on\ntick 10\ngates\narm\ntick 10\ngates\n",
        "uvlo": None,
        "sleep-abort": "debug on\nsleep\ntick 10\narm\ntick 10\ntick 10\n",
        "deepsleep": "arm\ntick 10\ndebug on\nsleep\ntick 10\ntick 10\nstatus\nhw wake\ntick 10\nhw reset power\nstatus\n",
        "gps": "hw gps 10.5 106.7\ntick 10\nsense\nhw gps 0 0\ntick 10\nsense\nsnapshot\n",
        "stall": "arm\ntick 10\ndebug on\nhold head on\ntick 10\ngates\nhw stall on\ntick 50\ngates\nfaults\n",
        "inject-v": "debug on\ninject lux 10\ntick 10\nstatus\n",
        "oc-range": "debug on\nconfig set oc_ma 3000\nconfig\n",
        "hold-debug": "hold head on\n",
        "snapshot": "snapshot\n",
    }
    for name, script in scripts.items():
        if script is None:
            continue
        bad = compare(script.splitlines())
        for item in bad:
            failures.append(f"{name}: {item}")

    uvlo_lines = ["debug on", "arm", "tick 10"]
    for _ in range(3):
        uvlo_lines += ["hw power 4000", "tick 80", "status", "hw power 4700", "tick 250"]
    uvlo_lines += ["status", "hw power 4700", "tick 300", "status"]
    for item in compare(uvlo_lines):
        failures.append(f"uvlo: {item}")

    if failures:
        print("\n".join(failures))
        return 1
    print(f"ok files={len(paths)} cases={len(scripts) + 1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
