# 冰蓝尖角角色桌宠素材

按用户提供的参考形象制作：冰蓝短发、双尖角、棕色大眼、单片眼镜、白蓝几何纹服装和背包束带。内置图像生成工具绘制，随后按真实透明区域拆分和打包。参考图中的悬浮屏幕、星星与机器人未加入动作帧，以便桌宠独立显示。

## PNG 动画（可使用）

- `frames/idle`：8 帧待机与眨眼。
- `frames/walk`：8 帧向右行走。
- `frames/wave`：8 帧挥手。
- `frames/sleep`：8 帧坐姿睡眠呼吸。
- `strips`：对应的横向 8 帧序列图。
- `sprite_sheet.png`：原始 8 列 × 4 行总表。

独立帧为 320 × 320 RGBA PNG，横向序列为 2560 × 320。角色按原生分辨率放入画布，未放大冒充细节。每动作有 8 张生成帧，未靠重复帧增加数量。建议待机 6–8 FPS、行走与挥手 12–15 FPS、睡眠 4–6 FPS。生成帧之间存在轻微线条、服饰和姿态变化。

`preview.html` 可在浏览器中打开，查看透明背景与循环动作。它是本地素材预览，不是 Live2D 播放器。

当前 Python 桌宠的单动作配置示例：

```json
{
  "image": "assets/ice_horns_chibi_v1/strips/idle_strip.png",
  "frames": 8
}
```

本次未修改现有程序或配置。

## Live2D 准备资料（尚未绑定）

`live2d_preparation/neutral_front.png`：1024 × 1536 的正面原画参考。

`live2d_preparation/parts`：16 张独立部件 PNG。

`live2d_preparation/parts_board_DRAFT.psd`：16 个独立、可编辑的图层，保持拆件板排列，用于拆件精修。它不是已经对齐合成的角色 PSD，更不是运行模型。

`live2d_preparation/RIGGING_NOTES.md`：缺陷、图层精修建议、绑定参数与完成步骤。

目前没有 `.cmo3`、`.moc3` 或可加载的 `.model3.json`。常见程序安装目录中未发现 Cubism，无法在本次环境中完成真实网格绑定与导出验证。PSD 以标准 RGB/8 位、多图层格式写出，并做结构及合成图读取检查；未在 Cubism 中验证导入。

完整生成提示见 `prompts`，透明通道、边界与文件格式检查见 `validation.json`。
