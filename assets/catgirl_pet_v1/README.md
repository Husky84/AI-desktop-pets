# 猫娘桌宠动画素材 v1

这套素材包含 16 张透明背景 PNG，角色尺寸与画风保持一致。

## 动作

- `idle`：4 帧待机呼吸循环
- `walk`：4 帧原地行走循环
- `wave`：4 帧挥手循环
- `sleep`：4 帧犯困到入睡动作（最后一帧可停留）

每个动作目录中的单帧画布为 328 × 320 像素。`strips` 目录提供横向拼接的 4 帧序列图（1312 × 320 像素），可直接配合项目中的 `pet.image` 与 `pet.frames: 4` 使用。

`catgirl_sprite_sheet.png` 是 4 × 4 完整总表，排列顺序从上到下依次为 idle、walk、wave、sleep。

建议播放速度：idle 4 FPS、walk 8 FPS、wave 6 FPS、sleep 2 FPS。
