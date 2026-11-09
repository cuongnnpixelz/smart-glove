"""USB/COM entry point for the five-finger 100 Hz collector."""
import argparse
import sys

if __package__:
    from . import collect_sequence_5 as collector
    from .serial_transport import list_ports
else:
    import collect_sequence_5 as collector
    from serial_transport import list_ports


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    preliminary = argparse.ArgumentParser(add_help=False)
    preliminary.add_argument("--list-ports", action="store_true")
    preliminary.add_argument("--serial-port")
    options, _ = preliminary.parse_known_args(argv)
    if "--help" in argv or "-h" in argv:
        print("USB collector. --list-ports: list ports without opening them.")
        return collector.main(argv)
    if options.list_ports or not options.serial_port:
        try:
            ports = list_ports()
        except ImportError:
            print("Thieu pyserial. Cai bang: python -m pip install pyserial")
            return 1
        for port in ports:
            print(f"{port.device}: {port.description}")
        if not ports:
            print("Khong tim thay COM. Cam cap USB truyen du lieu va kiem tra Device Manager.")
            return 1
        if options.list_ports:
            return 0
        try:
            # Always ask when unspecified: a listed port may belong to another device.
            selected = input("Nhap cong ESP32 trong Arduino IDE (vi du COM5) | Q: dung > ").strip()
        except (KeyboardInterrupt, EOFError):
            return 0
        if selected.upper() == "Q":
            return 0
        match = next((p.device for p in ports if p.device.lower() == selected.lower()), None)
        if not match:
            print("Cong da nhap khong nam trong danh sach.")
            return 1
        argv += ["--serial-port", match]
    return collector.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
