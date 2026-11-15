# 新場地重新訓練（拍照 → 標註 → 訓練 → 換模型）

兩個工具都在 **Mac** 上跑，用專案自己的 `venv`（裡面已經有 ultralytics，Apple
晶片用 `mps` 訓練）。它們不會動到 Orin，也不會覆蓋 `weights/best.pt`。

| 步驟 | 在哪裡做 | 大約時間 |
|---|---|---|
| 0. 拍照、拉回 Mac | 機器人 + Mac | 跑幾場練習賽 |
| 1. 去重複、自動框 | Mac：`prepare_capture.py` | 1–2 分鐘 |
| 2. 修正框 | Roboflow 網頁 | 30–60 分鐘 |
| 3. 合併、訓練、比較 | Mac：`train_merge.py` | 40 epochs 約 30 分鐘 |
| 4. 換模型 | Orin | 約 10 分鐘（含轉 TensorRT） |

以下指令都先進到專案資料夾：

```bash
cd ~/Desktop/RobotAI/YOLO_Detect_single
```

## 0. 拍照、拉回 Mac

練習時在 Dashboard 按 **P**（手把 View）開拍照，每秒一張。比賽流程照實跑；另外對著
**有場地圖案、沒有洞**的地方（場邊、看板、地板）多拍一些。拉回 Mac（`<OrinIP>`
在 Orin 上用 `hostname -I` 查）：

```bash
rsync -av jeremy@<OrinIP>:~/RobotAI/YOLO_Detect_single/dataset_capture/ ~/Desktop/RobotAI/YOLO_Detect_single/dataset_capture/
```

## 1. 去重複、自動框

```bash
venv/bin/python tools/dataset/prepare_capture.py
```

輸出在 `dataset_prepared/<時間>/`：

- `upload/`：有框到洞的照片＋框（YOLO 格式＋data.yaml），整個資料夾上傳 Roboflow。
- `no_holes/`：模型一個洞都沒框到的照片，**要一張一張看**：
  - 真的沒有洞 → 留著，就是「背景照」（教模型這些圖案不是洞）。
  - 有洞 → 模型漏抓。把它**移到** `upload/images/`，在 Roboflow 上手動補框。
- `report.txt`：張數統計。

常用選項：`--max 300`（最多留 300 張，平均挑）、`--dup-bits 10`（更積極去重複）、
`--src 別的資料夾`。

## 2. 在 Roboflow 修正

1. 打開原本的專案 **tel_2026_field_v3**，Upload → 拖進 `upload/` 整個資料夾（照片＋框會一起進來）。
2. 只做三件事：補漏掉的洞、刪錯框、框太歪的拉正。類別只能有 `hole` 一個。
3. Generate 一個新版本 → Export → 格式選 **YOLOv8** → 下載 zip，解壓縮到例如
   `~/Downloads/tel_field_1114/`。

（Roboflow 新版本裡的 train / valid / test 三個資料夾都會被拿來用，切分由下一步重新做。）

## 3. 合併、訓練、比較

```bash
venv/bin/python tools/dataset/train_merge.py --new ~/Downloads/tel_field_1114 --background dataset_prepared/<時間>/no_holes
```

- 舊的 300 張（`TEL_2026_Field_V3.v1i.yolov8/train`）全部進訓練，讓模型不會忘了舊場地。
- 新照片和背景照各抽 20% 當**檢查用**，兩個模型都沒看過，比較才公平。
- 從 `weights/best.pt` 接著訓練（不是從頭），顏色、亮度的變化加大，比較不依賴背景圖案。
- 最後印出新舊兩個模型的比較（用機器人一樣的門檻 conf 0.35）：

  | 欄位 | 意思 |
  |---|---|
  | 抓到 / 漏抓 | 標註的洞有沒有被框到（框和標註重疊 IoU ≥ 0.5） |
  | 誤抓 | 框在沒有洞的地方 |
  | 背景上誤抓 | 其中框在背景照上的 |

- 新模型在 `runs/finetune/<時間>/weights/best.pt`。

常用選項：`--epochs 60`、`--new` 和 `--background` 可以給很多次（例如今天＋正賽練習日）、
只重新比較不訓練：
`venv/bin/python tools/dataset/train_merge.py --check-only datasets_merged/<時間> --compare runs/finetune/<時間>/weights/best.pt`

**新模型漏抓和誤抓都沒有比較多，才換。**

## 4. 換到 Orin（保留舊的，隨時換回來）

Orin 跑的是 `weights/best.engine`（TensorRT，要在 Orin 上自己轉，Mac 轉的不能用）。

Mac 上，把新模型傳過去（改名成 best_new.pt）：

```bash
scp runs/finetune/<時間>/weights/best.pt jeremy@<OrinIP>:~/RobotAI/YOLO_Detect_single/weights/best_new.pt
```

Orin 上：

```bash
cd ~/RobotAI/YOLO_Detect_single
cp weights/best.pt weights/best_1114.pt && cp weights/best.engine weights/best_1114.engine
venv/bin/yolo export model=weights/best_new.pt format=engine half=True device=0 imgsz=640
```

先試新模型（不換檔案）：停掉服務，用新模型手動跑一次，在場上看洞抓得好不好：

```bash
sudo systemctl stop yolo-vision.service
venv/bin/python test_coordinate.py --source realsense --serial --serial-port /dev/ttyTHS1 --wait-for-mega --no-display --model weights/best_new.engine
```

確定要換（Ctrl+C 結束上面那個再做）：

```bash
cp weights/best_new.pt weights/best.pt && cp weights/best_new.engine weights/best.engine && sudo systemctl restart yolo-vision.service
```

換回舊的：

```bash
cp weights/best_1114.pt weights/best.pt && cp weights/best_1114.engine weights/best.engine && sudo systemctl restart yolo-vision.service
```

## 正賽

練習日用同樣流程再跑一輪：`--new` 同時給今天的和正賽的 Roboflow 匯出、`--background`
同時給兩次的 no_holes，`--base` 用今天訓練出來的模型。
