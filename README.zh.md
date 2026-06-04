# Audio-Video2Text-AI

[English](README.md) | [中文](README.zh.md)

一个跨平台音视频转写工具，支持 CLI、网页和桌面应用三种使用方式。可从视频文件中提取音频，使用多种 AI 进行语音转写，并支持演讲人标注、翻译和会议纪要生成。

## 功能特点

- **直接输入视频** — 选择任意视频/音频文件（mp4、mkv、mov、mp3、wav 等），ffmpeg 自动提取音轨
- **自动切片** — 将长音频切成短片段（默认 180 秒），避免模型截断和幻觉
- **演讲人区分** — 使用音频理解模型标注不同说话人（演讲人1、演讲人2，或真实姓名）
- **重复检测** — 自动检测 ASR 输出中的死循环/乱码
- **API Key 加密存储** — 使用基于机器信息的 Fernet 加密，保存在本地
- **多 ASR 提供商** — MiMo、OpenAI STT、本地 Whisper
- **多 LLM 提供商** — ChatGPT、Claude、Kimi、MiniMax、MiMo、Ollama
- **三种使用方式** — CLI 脚本、Web 应用（FastAPI + Next.js）、桌面应用（Electron）

## 支持的 AI 提供商

### ASR（语音识别）

| 提供商 | 直接音频输入 | 支持语言 | 状态 |
|--------|------------|---------|------|
| 小米 MiMo ASR | ✅ | 中文、英文、自动 | ✅ 已支持 |
| OpenAI Speech-to-Text | ✅ | 50+ 种语言 | 计划中 |
| 本地 Whisper / faster-whisper | ✅ | 99 种语言 | 计划中 |

### LLM（文本处理）

| 提供商 | 音频输入 | 文本处理 | 状态 |
|--------|---------|---------|------|
| 小米 MiMo v2.5 / Omni | ✅ | ✅ | ✅ 已支持 |
| OpenAI / ChatGPT | ✅ | ✅ | 计划中 |
| Anthropic Claude | ❌ | ✅ | 计划中 |
| 月之暗面 Kimi | ❌ | ✅ | 计划中 |
| MiniMax | ❌ | ✅ | 计划中 |
| 本地 LLM（Ollama） | ❌ | ✅ | 计划中 |

> **架构说明**：本工具将"听"（ASR）和"整理"（LLM 后处理）分开。不是所有模型都能直接处理音频 — Claude、Kimi、MiniMax 和本地 LLM 只能处理转写后的文本，用于演讲人标注、翻译、总结和会议纪要。

## 技术栈

```
┌─────────────────────────────────────────────────┐
│              Electron 桌面应用                    │
│  ┌───────────────────────────────────────────┐  │
│  │         Next.js 前端 (React)              │  │
│  │   页面 / 组件 / 实时进度                   │  │
│  └──────────────────┬────────────────────────┘  │
│                     │ HTTP / WebSocket           │
│  ┌──────────────────▼────────────────────────┐  │
│  │         FastAPI 后端 (Python)             │  │
│  │   API 路由 / WebSocket / 认证             │  │
│  │   ┌─────────────────────────────────┐     │  │
│  │   │   核心引擎 (Python)             │     │  │
│  │   │   ASR / LLM / FFmpeg / 流水线   │     │  │
│  │   └─────────────────────────────────┘     │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

| 层级 | 技术 | 职责 |
|------|------|------|
| **前端** | Next.js + React + TypeScript | 页面 UI、文件上传、实时进度、设置管理 |
| **后端** | FastAPI (Python) | API 路由、WebSocket、认证、配置管理 |
| **核心引擎** | Python | ASR/LLM 提供商、FFmpeg、转写流水线 |
| **桌面端** | Electron | 跨平台外壳、原生文件访问、系统托盘 |
| **命令行** | Python (argparse) | 直接命令行使用 |

## 快速开始（CLI）

### 环境要求

- Python 3.10+
- ffmpeg 已安装并加入 PATH
  - Windows：`winget install Gyan.FFmpeg`
  - Mac：`brew install ffmpeg`
  - Linux：`sudo apt install ffmpeg`

### 安装依赖

```bash
pip install openai cryptography
```

### 运行

```bash
python mimo_choose_file_transcribe.py
```

脚本会依次引导你完成：

1. **设置 API Key** — 输入 MiMo API Key（自动加密保存，下次免输入）
2. **选择模型** — ASR（纯转写）/ v2.5 / Omni（可区分演讲人）
3. **选择语言** — 中文 / 英文 / 自动检测
4. **选择文件** — 通过文件对话框选择任意视频或音频文件
5. **自动处理** — 提取音频 → 切片 → 转写 → 保存结果

### 命令行参数

```bash
python mimo_choose_file_transcribe.py --segment-seconds 180 --bitrate 128k
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--segment-seconds` | 180 | 切片长度（秒） |
| `--bitrate` | 128k | 提取音频的 MP3 码率 |
| `--prompt` | （内置） | 自定义演讲人区分提示词 |

### 环境变量

可设置以下环境变量跳过交互式输入：

```bash
MIMO_API_KEY=sk-xxxxx        # 或 tp-xxxxx（Token Plan）
MIMO_BASE_URL=https://api.xiaomimimo.com/v1
```

## 输出文件

结果保存在原文件旁边：

```
meeting.mp4
meeting.mp3                          # 提取的音频（保留）
meeting_mimo_work/                   # 工作目录
  parts_asr/                         # 切片后的音频片段
    part_001.mp3
    part_002.mp3
    ...
meeting.omni.speaker_transcript.txt  # 最终转写结果
```

## 路线图

### v0.1 — CLI 最小可用版 ✅
- [x] MiMo ASR / v2.5 / Omni 转写
- [x] 自动切片 + 重复检测
- [x] API Key 加密持久化
- [x] 演讲人区分（Prompt 方式）
- [x] 中英文支持

### v0.2 — 多提供商
- [ ] 多 ASR 提供商：OpenAI STT、本地 Whisper（faster-whisper）
- [ ] 多 LLM 提供商：ChatGPT、Claude、Kimi、MiniMax、Ollama
- [ ] ASR + LLM 流水线架构（ASR 负责听，LLM 负责整理）
- [ ] 输出格式：SRT 字幕、VTT 字幕、JSON（保留时间戳）
- [ ] 批量处理（整个文件夹）
- [ ] YAML 配置文件支持

### v0.3 — 高级功能
- [ ] pyannote / WhisperX 专业演讲人分离
- [ ] 自动章节检测
- [ ] 双语字幕
- [ ] 会议纪要 / 摘要生成
- [ ] 完全离线模式（本地 Whisper + Ollama）
- [ ] pip 可安装包（`pip install audio-video2text`）

### v0.4 — Web 应用（FastAPI + Next.js）
- [ ] FastAPI 后端（REST API + WebSocket）
- [ ] Next.js 前端（React + TypeScript）
- [ ] 浏览器端文件上传和转写
- [ ] WebSocket 实时进度展示
- [ ] Web 端 API Key 和提供商管理
- [ ] 长任务队列
- [ ] Docker Compose 部署（可选，用于服务器托管）

### v0.5 — Electron 桌面应用
- [ ] Electron 外壳（封装 FastAPI + Next.js）
- [ ] 内嵌 Python 运行时（PyInstaller / python-embedded）
- [ ] 原生文件拖拽
- [ ] 系统托盘和桌面通知
- [ ] 自动更新机制（electron-updater）
- [ ] 内置 ffmpeg 和 Whisper 模型（完全离线可用）

## 项目结构（规划中）

```
Audio-Video2Text-AI/
├── README.md
├── README.zh.md
├── LICENCE
├── .gitignore
│
├── backend/                        # FastAPI 后端 + 核心引擎
│   ├── requirements.txt
│   ├── main.py                     # FastAPI 入口
│   ├── api/
│   │   ├── routes/
│   │   │   ├── transcribe.py       # POST /api/transcribe
│   │   │   ├── providers.py        # GET /api/providers
│   │   │   └── tasks.py            # GET /api/tasks/{id}
│   │   └── websocket.py            # WebSocket 进度推送
│   ├── core/
│   │   ├── config.py               # 加密配置管理
│   │   ├── pipeline.py             # ASR → LLM 流水线
│   │   └── task_queue.py           # 后台任务管理
│   ├── providers/
│   │   ├── asr/
│   │   │   ├── base.py
│   │   │   ├── mimo_asr.py
│   │   │   ├── openai_asr.py
│   │   │   └── local_whisper.py
│   │   └── llm/
│   │       ├── base.py
│   │       ├── openai_chat.py      # ChatGPT / Kimi / MiniMax
│   │       ├── claude.py
│   │       ├── mimo_chat.py
│   │       └── ollama.py
│   ├── media/
│   │   ├── ffmpeg.py               # 音频提取和切片
│   │   └── picker.py               # 文件选择器（仅 CLI）
│   ├── prompts/
│   │   ├── speaker_zh.txt
│   │   └── speaker_en.txt
│   └── output/
│       └── writers.py              # txt / srt / vtt / json 输出
│
├── frontend/                       # Next.js 前端
│   ├── package.json
│   ├── next.config.js
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx            # 首页 / 文件上传
│   │   │   ├── transcribe/
│   │   │   │   └── page.tsx        # 转写进度页
│   │   │   ├── history/
│   │   │   │   └── page.tsx        # 历史记录
│   │   │   └── settings/
│   │   │       └── page.tsx        # API Key 和提供商设置
│   │   ├── components/
│   │   │   ├── FileDropzone.tsx
│   │   │   ├── ProviderSelect.tsx
│   │   │   ├── ProgressStream.tsx
│   │   │   └── TranscriptViewer.tsx
│   │   └── lib/
│   │       └── api.ts              # API 客户端
│   └── public/
│
├── electron/                       # Electron 外壳
│   ├── package.json
│   ├── main.ts                     # Electron 主进程
│   ├── preload.ts                  # 主进程 ↔ 渲染进程桥接
│   └── builder.yml                 # electron-builder 打包配置
│
├── cli/                            # CLI 入口（当前脚本）
│   └── mimo_choose_file_transcribe.py
│
└── examples/
    └── config.example.yaml
```

## 开发

### CLI（当前）

```bash
python mimo_choose_file_transcribe.py
```

### Web 应用（计划中）

```bash
# 后端
cd backend && pip install -r requirements.txt
uvicorn main:app --reload

# 前端
cd frontend && npm install && npm run dev
```

### Electron 桌面应用（计划中）

```bash
cd electron && npm install
npm run dev        # 开发模式
npm run build      # 打包
```

## 许可证

MIT
