import time

from config import (
    CONTROLLER_PROTOCOL_VERSION,
    MEGA_HEARTBEAT_TIMEOUT_SECONDS,
    SERIAL_BAUD,
    SERIAL_HEARTBEAT_SECONDS,
    SERIAL_IDLE_POLL_SECONDS,
    SERIAL_RECONNECT_SECONDS,
)


class VisionSerial:
    def __init__(
        self,
        port=None,
        baud=SERIAL_BAUD,
        enabled=False,
        heartbeat_seconds=SERIAL_HEARTBEAT_SECONDS,
        reconnect_seconds=SERIAL_RECONNECT_SECONDS,
        idle_poll_seconds=SERIAL_IDLE_POLL_SECONDS,
        mega_timeout_seconds=MEGA_HEARTBEAT_TIMEOUT_SECONDS,
        protocol_version=CONTROLLER_PROTOCOL_VERSION,
        clock=time.monotonic,
        sleeper=time.sleep,
        serial_factory=None,
    ):
        self.port = port
        self.baud = baud
        self.enabled = enabled
        self.last_message = ""
        self.last_send_time = 0.0
        self.heartbeat_seconds = heartbeat_seconds
        self.reconnect_seconds = float(reconnect_seconds)
        self.idle_poll_seconds = float(idle_poll_seconds)
        self.mega_timeout_seconds = float(mega_timeout_seconds)
        self.protocol_version = int(protocol_version)
        self.clock = clock
        self.sleeper = sleeper
        self.serial_factory = serial_factory
        self.serial = None
        self.last_connect_attempt = float("-inf")
        self.last_mega_heartbeat = None
        self.last_status = ""
        self.last_status_send_time = 0.0
        self._rx_buffer = b""
        self._last_connect_error = None

        if self.enabled:
            self.ensure_connected(force=True)

    def ensure_connected(self, force=False):
        if not self.enabled:
            return False

        if self.serial is not None and getattr(self.serial, "is_open", True):
            return True

        now = self.clock()
        if not force and now - self.last_connect_attempt < self.reconnect_seconds:
            return False
        self.last_connect_attempt = now

        try:
            factory = self.serial_factory
            if factory is None:
                import serial

                factory = serial.Serial
            self.serial = factory(self.port, self.baud, timeout=0)
            self._rx_buffer = b""
            self._last_connect_error = None
            print(f"Serial connected: {self.port} @ {self.baud}")
            return True
        except Exception as exc:
            self.serial = None
            message = str(exc)
            if message != self._last_connect_error:
                print(f"Serial waiting for connection: {exc}")
                self._last_connect_error = message
            return False

    def _disconnect(self, exc=None):
        if exc is not None:
            print(f"Serial disconnected: {exc}")
        if self.serial is not None:
            try:
                self.serial.close()
            except Exception:
                pass
        self.serial = None
        self._rx_buffer = b""

    def _write_line(self, message):
        if not self.ensure_connected():
            return False
        try:
            self.serial.write((message + "\n").encode("ascii"))
            return True
        except Exception as exc:
            self._disconnect(exc)
            return False

    def _read_lines(self):
        if not self.ensure_connected():
            return []
        try:
            available = int(getattr(self.serial, "in_waiting", 0))
            if available <= 0:
                return []
            self._rx_buffer += self.serial.read(available)
        except Exception as exc:
            self._disconnect(exc)
            return []

        if len(self._rx_buffer) > 4096:
            self._rx_buffer = self._rx_buffer[-4096:]

        chunks = self._rx_buffer.split(b"\n")
        self._rx_buffer = chunks.pop()
        lines = []
        for chunk in chunks:
            try:
                line = chunk.rstrip(b"\r").decode("ascii").strip()
            except UnicodeDecodeError:
                continue
            if line:
                lines.append(line)
        return lines

    def poll_mega(self):
        for line in self._read_lines():
            fields = [field.strip() for field in line.split(",")]
            if len(fields) < 2:
                continue
            if fields[0] not in ("MEGA_READY", "MEGA_HEARTBEAT"):
                continue
            if fields[1] != str(self.protocol_version):
                continue
            self.last_mega_heartbeat = self.clock()
        return self.mega_alive_without_poll()

    def mega_alive_without_poll(self):
        if self.last_mega_heartbeat is None:
            return False
        return self.clock() - self.last_mega_heartbeat <= self.mega_timeout_seconds

    def mega_alive(self):
        self.poll_mega()
        return self.mega_alive_without_poll()

    def wait_for_mega(self):
        print("WAIT_MEGA: waiting for MEGA_READY / MEGA_HEARTBEAT")
        while not self.poll_mega():
            self.send_status("VISION_STANDBY")
            self.sleeper(self.idle_poll_seconds)
        print("MEGA_READY received")

    def forget_mega(self):
        self.last_mega_heartbeat = None

    def send_status(self, status, force=False):
        message = f"{str(status).strip().upper()},{self.protocol_version}"
        now = self.clock()
        changed = message != self.last_status
        heartbeat_due = now - self.last_status_send_time >= self.heartbeat_seconds
        if not force and not changed and not heartbeat_due:
            return False
        sent = self._write_line(message)
        if sent:
            self.last_status = message
            self.last_status_send_time = now
        return sent

    def send(self, tx, ty, distance, target_id, valid, force=False):
        message = f"{int(tx)},{int(ty)},{int(distance)},{int(target_id)},{int(valid)}"
        now = self.clock()
        changed = message != self.last_message
        heartbeat_due = now - self.last_send_time >= self.heartbeat_seconds

        if not force and not changed and not heartbeat_due:
            return False

        if changed:
            print(message)

        self.last_message = message
        self.last_send_time = now

        if self.enabled:
            return self._write_line(message)
        return False

    def close(self):
        self._disconnect()
