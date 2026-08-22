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
        self.incoming = b""
        self.is_open = True

    @property
    def in_waiting(self):
        return len(self.incoming)

    def write(self, message):
        self.messages.append(message)

    def read(self, size):
        data = self.incoming[:size]
        self.incoming = self.incoming[size:]
        return data

    def feed(self, message):
        self.incoming += message

    def close(self):
        self.is_open = False


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

    def test_force_sends_neutral_packet_immediately(self):
        clock = FakeClock()
        sender = VisionSerial(enabled=False, heartbeat_seconds=1.0, clock=clock)
        sender.enabled = True
        sender.serial = FakeSerial()

        sender.send(0, 0, 0, 0, 0)
        sender.send(0, 0, 0, 0, 0, force=True)

        self.assertEqual(
            sender.serial.messages,
            [b"0,0,0,0,0\n", b"0,0,0,0,0\n"],
        )

    def test_versioned_mega_ready_starts_and_then_times_out(self):
        clock = FakeClock()
        fake_serial = FakeSerial()
        sender = VisionSerial(enabled=False, mega_timeout_seconds=1.0, clock=clock)
        sender.enabled = True
        sender.serial = fake_serial

        fake_serial.feed(b"noise\nMEGA_READY,1\n")
        self.assertTrue(sender.mega_alive())

        clock.now = 0.99
        self.assertTrue(sender.mega_alive())
        clock.now = 1.01
        self.assertFalse(sender.mega_alive())

    def test_heartbeat_accepts_extra_fields_and_rejects_wrong_version(self):
        clock = FakeClock()
        fake_serial = FakeSerial()
        sender = VisionSerial(enabled=False, protocol_version=1, clock=clock)
        sender.enabled = True
        sender.serial = fake_serial

        fake_serial.feed(b"MEGA_READY,2\n")
        self.assertFalse(sender.poll_mega())

        fake_serial.feed(b"MEGA_HEARTBEAT,1,boot-7,42\n")
        self.assertTrue(sender.poll_mega())

    def test_partial_uart_line_is_buffered_until_newline(self):
        clock = FakeClock()
        fake_serial = FakeSerial()
        sender = VisionSerial(enabled=False, clock=clock)
        sender.enabled = True
        sender.serial = fake_serial

        fake_serial.feed(b"MEGA_RE")
        self.assertFalse(sender.poll_mega())
        fake_serial.feed(b"ADY,1\r\n")
        self.assertTrue(sender.poll_mega())

    def test_status_and_numeric_packets_share_one_uart(self):
        clock = FakeClock()
        fake_serial = FakeSerial()
        sender = VisionSerial(enabled=False, heartbeat_seconds=0.1, clock=clock)
        sender.enabled = True
        sender.serial = fake_serial

        sender.send_status("VISION_STARTING", force=True)
        sender.send_status("VISION_READY", force=True)
        sender.send(-12, 8, 2450, 7, 1)

        self.assertEqual(
            fake_serial.messages,
            [
                b"VISION_STARTING,1\n",
                b"VISION_READY,1\n",
                b"-12,8,2450,7,1\n",
            ],
        )

    def test_wait_loop_stays_lightweight_until_mega_heartbeat(self):
        clock = FakeClock()
        fake_serial = FakeSerial()
        sleep_calls = []

        def sleeper(seconds):
            sleep_calls.append(seconds)
            clock.now += seconds
            if len(sleep_calls) == 2:
                fake_serial.feed(b"MEGA_HEARTBEAT,1\n")

        sender = VisionSerial(
            enabled=False,
            heartbeat_seconds=0.01,
            idle_poll_seconds=0.02,
            clock=clock,
            sleeper=sleeper,
        )
        sender.enabled = True
        sender.serial = fake_serial

        sender.wait_for_mega()

        self.assertEqual(sleep_calls, [0.02, 0.02])
        self.assertTrue(sender.mega_alive_without_poll())
        self.assertEqual(
            fake_serial.messages,
            [b"VISION_STANDBY,1\n", b"VISION_STANDBY,1\n"],
        )

    def test_connection_failure_is_retried_instead_of_disabling_serial(self):
        clock = FakeClock()
        fake_serial = FakeSerial()
        attempts = []

        def factory(port, baud, timeout):
            attempts.append((port, baud, timeout))
            if len(attempts) == 1:
                raise OSError("not ready")
            return fake_serial

        sender = VisionSerial(
            port="test-uart",
            enabled=True,
            reconnect_seconds=0.5,
            clock=clock,
            serial_factory=factory,
        )
        self.assertTrue(sender.enabled)
        self.assertIsNone(sender.serial)

        clock.now = 0.49
        self.assertFalse(sender.ensure_connected())
        clock.now = 0.50
        self.assertTrue(sender.ensure_connected())
        self.assertIs(sender.serial, fake_serial)


if __name__ == "__main__":
    unittest.main()
