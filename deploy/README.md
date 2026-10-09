# Orin systemd supervisor

`yolo-vision.service.example` is the second recovery layer. The Python process
first performs its bounded RealSense reopen attempts. Only a fatal model/CUDA
error or exhausted camera recovery exits non-zero and reaches systemd, which
waits 2 seconds before starting a fresh process.

`jetson-maxperf.service.example` is a separate one-shot service that sets the
power mode and locks max clocks at boot (2026-10-09: discovered the hard way
that this Orin defaults to 25W on every boot per `nvpmodel -p --verbose`'s
`PM_CONFIG: DEFAULT=...` line, and `jetson_clocks` never persists across a
reboot -- without this service, `yolo-vision.service` silently starts at a
fraction of the performance measured during a manual, already-tuned session).
`yolo-vision.service.example` declares `Requires=`/`After=` on it, so starting
or enabling the vision service pulls this one in too.

Before installing either example, verify and edit all deployment-specific values:

- `User=jeremy`
- both `/home/jeremy/RobotAI/YOLO_Detect_single` paths
- `/dev/ttyTHS1`, using the stable UART device verified on the Orin
- `--no-display`, which is appropriate for a headless competition service
- `--model weights/best.engine`, which requires that file to already exist
  (`yolo export model=weights/best.pt format=engine half=True device=0
  imgsz=640`, run once on this Orin -- the resulting `.engine` is tied to
  this GPU/TensorRT/JetPack version and is not portable; re-export after a
  reflash or JetPack upgrade, or the service will fail to start on a missing
  file)
- in `jetson-maxperf.service.example`: `nvpmodel -m 2` assumes `MAXN_SUPER` is
  index 2 on this device -- **re-verify with `nvpmodel -p --verbose` before
  installing**, this index is device/firmware-specific, not a universal
  constant, and can change after a JetPack upgrade
- in `jetson-maxperf.service.example`: the absolute paths
  `/usr/sbin/nvpmodel` and `/usr/bin/jetson_clocks` are the standard JetPack
  install locations -- confirm with `which nvpmodel` / `which jetson_clocks`
  and edit if different (systemd's `ExecStart=` requires an absolute path,
  it does not search `$PATH` the way an interactive shell does)

Install and bench-test on the Orin only after those values are correct:

```bash
sudo cp deploy/jetson-maxperf.service.example /etc/systemd/system/jetson-maxperf.service
sudo cp deploy/yolo-vision.service.example /etc/systemd/system/yolo-vision.service
sudo systemctl daemon-reload
sudo systemctl start yolo-vision.service
systemctl status jetson-maxperf.service
systemctl status yolo-vision.service
nvpmodel -q
journalctl -u yolo-vision.service -f
```

Confirm `nvpmodel -q` reports `MAXN_SUPER` and the `timing:` lines in the
journal show `yolo=` close to the TensorRT-engine figure measured during
manual testing (not 2-3x higher, which would mean the power-mode service
didn't actually run first).

After the hardware tests pass, enable automatic startup:

```bash
sudo systemctl enable jetson-maxperf.service
sudo systemctl enable yolo-vision.service
```

To stop or remove automatic startup:

```bash
sudo systemctl stop yolo-vision.service
sudo systemctl disable yolo-vision.service
sudo systemctl disable jetson-maxperf.service
```

The initial restart limiter allows at most 5 starts in 60 seconds. Validate
that limit, the 2-second restart delay, UART permissions, RealSense USB access,
and shutdown behavior on the actual Orin before competition use. Also validate
a real reboot at least once -- confirm both services come up automatically in
the right order and the vision loop actually reaches the tuned FPS, since
everything above can only be exercised by manually re-running commands, not by
simulating a cold boot. This repository does not install or enable the
service automatically.
