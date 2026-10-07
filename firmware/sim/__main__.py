"""Phiên gõ tay: python3 -m sim  (chạy từ thư mục firmware)."""

from sim.session import Session


def main() -> None:
    session = Session()
    print("sim ready. gõ help, hw help, tick <ms>. quit để thoát.")
    while True:
        try:
            line = input("sim> ")
        except EOFError:
            print()
            break
        if line.strip() in ("quit", "exit"):
            break
        for reply in session.exec(line):
            print(reply)


if __name__ == "__main__":
    main()
