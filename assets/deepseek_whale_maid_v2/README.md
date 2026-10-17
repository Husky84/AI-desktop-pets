# 参考图版鲸鱼娘桌宠素材

按用户提供的蓝发女仆鲸鱼娘参考图，使用内置图像生成工具制作。保留长卷发、女仆头饰、蓝白裙装、围裙鲸鱼图案、鱼鳍与尾巴。

32 张独立透明 PNG：idle（待机）、walk（行走）、wave（挥手）、sleep（睡眠）各 8 帧。独立帧尺寸 256 × 256；strips 目录中的横向序列尺寸 2048 × 256。sprite_sheet.png 是原始总表。

建议待机、睡眠 8–12 FPS，行走、挥手 12–15 FPS。当前程序绘制上限约 15 FPS，素材播放参数本身不能突破程序上限。8 帧为生成的原始动作帧，未重复帧数或合成插值；帧间可能有轻微形状变化。

可将 pet.image 设为 assets/deepseek_whale_maid_v2/strips/idle_strip.png，将 pet.frames 设为 8；多动作可映射 idle、walk、happy（wave）、sleep。此次未修改程序配置。

prompt.txt 保存完整生成提示。split.ps1 保存透明裁切和拆分流程。
