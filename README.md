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
- 👀 **屏幕感知**：知道你在写代码 / 看视频 / 摸鱼，会主动搭话（久坐、深夜、离开回来都会提醒）

## 快速开始

### 方式一：一键启动（推荐）

```bash
git clone https://github.com/Husky84/AI-desktop-pets.git
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
| `ai.active` | 默认使用哪个模型来源（`profiles` 里的名字），右键菜单可随时切换 |
| `ai.profiles` | **模型来源列表**：本地 / 云端 API 各自一份配置，见下节 |
| `ai.vision_profile` | 看图用哪个来源（不填就跟 `active`；用来实现"聊天走云端、看图走本地"）|
| `ai.system_prompt` | 人设提示词（小团子的性格） |
| `ai.temperature` | 温度，越高越放飞 |
| `ai.max_tokens` | 单次回复最大 token 数 |

每个来源（profile）里可以写：

| 字段 | 含义 |
| --- | --- |
| `api_format` | `"ollama"`（Ollama 原生）或 `"openai"`（OpenAI 兼容，绝大多数都支持） |
| `base_url` | 本地如 `http://127.0.0.1:1234/v1`；云端如 `https://api.deepseek.com/v1` |
| `model` | 模型名，如 `qwen2.5:7b`、`deepseek-chat` |
| `api_key` | 密钥（本地服务随便填占位符如 `not-needed`）|
| `api_key_env` | 或者只写**环境变量名**（如 `DEEPSEEK_API_KEY`），密钥就不落在配置文件里 |
| `vision` | 这个来源能不能看图；`false` 时视觉层会自动改用它之外的来源 |
| `proxy` | 该来源专用的代理，如 `http://127.0.0.1:7892`（默认直连）|
| `extra_body` | 提供方特有参数，并入请求体（如关闭思考）|
| `fallbacks` | 备用端点，主端点连不上自动切换并记住可用的那个 |

### 模型来源：本地 或 云端 API

配好之后，**右键桌宠 → 🤖 模型来源** 就能切换，选择会写回 `config.json` 的 `ai.active`，下次启动沿用。

```json
"ai": {
  "active": "local",
  "vision_profile": "local",
  "profiles": {
    "local": {
      "api_format": "openai",
      "base_url": "http://127.0.0.1:1234/v1",
      "model": "qwen3.8-27b-gsq-rco",
      "api_key": "not-needed",
      "vision": true,
      "extra_body": { "reasoning_effort": "none" }
    },
    "deepseek": {
      "api_format": "openai",
      "base_url": "https://api.deepseek.com/v1",
      "model": "deepseek-chat",
      "api_key_env": "DEEPSEEK_API_KEY",
      "vision": false
    }
  }
}
```

> 💡 `vision: false` 的妙用：云端的 `deepseek-chat` 看不了图，所以上面把
> `vision_profile` 固定成 `local` —— **聊天走云端（快、便宜），看图仍走本地（免费、隐私）**。
> 反过来也行：本地聊天 + 云端视觉。

> 旧版的扁平写法（顶层直接写 `base_url` / `model` / `fallbacks`）仍然兼容，会被当成一个叫 `default` 的来源。
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

### watch（屏幕感知）

| 字段 | 含义 |
| --- | --- |
| `watch.enabled` | 是否开启屏幕感知（右键菜单里也能随时开关） |
| `watch.poll_seconds` | 采样间隔，默认 15 秒（只读窗口标题，开销可忽略） |
| `watch.min_gap_seconds` | 两次主动搭话的最小间隔，防话痨，默认 150 秒 |
| `watch.vision` | 是否允许看截图（需要模型支持视觉；关掉就只用窗口标题） |
| `watch.vision_interval_seconds` | 视觉点评间隔，默认 300 秒（独立定时器精确触发，最小 15 秒）|
| `watch.max_width` | 截图缩放到的宽度，默认 1024（越小越快、越省显存） |
| `watch.blacklist` | 追加的隐私关键词，命中的窗口不截图（内置已含密码/银行/支付等） |

## 屏幕感知（它会知道你在干什么）

两层设计，**尽量少打扰、也不乱看**：

| 层 | 做什么 | 开销 |
| --- | --- | --- |
| 轻量层 | 读前台进程名 / 窗口标题 / 键鼠空闲时间，归到 写代码·浏览·看视频·游戏·文档·聊天·设计 | 几乎为零，每 `poll_seconds` 一次 |
| 视觉层 | 截图（缩放后）交给视觉模型，让它以桌宠口吻点评 | 独立定时器，严格每 `vision_interval_seconds` 一次 |

触发反馈的场景：

- 换了个程序 → 有较大概率搭话（"又在敲代码呀，我安静看着 (oωo)"）
- 同一个程序坐了 50 分钟 → 提醒起来动动
- 凌晨 0–5 点还在用 → "都这个点了还不睡？"
- 键鼠空闲 10 分钟以上 → "人跑哪去了……"；回来时 → "你回来啦！"
- 到间隔了就截图点评 → "终端黑乎乎一片，是在憋大招吗？(oωo)"

**隐私设计**（重要）：

- 截图**只发给你自己配置的模型**（本项目默认就是本机 LM Studio / Ollama），不经过任何云端
- 内置隐私关键词（密码 / 银行 / 支付 / 钱包 / 2FA…）命中的窗口：**不截图、不点评，标题也不会进入上下文**
- 桌宠自己的窗口会被忽略，避免自问自答
- 右键 → `🔕 停止观察` 可随时彻底关掉；`👀 看看我在干嘛` 可手动让它看一眼

> 想要视觉能力，模型必须是多模态的（比如 Qwen-VL 系列，或带 `mmproj` 视觉头的 GGUF）。
> 模型看不了图时，程序会自动退回轻量层，只根据窗口标题陪你。

## 交互一览

| 操作 | 效果 |
| --- | --- |
| 左键单击小猫 | 打开聊天窗口 |
| 左键拖动 | 移动小猫 |
| 双击小猫 | 撒娇冒泡 |
| 右键小猫 | 菜单：聊天 / 打招呼 / 睡觉 / 走动开关 / **看看我在干嘛** / **停止观察** / 退出 |
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
├── ai_client.py          # 本地模型客户端（Ollama / OpenAI 兼容 + 多端点回退 + 多模态）
├── activity.py           # 屏幕活动采集（前台窗口 / 空闲时间 / 截图 / 隐私过滤）
├── watcher.py            # 屏幕感知的决策层（行为规则 + 视觉点评调度）
├── run.bat / run.sh      # 一键启动器（纯 ASCII + 无标签，见下方说明）
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
