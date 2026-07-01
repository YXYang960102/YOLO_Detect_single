from config import SERIAL_BAUD


class VisionSerial:
    def __init__(self, port=None, baud=SERIAL_BAUD, enabled=False):
        self.port = port
        self.baud = baud
        self.enabled = enabled
        self.last_message = ""
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

        if message == self.last_message:
            return

        print(message)
        self.last_message = message

        if self.enabled and self.serial is not None:
            self.serial.write((message + "\n").encode("ascii"))
