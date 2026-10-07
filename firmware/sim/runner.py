"""Chạy file kịch bản trên giả lập hoặc trên cổng serial."""

from __future__ import annotations

import sys
from pathlib import Path

from sim.session import SerialSession, Session

ROOT = Path(__file__).resolve().parent
SCENARIOS = ROOT / "scenarios"


def run_lines(session: Session | SerialSession, lines: list[str]) -> list[str]:
    failures: list[str] = []
    produced: list[str] = []
    for index, raw in enumerate(lines, start=1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("expect "):
            needle = text[len("expect ") :]
            if not any(needle in line for line in produced):
                failures.append(f"{index}: thiếu '{needle}' trong {produced}")
            continue
        produced = session.exec(text)
    return failures


def run_file(session: Session | SerialSession, path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    failures = run_lines(session, lines)
    return [f"{path.name}: {item}" for item in failures]


def main(argv: list[str]) -> int:
    args = list(argv)
    port = None
    if args and args[0] == "--port":
        if len(args) < 2:
            print("err syntax", file=sys.stderr)
            return 2
        port = args[1]
        args = args[2:]
    if port:
        session: Session | SerialSession = SerialSession(port)
    else:
        session = Session()
    if not args:
        paths = sorted(SCENARIOS.rglob("*.txt"))
    else:
        paths = [Path(item) for item in args]
    failures: list[str] = []
    for path in paths:
        if not port:
            session = Session()
        failures.extend(run_file(session, path))
    if failures:
        print("\n".join(failures))
        return 1
    print(f"ok files={len(paths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
