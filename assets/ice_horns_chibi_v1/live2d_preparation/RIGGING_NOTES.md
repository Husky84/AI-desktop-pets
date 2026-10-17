# Live2D 拆件草稿交接

## 当前状态

可以将这个角色制作成 Live2D。当前交付是正面原画、独立部件 PNG 和 16 层的拆件板 PSD，尚未完成模型绑定。PNG 动画与 Live2D 模型是两条制作路线。

PSD 中的部件保留在拆件板上的位置，需要精修并在统一角色坐标中重新对齐。左右命名均按画面观察者视角，不是角色解剖学视角。

## 需要精修的内容

1. 后发草稿仍包含刘海和呆毛，需清除重复部分、补全后脑；与前发、独立呆毛分开。
2. 躯干草稿仍带部分袖子，需在腋下和肩部补全衣服并移除重复袖子；独立双臂需要肩关节重叠区域。
3. 眼睛当前各是一张完整图，需要进一步拆成眉、上睫毛、下睫毛、眼白、虹膜与高光，并准备闭眼形状。
4. 嘴和鼻子同一图层，需要进一步拆分；嘴部需要口腔、上唇、下唇等结构才能自然开口。
5. 镜片需确认半透明度与眼睛的遮挡顺序。背包、带子、几何衣纹需要按实际摆动范围再细拆。
6. 所有旋转处补全被遮挡的像素，检查接缝；生成部件不能保证无缝复原正面立绘。

建议精修后的图层栈（前到后）：镜片、前发/呆毛、角、眉眼与嘴、脸底、前侧手臂、衣服与束带、后侧手臂、双腿、后发、背包。

## 建议参数（待建模后才能生效）

| 参数 | 建议范围 | 作用 |
|---|---|---|
| ParamAngleX / ParamAngleY / ParamAngleZ | -15 到 15 | 小幅转头和歪头 |
| ParamEyeLOpen / ParamEyeROpen | 0 到 1 | 眨眼 |
| ParamEyeBallX / ParamEyeBallY | -1 到 1 | 视线跟随 |
| ParamMouthOpenY | 0 到 1 | 说话口型 |
| ParamBreath | 0 到 1 | 呼吸 |
| ParamBodyAngleX / ParamBodyAngleZ | -10 到 10 | 身体轻摆 |
| 自定义 HairSway / StrapSway | -1 到 1 | 发梢与带子摆动 |

在 Cubism 中建立 ArtMesh、旋转/曲面变形器和参数关键形后，再设置头发与束带物理。检查转头露底、镜片顺序、眨眼闭合及袖口接缝，然后导出 `.moc3`、`.model3.json`、纹理与所需物理/动作文件，并在兼容的播放程序验证。

当前桌宠使用 PNG 序列绘制。若改用 Live2D，还需在桌宠中接入兼容的模型渲染运行时，不能只把配置里的 PNG 路径换成 PSD 或 model3.json。

## 官方参考

- 材质拆分：https://docs.live2d.com/en/cubism-editor-manual/divide-the-material/
- PSD 导入：https://docs.live2d.com/en/cubism-editor-manual/psd-import/
- 运行数据导出：https://docs.live2d.com/en/cubism-editor-manual/export-moc3-motion3-files/
