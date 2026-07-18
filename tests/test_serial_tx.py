import unittest

from serial_tx import VisionSerial


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeSerial:
    def __init__(self):
        self.messages = []

    def write(self, message):
        self.messages.append(message)


class VisionSerialTest(unittest.TestCase):
    def test_unchanged_packet_is_repeated_as_heartbeat(self):
        clock = FakeClock()
        sender = VisionSerial(enabled=False, heartbeat_seconds=0.1, clock=clock)
        sender.enabled = True
        sender.serial = FakeSerial()

        sender.send(1, 2, 3, 4, 1)
        clock.now = 0.05
        sender.send(1, 2, 3, 4, 1)
        clock.now = 0.11
        sender.send(1, 2, 3, 4, 1)

        self.assertEqual(
            sender.serial.messages,
            [b"1,2,3,4,1\n", b"1,2,3,4,1\n"],
        )


if __name__ == "__main__":
    unittest.main()
