# 🐱 AI 桌宠（小团子）

一只住在桌面上的桌宠，可以接入**本地大模型**（Ollama / LM Studio / vLLM / llama.cpp / KVMem 等）。
纯 Python + PySide6 实现：透明置顶窗口 + 序列帧动画 + 流式聊天。

- 形象支持**任意序列帧素材**（也内置了代码绘制的备用小猫，没有素材也能跑）
- 模型支持**多端点自动回退**：配置里写几个端点，哪个开着就用哪个

## 功能

- 透明、无边框、置顶，可随意拖动；透明区域**不挡鼠标**（点击可穿透到桌面）
- 会发呆、眨眼、闲逛、犯困睡觉、被双击时会撒娇
- **单击** → 打开聊天窗口；**双击** → 打招呼；**右键** → 菜单（睡觉 / 走动 / 配色 / 退出）
- 聊天窗口流式回复（模型吐一个字显示一个字），头顶气泡同步显示
- 启动自动问候，聊天窗口内可一键"检测模型"
- 自动适配 **高 DPI**（125% / 150% 缩放不发糊）

## 快速开始

### 方式一：一键启动（推荐）

```bash
git clone https://github.com/husky84/AI-desktop-pets.git
cd AI-desktop-pets
```

| 系统 | 双击 / 执行 | 说明 |
| --- | --- | --- |
| Windows | `run.bat` | 自动找 Python、缺依赖会问你要不要装、无控制台启动 |
| macOS / Linux | `./run.sh` | 同上（首次可能要 `chmod +x run.sh`）|

脚本会自动探测多个 Python 位置，并**优先选择已经装好依赖的那个**，不会重复下载 PySide6。

### 方式二：手动运行

```bash
pip install -r requirements.txt
python main.py                 # 会用当前目录的 config.json
python main.py --config 路径   # 或指定配置文件
```

> 配置文件不存在时会自动从 `config.example.json` 生成一份 `config.json`，
> 改完重启生效。也可以打包安装：`pip install .` 之后在任意终端敲 `ai-deskpet`。

### 接上你的本地模型

宠物**不依赖模型也能跑**（会用代码画的小猫 + 本地问候），配好模型后才会接大模型聊天。

- **Ollama**（最常见）：
  ```bash
  ollama pull qwen2.5:7b
  ```
  `config.json` 里 `api_format: "ollama"`、`base_url: "http://localhost:11434"`。
- **LM Studio / vLLM / llama.cpp server**：把 `api_format` 改成 `"openai"`，
  `base_url` 填 `http://127.0.0.1:1234/v1`，`model` 填服务里的模型名，
  `api_key` 随便填个占位符（如 `not-needed`）。
- **多个端点**：写进 `fallbacks` 数组，主端点连不上会自动切换并记住可用的那个。

## config.json 说明

| 字段 | 含义 |
| --- | --- |
| `ai.api_format` | `"ollama"` 或 `"openai"`（OpenAI 兼容接口） |
| `ai.base_url` | Ollama：`http://localhost:11434`；OpenAI 兼容：`http://localhost:1234/v1` |
| `ai.model` | 模型名，如 `qwen2.5:7b`、`qwen3.8-27b-gsq-rco` |
| `ai.api_key` | 本地服务随便填个占位符（如 `not-needed`），留空则不发 Authorization 头 |
| `ai.fallbacks` | 备用端点列表，主端点连不上自动切换并记住可用的那个 |
| `ai.extra_body` | 提供方特有参数，会并入请求体（如关闭思考） |
| `ai.system_prompt` | 人设提示词（小团子的性格） |
| `ai.temperature` | 温度，越高越放飞 |
| `ai.max_tokens` | 单次回复最大 token 数 |
| `pet.name` | 小猫的名字 |
| `pet.auto_walk` | 是否自动闲逛 |
| `pet.bubble_seconds` | 气泡显示秒数 |
| `pet.sleep_after_seconds` | 多久没互动就睡觉 |
| `pet.theme` | 代码小猫配色：`cream` / `mint` / `pink` / `blue` |
| `pet.images` | 按动作分文件的序列帧素材（推荐，见下） |
| `pet.image` | 单条序列帧素材路径（所有状态共用；留空且无 images = 用代码画的小猫） |
| `pet.frames` | 每条序列图含几帧（留空则按 宽 ÷ 高 自动推算） |
| `pet.height` | 角色显示高度（像素），默认 250 |
| `pet.fps` | 各状态播放帧率，如 `{"idle": 4, "walk": 8, "happy": 6, "sleep": 2}` |
| `pet.click_mask` | 是否给窗口加形状遮罩。Windows 默认 `false`（透明像素本来就点击穿透）；其他平台默认 `true` |

> 💡 **关于清晰度**：程序会按屏幕缩放比例（125% / 150% 等）生成素材并渲染，
> 不会出现被系统放大而发糊的问题。想要最清晰，让素材内容高度 ≥ `pet.height` × 屏幕缩放即可
> （本项目素材约 310px，配 `height: 250` + 125% 缩放正好 1:1）。
> 觉得不够大可以调大 `pet.height`，但超过素材原始像素后会开始变软。

> ⚠️ 路径请用**正斜杠**（`assets/x.png`）。Windows 的反斜杠在 JSON 里是转义符，
> 写成 `"E:\桌宠\x.png"` 会导致整份配置解析失败（程序会自动修复并弹提示，但建议直接写对）。

## 交互一览

| 操作 | 效果 |
| --- | --- |
| 左键单击小猫 | 打开聊天窗口 |
| 左键拖动 | 移动小猫 |
| 双击小猫 | 撒娇冒泡 |
| 右键小猫 | 菜单：聊天 / 打招呼 / 睡觉 / 走动开关 / 退出 |
| 聊天框 Enter | 发送消息（流式回复） |

## 换形象（两种方式）

### 方式一：代码小猫换配色（最简单）

- **实时切换**：右键小猫 → 🎨 外观，选 奶油 / 薄荷 / 樱粉 / 海蓝
- **永久生效**：改 `config.json` 的 `pet.theme`（`cream` / `mint` / `pink` / `blue`），重启

### 方式二：换成自定义图片（推荐用 AI 生图）

准备**透明背景**的 PNG。用 AI 画图时可以这样描述：
> "cute chibi catgirl, full body, front view, flat color, transparent background, no shadow"

**A. 每个动作用各自的序列图（推荐，本项目的 `catgirl_pet_v1` 就是这么配的）**

```json
"pet": {
  "images": {
    "idle": "assets/catgirl_pet_v1/strips/idle_strip.png",
    "walk": "assets/catgirl_pet_v1/strips/walk_strip.png",
    "happy": "assets/catgirl_pet_v1/strips/wave_strip.png",
    "sleep": "assets/catgirl_pet_v1/strips/sleep_strip.png"
  },
  "frames": 4,
  "height": 250,
  "fps": { "idle": 4, "walk": 8, "happy": 6, "thinking": 4, "sleep": 2 }
}
```

状态对应关系：`idle` 待机、`walk` 走动、`happy` 开心（挥手）、`sleep` 睡觉、`thinking` 思考。
某个状态没配就自动回退（开心→wave→idle，睡觉→idle），所以少配几个也不会报错。

**B. 只有一条序列图**：用 `"image": "assets/xxx_strip.png"`，所有状态共用它。

制作要点：

1. 把多帧画面**横向拼成一张长图**，每帧等宽（例如 4 帧 1312×320 → 每帧 328×320）
2. 程序会自动：裁掉每帧透明留白 → 按内容水平居中 → 底边对齐地面 → 统一缩放
   （这几步专治 AI 生图"每帧位置漂移"导致的左右抖动）
3. `frames` 可省略：会按 `宽 ÷ 高` 自动推算
4. 睡觉动画会**播完一次后停在最后一帧**，符合"犯困 → 入睡"的表现

加载失败时会在控制台打印提示，并自动回退到代码小猫，不会崩。

> 注：使用自定义图片后，右键菜单里的"🎨 配色"子菜单不再显示。

### 方式三：从零重画一套素材

`assets/catgirl_pet_v1/` 里已有可直接参考的结构：
`frames/<动作>/<动作>_NN.png` 单帧、`strips/<动作>_strip.png` 横向序列图、
`catgirl_sprite_sheet.png` 4×4 总表。照着这个结构生成新素材即可。

## 常见问题

- **气泡里只出现默认文字、聊天报错？** 模型服务没起或模型名不对。
  先在聊天窗口点"检测模型"，或命令行执行 `ollama list` 核对名字。
- **想换人设？** 改 `ai.system_prompt` 即可，重启生效。
- **想让它更安静/更话痨？** 调 `temperature` 和 `max_tokens`。
- **改完 config.json 形象没变？** 多半是路径写法问题：JSON 里的 `\` 是转义符，
  写成 `"E:\桌宠\x.png"` 会让整份配置解析失败。用正斜杠 `assets/x.png`，
  或看聊天窗口有没有弹出配置报错提示。
- **画面出现网格状空洞 / 颜色发灰？** 这是窗口形状遮罩把图像当 1bit 抖动处理了。
  已修复：Windows 下默认不加遮罩（`pet.click_mask: false`），透明区域照样点击穿透。
- **多显示器？** 小猫活动范围是主显示器的可用区域。

## 文件结构

```
├── main.py               # 入口（也可以 python -m / pip 安装后用 ai-deskpet 命令）
├── pet.py                # 宠物窗口（序列帧素材 / 程序化绘制 + 状态机 + 高 DPI）
├── chat.py               # 聊天窗口（流式回复）
├── ai_client.py          # 本地模型客户端（Ollama / OpenAI 兼容 + 多端点回退）
├── run.bat / run.sh      # 一键启动器（纯 ASCII + CRLF，见下方说明）
├── tools/launch.py       # 启动器实际逻辑：依赖检查 / 安装 / 拉起主程序
├── config.example.json   # 配置模板（首次运行自动复制成 config.json）
├── pyproject.toml        # 打包元数据（pip install . 后可敲 ai-deskpet）
├── assets/               # 形象素材（catgirl_pet_v1：4 动作 × 4 帧 + 总表）
├── LICENSE               # MIT
└── requirements.txt
```

> Windows 启动器的两个设计约束（都是踩坑换来的）：
> 1. **纯 ASCII**：`cmd.exe` 按系统码页解析批处理文件，UTF-8 中文会把同一行
>    后面的命令一起吃掉（表现为一堆 `'mport' is not recognized`）。
>    所以中文提示全部放在 `tools/launch.py` 里。
> 2. **不用 `call :label`**：批处理只有 LF 换行时，cmd 的标签扫描会按字节
>    错位（git 规范化换行符很容易造成 LF-only）。改成无标签后，LF/CRLF 都能跑。
>
> 另外启动器会**扫描机器上所有 Python，优先选已经装好 PySide6 的那个**——
> 免得像本机这样同时有 Python 3.14 和 miniconda 时，往干净的那个里重下 250MB。

## 许可证

代码采用 [MIT License](LICENSE)。

`assets/catgirl_pet_v1/` 下的角色素材由 AI 生成，仅供学习交流使用；
若要商用请自行确认版权，或替换成你拥有版权的素材（见"换形象"一节）。
