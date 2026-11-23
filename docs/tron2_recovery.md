# TRON2 Cube Lift 恢复评测

本页记录 2026-11-23 完成的真值位姿恢复和 RGB-D 视觉差分（VDM）对照，并给出 RGB-D 复跑命令。

[English](tron2_recovery.en.md) · [仿真环境与官方资产](tron2_bringup.md#setup)

## 目录

- [结果](#结果)
- [试验设置](#试验设置)
- [复跑 RGB-D 对照](#复跑-rgb-d-对照)

## 结果

| 物体位置与第二轮反馈 | 首轮物理成功 | 空抓后恢复成功 |
| --- | ---: | ---: |
| 真值位置 + 文本 | 0/20 | 20/20 |
| RGB-D + 文本 | 0/20 | 20/20 |
| RGB-D + 文本与 VDM | 0/20 | 20/20 |

RGB-D 两组均使方块中心升高 **11.94–12.00 cm**。全部种子的首轮代码、仿真状态与前后帧哈希逐一匹配。图像中红方块向画面上方移动约 **27–28 px**，20 条 SmolVLM 描述均漏掉了这次移动。物理成功要求保持夹持，方块中心升高至少 7 cm，并在 0.25 秒稳定窗口内保持速度不高于 0.04 m/s。 [任务判分](tron2_bringup.md#results)

## 试验设置

| 项目 | 设置 |
| --- | --- |
| 场景 | 官方 DACH_TRON2A 双指夹爪，桌面世界 Z 为 0.620 m |
| 扰动 | 首次接近后将方块沿世界 X 正向移动 0.075 m，空抓由仿真接触判定 |
| 配对 | 种子 1–20。第二轮从首轮结束的同一场景继续，RGB-D 对照仅改变是否追加 VDM 文本 |
| 代码模型 | Qwen2.5-Coder-3B-Instruct，BF16 贪心解码。 [权重版本](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct/tree/488639f1ff808d1d3d0ba301aef8c11461451ec5) |
| 视觉模型 | SmolVLM-500M-Instruct，输入头部相机的两张 RGB 快照。 [权重版本](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct/tree/753c1752602b5e739af7a7fa6947a635051897a3) |

## 复跑 RGB-D 对照

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
