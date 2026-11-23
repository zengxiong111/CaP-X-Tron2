# TRON2 Cube Lift 固定安装高差遮挡评测

在桌面世界 Z 为 0.620 m、仿真 `base_Link` 与桌面高差为 0.450 m 的条件下，比较文本恢复与文本 + 目标跟踪 VDM。结果记录于 2026-11-23。

这里的结果使用旧的覆盖式安装场景。要复跑这些历史数字，请在独立工作树使用提交 `62c243a`。当前版本同一评估入口使用下沉安装位和新的右夹爪朝向。 [当前配对基准](tron2_benchmark.md)

[English](tron2_calibrated_occlusion.en.md) · [仿真环境与官方资产](tron2_bringup.md#setup)

## 目录

- [配置与边界](#配置与边界)
- [评测结果](#评测结果)
- [复跑步骤](#复跑步骤)

## 配置与边界

| 项目 | 设置 |
| --- | --- |
| 场景 | 官方 DACH_TRON2A 双指夹爪。实验入口在临时 MJCF 中将 `base_Link` 世界 Z 从 1.210 m 移到 1.070 m。桌面仍为 0.620 m。 [官方资产版本](https://github.com/limxdynamics/tron2-robot-description/tree/9939c22e69d27653ec0ba8a505859a2903dd1a71) |
| 轨迹与感知 | 重新求解右臂归位分支，TCP 目标为基座坐标 `[0.430, -0.220, -0.320]` m。调整基座坐标下的 RGB-D 裁剪范围，使其世界坐标范围保持一致。 |
| 扰动 | 种子 41–60，奇数沿 +X，偶数沿 −Y，每次平移 75 mm。 |
| 遮挡 | 三个固定图像区域遮挡头部相机 RGB，并把对应深度标为无效。无遮挡的 overview 相机可用于 RGB-D 位姿回退。 |
| 代码模型 | Qwen2.5-Coder-3B-Instruct，BF16 贪心解码。 [权重版本](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct/tree/488639f1ff808d1d3d0ba301aef8c11461451ec5) |

在该实验布局中，原厂固定支座的 `base_3_Link` 网格与世界 Z = 0 的地面相交约 **13.0 cm**。本页仅验收仿真机械臂的 Cube Lift 恢复。完整场景仍需匹配支座，实体设备的安装基准仍需标定。

## 评测结果

在 0.450 m 高差下，原归位姿态的 S1 和 S2 Oracle 均在种子 21–24 的首次接近遇到 IK 失败。采用新归位姿态和 RGB-D 裁剪后，S2 无扰动首轮成功 **4/4**，双方向扰动后的第二轮恢复 **4/4**。Oracle 预检测得最小臂关节限位余量约为 0.00045 rad。

| 指标 | 文本反馈 | 文本 + VDM |
| --- | ---: | ---: |
| 首轮空抓 | 20/20 | 20/20 |
| 恢复成功 | 20/20 | 20/20 |
| 恢复时使用 overview 的种子 | 12/20 | 12/20 |
| 移动方向正确 | — | 20/20 |

两组实际动作序列 20/20 一致，恢复程序 13/20 完全相同。本轮没有测出恢复率提升。首轮前后的红像素遮挡比例中位数分别为 59.3% 和 54.5%，14/20 对图像在两帧中都至少遮住 25% 红像素。

两组逐种子匹配首轮物理状态和深度帧，恢复提示只相差一条 VDM 描述。40 张 RGB 图中有 24 张在重渲染时出现微小差异，每张最多 6 个像素、单通道差值最多 1。核对红色识别掩码一致后，VDM 对这些帧使用已校验的文本基线快照。

## 复跑步骤

1. 按仿真指南安装环境和官方资产，将 `TRON2_MJCF_PATH` 指向原始 `robot_grasper.xml`。将 `CAPX_MODEL_URL` 设为完整的 OpenAI 兼容 Chat Completions 端点，将 `CAPX_MODEL_NAME` 设为端点接受的模型 ID。从仓库根目录运行以下命令。 [安装说明](tron2_bringup.md#setup)
2. 先运行文本反馈组。

   ```bash
   export MUJOCO_GL=egl
   recovery_options=(
     --config env_configs/tron2/cube_lift_s1_guided_multi.yaml
     --model "$CAPX_MODEL_NAME" --server-url "$CAPX_MODEL_URL"
     --start-seed 41 --trials 20 --offset-directions '+X,-Y'
   )
   python -m capx.envs.evaluate_tron2_calibrated_occlusion "${recovery_options[@]}" \
     --output outputs/tron2_calibrated_occlusion/text.json
   ```

3. 在同一个 shell 中运行配对 VDM 组。保留文本组输出的 `text.json` 和 `text_frames/`，两者用于校验配对。每次复跑使用新输出目录。日志包含各组成功数，JSON 还包括头部相机遮挡统计、位姿相机调用轨迹和 RGB 快照回放记录。冒烟测试可把 `--trials 20` 改成 `--trials 2`。

   ```bash
   python -m capx.envs.evaluate_tron2_calibrated_occlusion "${recovery_options[@]}" \
     --baseline outputs/tron2_calibrated_occlusion/text.json --target-motion \
     --output outputs/tron2_calibrated_occlusion/vdm.json
   ```
