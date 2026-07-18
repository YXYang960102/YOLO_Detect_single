import time

from config import SERIAL_BAUD, SERIAL_HEARTBEAT_SECONDS


class VisionSerial:
    def __init__(
        self,
        port=None,
        baud=SERIAL_BAUD,
        enabled=False,
        heartbeat_seconds=SERIAL_HEARTBEAT_SECONDS,
        clock=time.monotonic,
    ):
        self.port = port
        self.baud = baud
        self.enabled = enabled
        self.last_message = ""
        self.last_send_time = 0.0
        self.heartbeat_seconds = heartbeat_seconds
        self.clock = clock
        self.serial = None

        if self.enabled:
            try:
                import serial

                self.serial = serial.Serial(self.port, self.baud, timeout=0)
            except Exception as exc:
                print(f"Serial disabled: {exc}")
                self.enabled = False

    def send(self, tx, ty, distance, target_id, valid):
        message = f"{int(tx)},{int(ty)},{int(distance)},{int(target_id)},{int(valid)}"
        now = self.clock()
        changed = message != self.last_message
        heartbeat_due = now - self.last_send_time >= self.heartbeat_seconds

        if not changed and not heartbeat_due:
            return

        if changed:
            print(message)

        self.last_message = message
        self.last_send_time = now

        if self.enabled and self.serial is not None:
            self.serial.write((message + "\n").encode("ascii"))
