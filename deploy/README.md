# Orin systemd supervisor

`yolo-vision.service.example` is the second recovery layer. The Python process
first performs its bounded RealSense reopen attempts. Only a fatal model/CUDA
error or exhausted camera recovery exits non-zero and reaches systemd, which
waits 2 seconds before starting a fresh process.

Before installing the example, verify and edit all deployment-specific values:

- `User=jeremy`
- both `/home/jeremy/RobotAI/YOLO_Detect_single` paths
- `/dev/ttyTHS1`, using the stable UART device verified on the Orin
- `--no-display`, which is appropriate for a headless competition service

Install and bench-test on the Orin only after those values are correct:

```bash
sudo cp deploy/yolo-vision.service.example /etc/systemd/system/yolo-vision.service
sudo systemctl daemon-reload
sudo systemctl start yolo-vision.service
systemctl status yolo-vision.service
journalctl -u yolo-vision.service -f
```

After the hardware tests pass, enable automatic startup:

```bash
sudo systemctl enable yolo-vision.service
```

To stop or remove automatic startup:

```bash
sudo systemctl stop yolo-vision.service
sudo systemctl disable yolo-vision.service
```

The initial restart limiter allows at most 5 starts in 60 seconds. Validate
that limit, the 2-second restart delay, UART permissions, RealSense USB access,
and shutdown behavior on the actual Orin before competition use. This repository
does not install or enable the service automatically.
