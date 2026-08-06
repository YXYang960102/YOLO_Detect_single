# Jetson Orin Nano 重刷前檢查清單

狀態：**PREPARE ONLY — 尚未授權重刷**  
建立日期：2026-07-23（Asia/Taipei）  
適用系統：TEL 2026 AI Vision（Jetson Orin Nano → Arduino Mega）

## 使用規則

- `[x]`：已有本機或 repository 證據。
- `[ ]`：必須在 Jetson、重刷主機或實體設備上確認。
- 任一標示 `STOP` 的項目未完成時，不得開始重刷。
- 本文件不授權格式化、分割磁碟、進入 flashing step、更新 QSPI、寫入 bootloader 或重刷 Jetson。
- 不要把密碼、token、SSH private key、Wi-Fi 密碼或 NVIDIA 登入資訊貼進本文件或 repository。

## 0. 重刷授權閘門

- [x] Jeremy 只授權準備重刷前清單，尚未授權執行重刷。
- [ ] **STOP：** Jeremy 已在執行當下明確確認下列四項：
  - Jetson 型號／SKU：`________________`
  - 目標 JetPack／Jetson Linux：`________________`
  - 要清除及寫入的儲存裝置：`________________`
  - 重刷方式與 host：`________________`
- [ ] **STOP：** 已再次確認機器人致動器、Arduino Mega 與高功率負載不會因 Jetson 重啟或 Serial 雜訊動作。

## 1. 已確認的本機恢復資產

- [x] `YOLO_Detect_single` working tree 乾淨。
- [x] Git commit：`d36d5ca42d44979e4be9a56fa5c7246d9b8cd11a`。
- [x] 本機存在 `weights/best.pt`，大小約 6.0 MiB。
- [x] `best.pt` SHA-256：

  ```text
  c150305bf8fef852f8fd4550d2c255f40e2d1505c38002fa08fb78d888313d53
  ```

- [x] Dataset 目錄有 605 個 Git tracked files。
- [ ] **STOP：** 已把 repository、`best.pt` 與需要的 dataset 複製到 Jetson 以外的第二個實體位置。
- [ ] 已在第二個位置重新計算 SHA-256，結果與上方一致。
- [ ] 已確認 private Git remote 可重新 clone，或另有完整 Git bundle／離線副本。
- [ ] 已記錄 Arduino Mega 對應 branch／commit：`________________`。

## 2. 確認硬體身分與目標磁碟

- [ ] **STOP：** 確認是 Jetson Orin Nano Developer Kit 或 production module＋自製 carrier。
- [ ] 記錄 module SKU（例如 P3767-0003／0004）：`________________`。
- [ ] 記錄 carrier board：`________________`。
- [ ] 記錄 RAM：`4 GB / 8 GB / 其他：________`。
- [ ] 記錄目前 boot medium：`microSD / NVMe / USB / 其他`。
- [ ] 記錄目標磁碟廠牌與容量：`________________`。
- [ ] **STOP：** 同時以 `lsblk`、容量與型號確認目標磁碟；不能只依賴 `/dev/nvme0n1` 名稱。
- [ ] 已確認是否需要保留 microSD、第二顆 NVMe 或其他資料碟。
- [ ] 已拍攝目前接線與 NVMe 安裝位置，作為回復參考。

在目前 Jetson 上只讀收集：

```bash
cat /proc/device-tree/model; echo
tr -d '\0' </proc/device-tree/compatible; echo
cat /etc/nv_tegra_release
cat /etc/os-release
uname -a
lsblk -o NAME,SIZE,MODEL,FSTYPE,MOUNTPOINTS
df -hT
sudo nvbootctrl dump-slots-info
sudo nvpmodel -q --verbose
```

把輸出保存到 Jetson 以外的位置；檢查後移除不必要的 hostname、IP 或裝置識別資訊。

## 3. 決定 JetPack／Jetson Linux 版本

目前建議候選：**JetPack 6.2.2／Jetson Linux 36.5**，因為它仍是 Ubuntu 22.04、CUDA 12.6、TensorRT 10.3、cuDNN 9.3，與先前記錄的專案環境最接近。這是暫定建議，不是已核准目標。

- [ ] **STOP：** AccuPick3D／深度相機供應商明確支援所選 JetPack、kernel、CUDA 與 Python 版本。
- [ ] **STOP：** Ultralytics、PyTorch、OpenCV 與相機 SDK 的安裝方式已在相同版本上確認。
- [ ] 已決定使用：
  - [ ] JetPack 6.2.2／Jetson Linux 36.5
  - [ ] 其他：`________________`，原因：`________________`
- [ ] 若考慮 JetPack 7.x，已確認相機 SDK、PyTorch wheel、CUDA 13 與現有部署流程全部相容。
- [ ] 已下載對應版本文件及 installer，並記錄下載來源與 checksum。

NVIDIA 官方基準：

- [JetPack 6.2.2](https://developer.nvidia.com/embedded/jetpack-sdk-622)
- [Jetson Linux 36.5](https://developer.nvidia.com/embedded/jetson-linux-r365)
- [JetPack downloads](https://developer.nvidia.com/embedded/jetpack/downloads)
- [Jetson software archive](https://docs.nvidia.com/jetson/archives/)

## 4. 保存目前軟體基準

- [ ] 保存 JetPack／L4T package 版本。
- [ ] 保存 CUDA、cuDNN、TensorRT、OpenCV、PyTorch、Ultralytics、NumPy、pyserial 版本。
- [ ] 保存 Python virtual environments 與安裝方式；不要只保存 `pip freeze` 而沒有 Python／JetPack 版本。
- [ ] 保存 Docker image 名稱、digest、compose files、volume 資料與啟動命令（若有）。
- [ ] 保存自訂 systemd services、udev rules、cron jobs、環境檔與啟動順序。
- [ ] 保存相機 SDK 安裝包版本、license／安裝說明及必要 kernel modules。
- [ ] 保存 camera intrinsics、extrinsics、depth alignment 與現場校正檔。
- [ ] 保存 Serial device 名稱、baud、udev 規則及使用者群組設定。
- [ ] 保存目前 power mode、風扇策略與任何自訂 device-tree／pinmux。

建議的唯讀版本盤點命令：

```bash
dpkg-query -W 'nvidia-l4t-*' 'nvidia-jetpack*' 2>/dev/null
nvcc --version
python3 --version
python3 -m pip freeze
python3 - <<'PY'
mods = ['torch', 'cv2', 'ultralytics', 'numpy', 'serial']
for name in mods:
    try:
        module = __import__(name)
        print(name, getattr(module, '__version__', getattr(module, 'VERSION', 'unknown')))
    except Exception as exc:
        print(name, 'ERROR', exc)
PY
systemctl list-unit-files --state=enabled
find /etc/udev/rules.d -maxdepth 1 -type f -print
getent group dialout
```

## 5. 備份內容與驗證

- [ ] **STOP：** Source、model、dataset／sample recordings、calibration 和 deployment config 都有外部備份。
- [ ] **STOP：** 備份不是放在即將被清除的 NVMe、microSD 或 Jetson 內部。
- [ ] 備份包含 `weights/best.pt`，不是只有被 `.gitignore` 排除模型的 Git clone。
- [ ] 備份包含未進 Git 的相機設定、錄影、systemd、udev 與部署腳本。
- [ ] 備份包含重建環境的版本 manifest。
- [ ] 使用 SHA-256 驗證重要模型、校正檔和安裝包。
- [ ] 隨機開啟至少一個錄影、校正檔和設定檔，確認備份可讀。
- [ ] 在另一台機器或乾淨目錄成功載入 `best.pt`。
- [ ] 密碼、token、SSH private key 與 Wi-Fi 密碼只存在 Jeremy 管理的加密備份，不放進專案備份或清單。
- [ ] 若需要完整磁碟映像，已安排離線 imaging；不要對正在掛載的 root NVMe 直接做未驗證的 block copy。

## 6. 重刷 host 準備

目前 Codex 所在主機是 macOS 26.5.2 arm64，**不作為原生 NVIDIA SDK Manager direct-flash host**。

- [ ] **STOP：** 已準備原生 Ubuntu x86_64 host；JetPack 6.x 優先使用 Ubuntu 22.04。
- [ ] 已確認 SDK Manager compatibility matrix 支援選定 JetPack 與 host OS。
- [ ] Host 至少符合 NVIDIA 的 8 GB RAM、27 GB host free space；實務上保留 60 GB 以上。
- [ ] Target 至少有 NVIDIA 要求的 16 GB 可用空間；實際依 SDK、模型和 recordings 保留更多。
- [ ] Host 使用穩定網路與 AC 電源，不會休眠。
- [ ] 準備已驗證可傳輸資料的 USB-C cable，不是充電限定線。
- [ ] Host 只有一台待刷 Jetson 進入 Recovery Mode，避免選錯目標。
- [ ] 已準備 DisplayPort monitor、鍵盤、滑鼠與 Jetson 原廠／合規 19V 電源。
- [ ] 已確認外接 Ubuntu 環境不會把 Windows／macOS 內部磁碟或 EFI partition 當成目標。

官方要求與流程：

- [SDK Manager system requirements](https://docs.nvidia.com/sdk-manager/system-requirements/index.html)
- [SDK Manager direct flash](https://docs.nvidia.com/sdk-manager/install-with-sdkm-jetson-direct-flash/index.html)
- [Orin Nano software setup](https://developer.nvidia.com/embedded/learn/jetson-orin-nano-devkit-user-guide/software_setup.html)

## 7. Force Recovery dry-run 準備

本節只準備，不在目前授權下執行 power cycle 或進入 Recovery Mode。

- [ ] 找到 carrier board 正確的 `FC REC` 與 `GND`，不得依其他 Jetson 型號 pinout 猜測。
- [ ] 已準備 USB-C data cable 連接 Jetson recovery port 與 Ubuntu host。
- [ ] 已寫下正確的進入及退出 Recovery Mode 步驟。
- [ ] 在未啟動 flash 的情況下，host 能以 `lsusb` 看見 NVIDIA APX／`0955:*` 裝置。
- [ ] SDK Manager 正確識別 Jetson Orin Nano 型號。
- [ ] **STOP：** SDK Manager flash dialog 中的 target storage 與第 2 節確認的實體磁碟完全一致。

## 8. 重刷設定草案（尚未執行）

- Product：`Jetson`
- Target hardware：`________________`
- JetPack：`________________`
- Install method：`Direct Flash / 其他：________`
- Storage：`NVMe / microSD / USB / 其他：________`
- Storage model／capacity：`________________`
- OEM config：`Runtime / Pre-Config`
- Jetson SDK Components：`Full / Runtime only / 自訂：________`
- Download directory：`________________`
- Host free space：`________________`
- Rollback artifact：`________________`

- [ ] 截圖或抄錄 SDK Manager 最終 summary。
- [ ] 由第二人或 Jeremy 再核對 target hardware、JetPack 與 storage。
- [ ] **STOP：** 停在開始寫入前；取得執行當下的明確重刷授權。

## 9. 重刷後驗收計畫

重刷完成不代表系統完成；應依風險由低到高驗收：

- [ ] 首次開機、時間、locale、hostname 與網路正常。
- [ ] `cat /etc/nv_tegra_release`、JetPack、kernel 與 Ubuntu 版本符合記錄。
- [ ] NVMe 容量、partition、mount 與 boot device 正確。
- [ ] CUDA sample／PyTorch CUDA availability 通過。
- [ ] TensorRT、cuDNN、OpenCV／GStreamer 可用。
- [ ] 安裝鎖定版本的 Python dependencies。
- [ ] `best.pt` SHA-256 正確且可載入。
- [ ] 先用錄影或靜態影像跑 YOLO，不接致動器。
- [ ] 深度相機 RGB stream 通過。
- [ ] Depth stream、alignment、invalid depth 與距離單位通過。
- [ ] 用 mock serial receiver 驗證 `tx,ty,distance,target_id,valid` heartbeat。
- [ ] 模擬程式 crash、Serial 拔除與 stale packet，確認 Mega 在 300 ms 內失效。
- [ ] Jetson-to-Mega bench test 時致動器輸出維持 disabled／neutral。
- [ ] 最後才進行受限水平瞄準測試；射擊與底盤動作另行授權。
- [ ] 記錄 FPS、P50/P95 latency、RAM、溫度、power mode 和 match-length thermal soak。

## 10. 回復與停止條件

遇到以下任一情況立即停止，不嘗試「多按一次」或改猜另一顆磁碟：

- Target hardware／SKU 與預期不符。
- SDK Manager 顯示的 storage、容量或型號不符。
- Backup checksum 不符或外部副本無法讀取。
- AccuPick3D SDK 不支援所選 JetPack／kernel。
- Recovery USB 反覆斷線、出現 `timeout in USB write` 或電源不穩。
- Host 對內部系統碟、EFI 或非 Jetson 磁碟提出格式化要求。
- Jetson、Mega 或機構仍連接在可能造成動作的供電狀態。

回復點：

- Git commit：`d36d5ca42d44979e4be9a56fa5c7246d9b8cd11a`
- Model SHA-256：`c150305bf8fef852f8fd4550d2c255f40e2d1505c38002fa08fb78d888313d53`
- 舊 JetPack／L4T：`待第 4 節收集`
- 外部備份位置：`________________`
- 完整磁碟映像／替代 boot media：`________________`

## 最終 Go／No-Go

- [ ] 所有 `STOP` 項目已完成。
- [ ] 備份已從第二個位置驗證。
- [ ] 版本與相機 SDK 相容性已有證據。
- [ ] Flash target 與 storage 已由兩次獨立檢查確認。
- [ ] 重刷後驗收與 rollback 已有人員、時間和設備。
- [ ] Jeremy 已給出執行當下的明確授權。

只有以上全部勾選後，狀態才可從 `PREPARE ONLY` 改為 `READY TO FLASH`。
