"""USB serial adapter for the shared RAW5_100 stream reader."""
import socket
import threading
import time


BAUD = 230400


def list_ports():
    from serial.tools import list_ports as ports
    return sorted(ports.comports(), key=lambda p: p.device)


class SerialTransport:
    def __init__(self, port, baudrate=BAUD):
        import serial
        self._write_lock = threading.Lock()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread = None
        self._heartbeat_error = None
        # Opening an ESP32 USB bridge can reset the board. Wait for our specific
        # firmware handshake, not an arbitrary sleep or a bootloader message.
        self.port = serial.Serial(port, baudrate, timeout=.2, write_timeout=1)
        try:
            self._handshake()
            self._heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True,
                                                       name="glove-com-heartbeat")
            self._heartbeat_thread.start()
        except BaseException:
            self.port.close()
            raise

    def _heartbeat(self):
        # Keep USB ownership even while input() waits for the wearer. If Python
        # is killed, firmware returns to Wi-Fi after its 6-second lease expires.
        while not self._heartbeat_stop.wait(1):
            try:
                self.sendall(b"PING\n")
            except OSError as error:
                self._heartbeat_error = error
                return

    def _stop_heartbeat(self):
        self._heartbeat_stop.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(1.5)

    def _handshake(self):
        deadline = time.monotonic() + 8
        pending = b""
        while time.monotonic() < deadline:
            self.sendall(b"HELLO\n")
            pending += self.port.read(min(4096, self.port.in_waiting or 1))
            if len(pending) > 65536:
                raise ValueError("Du lieu khoi dong COM qua dai")
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if line.strip() == b"READY_COM5_100":
                    return
                if line.startswith(b"ERROR_COM5_"):
                    raise ValueError(line.decode("ascii", errors="replace"))
        raise ValueError("Khong thay firmware COM. Nap mophong_com/mophong_com.ino; dong Serial Monitor va thu lai")

    def settimeout(self, seconds):
        self.port.timeout = seconds

    def recv(self, size):
        if self._heartbeat_error:
            raise self._heartbeat_error
        # Do not wait for all 4096 bytes: promptly drain whatever is available.
        data = self.port.read(min(size, self.port.in_waiting or 1))
        if not data:
            raise socket.timeout("COM read timeout")
        return data

    def sendall(self, data):
        with self._write_lock:
            if self.port.write(data) != len(data):
                raise OSError("Khong gui du lenh qua COM")

    def shutdown(self, how):
        self._stop_heartbeat()
        self.sendall(b"IDLE\n")

    def close(self):
        self._stop_heartbeat()
        self.port.close()
