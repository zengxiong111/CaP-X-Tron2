# TRON2 Cube Lift 恢复评测

本页记录 2026-11-23 完成的 TRON2 Cube Lift 恢复试验，涵盖真值位姿、RGB-D 配对恢复和红色方块移动识别。

本页使用官方 MJCF 的原始基座布局。桌面世界 Z 为 0.620 m，`base_Link` 世界 Z 为 1.210 m。 [0.450 m 安装高差下的后续遮挡评测](tron2_calibrated_occlusion.md)

[English](tron2_recovery.en.md) · [仿真环境与官方资产](tron2_bringup.md#setup)

## 目录

- [结果](#结果)
  - [固定 +X 偏移](#固定-x-偏移)
  - [红色方块移动识别](#红色方块移动识别)
  - [双方向配对恢复](#双方向配对恢复)
- [试验设置](#试验设置)
- [复跑 RGB-D 对照](#复跑-rgb-d-对照)
  - [固定方向与 SmolVLM](#固定方向与-smolvlm)
  - [两个方向与目标跟踪](#两个方向与目标跟踪)

## 结果

### 固定 +X 偏移

| 物体位置与第二轮反馈 | 首轮物理成功 | 空抓后恢复成功 |
| --- | ---: | ---: |
| 真值位置 + 文本 | 0/20 | 20/20 |
| RGB-D + 文本 | 0/20 | 20/20 |
| RGB-D + 文本与 VDM | 0/20 | 20/20 |

RGB-D 两组均使方块中心升高 **11.94–12.00 cm**。全部种子的首轮代码、仿真状态与前后帧哈希逐一匹配。图像中红方块向画面上方移动约 **27–28 px**，20 条 SmolVLM 描述均漏掉了这次移动。物理成功要求保持夹持，方块中心升高至少 7 cm，并在 0.25 秒稳定窗口内保持速度不高于 0.04 m/s。 [任务判分](tron2_bringup.md#results)

### 红色方块移动识别

目标跟踪版 VDM 对两张 RGB 图分别提取饱和红色像素，通过截尾质心估计位移，移动阈值为 3 px。

| 保存的图像与衍生对照 | 预期分类 | 目标跟踪 |
| --- | --- | ---: |
| 20 对原始图像 | 向上 | 20/20 |
| 20 对倒序图像 | 向下 | 20/20 |
| 20 对重复同一张图像 | 未移动 | 20/20 |
| 20 对缺少红色目标的对照 | 无法判断 | 20/20 |

SmolVLM 在原始、倒序和重复图像的提示词试验中，60 次均回答 `LEFT`，分类正确数为 **0/60**。

### 双方向配对恢复

Qwen 使用种子 21–40。+X 与 −Y 各 10 个种子，每次平移 75 mm。两组逐种子匹配首轮程序、仿真状态和前后 RGB 图像哈希。

| 指标 | 文本反馈 | 文本 + 目标跟踪 VDM |
| --- | ---: | ---: |
| 首轮空抓 | 20/20 | 20/20 |
| 空抓后恢复成功 | 20/20 | 20/20 |
| 图像移动方向正确 | — | 20/20 |

头部相机下，+X 对应图像向上，−Y 对应图像向右，各判对 10/10。移动方向使用仿真方块中心的离线投影评分，代码模型仅收到视觉估计描述。20 对恢复结果完全一致。四方向预检在 75 mm 和 55 mm 处均出现 IK 或跟踪失败，本轮选取通过 Oracle 预检的两个方向。缺少红色目标的对照属于离线识别试验，配对恢复未覆盖部分遮挡。

## 试验设置

| 项目 | 设置 |
| --- | --- |
| 场景 | 官方 DACH_TRON2A 双指夹爪，桌面世界 Z 为 0.620 m |
| 扰动 | 首次接近后将方块在世界 XY 平面移动 0.075 m，空抓由仿真接触判定 |
| 配对 | 固定方向使用种子 1–20，双方向使用种子 21–40。第二轮从首轮结束状态继续，RGB-D 对照仅改变是否追加 VDM 文本 |
| 代码模型 | Qwen2.5-Coder-3B-Instruct，BF16 贪心解码。 [权重版本](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct/tree/488639f1ff808d1d3d0ba301aef8c11461451ec5) |
| 视觉模型 | SmolVLM-500M-Instruct，输入头部相机的两张 RGB 快照。 [权重版本](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct/tree/753c1752602b5e739af7a7fa6947a635051897a3) |

## 复跑 RGB-D 对照

### 固定方向与 SmolVLM

下方命令覆盖两个 RGB-D 组，表中的真值组记录同扰动下的先前基线。完成[仿真环境设置](tron2_bringup.md#setup)，并从仓库根目录运行。准备两个 OpenAI 兼容 Chat Completions 端点，将完整 URL 分别设置为 `CAPX_MODEL_URL`、`CAPX_VDM_URL`，将端点接受的模型 ID 设置为 `CAPX_MODEL_NAME`、`CAPX_VDM_NAME`。单种子冒烟可在两条命令中加 `--trials 1`，默认各运行 20 次。每次使用新的输出路径。

```bash
export MUJOCO_GL=egl
config=env_configs/tron2/cube_lift_s1_guided_multi.yaml
python -m capx.envs.evaluate_tron2_recovery \
  --config "$config" --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" \
  --output outputs/tron2_recovery/text.json
python -m capx.envs.evaluate_tron2_recovery \
  --config "$config" --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" \
  --baseline outputs/tron2_recovery/text.json \
  --vdm-server-url "$CAPX_VDM_URL" --vdm-model "$CAPX_VDM_NAME" \
  --output outputs/tron2_recovery/vdm.json
```

配置提供共用的动作提示，恢复入口使用 **S2 RGB-D** 获取物体位置。第二条命令复用首轮代码，逐种子核对恢复前的仿真状态和图像。输出 JSON 的 `summary` 记录物理成功数，`seed_results` 记录动作、模型响应和 VDM 描述。

### 两个方向与目标跟踪

沿用同一仿真环境和代码模型端点。本地目标跟踪只读取两张 RGB 图像。两条命令运行种子 21–40，奇数种子沿 +X 偏移，偶数种子沿 −Y 偏移。

1. 运行文本反馈组，生成配对基线。

   ```bash
   export MUJOCO_GL=egl
   config=env_configs/tron2/cube_lift_s1_guided_multi.yaml
   python -m capx.envs.evaluate_tron2_recovery \
     --config "$config" --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" \
     --start-seed 21 --offset-directions '+X,-Y' \
     --output outputs/tron2_target_motion/text.json
   ```

2. 在同一个 shell 中运行目标跟踪组。输出包含逐种子的像素位移与离线方向核对，以及汇总字段 `correct_visual_directions`。

   ```bash
   python -m capx.envs.evaluate_tron2_recovery \
     --config "$config" --server-url "$CAPX_MODEL_URL" --model "$CAPX_MODEL_NAME" \
     --start-seed 21 --offset-directions '+X,-Y' \
     --baseline outputs/tron2_target_motion/text.json --target-motion \
     --output outputs/tron2_target_motion/vdm.json
   ```
