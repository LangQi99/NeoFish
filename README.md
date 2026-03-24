<div align="center">
  <img src="docs/readme_img/new_icon.png" width="120" alt="NeoFish Logo" />
  <h1>NeoFish 🐟</h1>
  <p><strong>人人可用的 Agent，你的终极数字奴隶</strong></p>

  <p>
    <a href="https://github.com/LangQi99/NeoFish/stargazers"><img src="https://img.shields.io/github/stars/LangQi99/NeoFish?style=for-the-badge&color=00D4E4" alt="Stars"></a>
    <a href="https://github.com/LangQi99/NeoFish/network/members"><img src="https://img.shields.io/github/forks/LangQi99/NeoFish?style=for-the-badge&color=00D4E4" alt="Forks"></a>
    <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/Vue.js-3.5+-4FC08D?style=for-the-badge&logo=vue.js&logoColor=white" alt="Vue">
  </p>
</div>

---

## 🌟 什么是 NeoFish？

**NeoFish** 是一款旨在让人人都能轻松使用的全能 AI Agent 原型系统。它不仅是一个可以聊天的助手，更是一个能够真正**操控浏览器、接管繁琐工作**的数字劳动力。无需复杂的编程知识，只要用自然语言下达指令，NeoFish 就能像你最忠诚的“数字奴隶”一样，不知疲倦地在网页中为你点击、输入、提取信息、完成任务。

<p align="center">
  <img src="docs/readme_img/what-can-i-do-4-u.png" alt="NeoFish 主界面" width="800">
</p>

## ✨ 核心特性

<p align="center">
  <img src="docs/readme_img/takeover.png" alt="NeoFish 接管浏览器" width="800">
</p>

- 🤖 **全能浏览器交互**: 深度集成 `Playwright` 引擎，支持页面导航、元素点击、键盘输入、滚动和截图分析。
- ⚡️ **极速实时流式响应**: 基于 `FastAPI` 和 `WebSocket` 架构，实现后台 Agent 思考过程与前端 UI 的毫秒级状态同步。
- 🎨 **现代化丝滑前端 UI**: 采用 `Vue 3` + `Tailwind CSS` 打造的极简质感界面，内置流畅的对话滚动与状态指示。
- 🌍 **原生多语言支持**: 完整的中英文 (`i18n`) 支持，侧边栏一键顺滑切换。
- 🧠 **智能停顿与人工介入**: 当 Agent 遇到阻碍（如遇到验证码、需要扫码登录时），会自动暂停并截取当前画面发送给用户，等待人类确认后继续执行。
- 🛠️ **极简配置接入**: 通过标准 `.env` 配置，轻松接入任何支持工具调用 (Tool Use) 的大模型 API（默认兼容 Anthropic/OpenAI 接口规范）。

## 🏗️ 架构概览

NeoFish 采用轻量级的前后端分离架构设计：

- **服务端 (Backend)**: Python (`FastAPI` + `Playwright`)
  - 负责维护浏览器进程上下文。
  - 通过 WebSocket 接受前端指令。
  - 运行 Agent 核心逻辑：思考(Think) -> 调用工具(Action) -> 观察反馈(Observation)。
- **客户端 (Frontend)**: Web (`Vue 3` + `Vite` + `TailwindCSS`)
  - 负责与用户的交互可视化。
  - 实时渲染 Agent 的执行动作、日志和错误提示。
  - 内置完整的国际化语言包。

## 🖥️ 平台支持

NeoFish 支持多种接入平台，可按需选择一种或同时运行多种：

| 平台 | 说明 | 启动方式 |
|------|------|----------|
| 🌐 **Web** | 内置 Vue 3 网页界面，开箱即用 | `uv run uvicorn main:app --reload` |
| 💬 **Telegram** | 通过 Telegram Bot API 接入，随时随地使用 | `uv run python run_telegram.py` |
| 🐧 **QQ** | 通过 NapCat / go-cqhttp (OneBot v11) 接入 QQ | `uv run python run_qq.py` |

> 💡 也可以使用 `uv run python run_all.py` **同时启动所有已配置的平台**。

---

## 🚀 快速开始

### 1. 环境准备

确保你已安装强大的 Python 依赖管理工具 [uv](https://docs.astral.sh/uv/) 以及 `Node.js`。

### 2. 克隆项目

```bash
git clone https://github.com/LangQi99/NeoFish.git
cd NeoFish
```

### 3. 配置环境变量

在根目录创建或修改 `.env` 文件：

```env
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_BASE_URL=https://api.your-proxy.com
# 推荐使用具备强大推理与 Tool Call 能力的模型
MODEL_NAME=claude-3-7-sonnet-20250219 
```

### 4. 启动后端 (Agent 服务)

后端将自动安装所需依赖并启动网页交互引擎（首次运行可能会下载浏览器内核）：

```bash
uv run uvicorn main:app --reload
```
*服务将运行在 `http://127.0.0.1:8000`*

### 5. 启动前端 (UI 界面)

打开一个新的终端窗口：

```bash
cd frontend
npm install
npm run dev
```
*打开浏览器访问 `http://localhost:5173` 即可开始体验！*

---

## 🔌 平台接入指南

### 💬 Telegram Bot

1. 在 Telegram 中找到 [@BotFather](https://t.me/BotFather)，创建一个新 Bot 并获取 Token。
2. 在 `.env` 中添加以下配置：

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here

# 可选：只允许指定用户使用（留空则允许所有人）
# TELEGRAM_ALLOWED_USERS=123456789,987654321
```

3. 安装依赖并启动：

```bash
uv add python-telegram-bot
uv run python run_telegram.py
```

### 🐧 QQ Bot (NapCat / go-cqhttp)

1. 安装并启动 [NapCat](https://github.com/NapNeko/NapCatQQ)，使用 QQ 账号登录。
2. 在 NapCat 中开启**正向 WebSocket** 插件（默认端口 3001）。
3. 在 `.env` 中添加以下配置：

```env
QQ_WS_URL=ws://127.0.0.1:3001

# 可选：NapCat 访问令牌（未配置则留空）
# QQ_ACCESS_TOKEN=

# 可选：只允许指定用户/群使用（留空则允许所有人）
# QQ_ALLOWED_IDS=group_123456,private_987654
```

4. 启动 QQ Bot：

```bash
uv run python run_qq.py
```

### 🚀 同时启动所有平台

```bash
uv run python run_all.py
```

> 系统会根据 `.env` 中的配置自动决定启用哪些平台：Web 始终启动，Telegram 和 QQ 仅在对应 Token / URL 已配置时才会启动。

## 💡 使用场景示例

你可以对 NeoFish 说出以下指令：

- *"帮我打开掘金，搜索 'Vue3 性能优化'，并把前三篇文章的标题和链接总结给我。"*
- *"进入 Github，查看趋势榜单，截个图发给我。"*

- *"总结oiwiki的kmp内容然后发到小红书上"*

  <img src="docs/readme_img/image.png" alt="NeoFish 接管浏览器" width="800">
  
- *"帮我填写一份调查问卷..."*

  <img src="docs/readme_img/image_1.png" alt="NeoFish 接管浏览器" width="800">
  <img src="docs/readme_img/image_2.png" alt="NeoFish 接管浏览器" width="800">

- *"根据我的b站视频浏览记录分析我的喜好/作息/行为特点"*
  <img src="docs/readme_img/cd2b0c7107914acea3318078c12d83a4.jpg" alt="NeoFish 接管浏览器" width="800">
  <img src="docs/readme_img/52431414c1a8749059c44c68b32451a1.jpg" alt="NeoFish 接管浏览器" width="800">
  <img src="docs/readme_img/image_copy.png" alt="NeoFish 接管浏览器" width="800">

## 🤝 参与贡献

NeoFish 欢迎任何形式的贡献！无论你是想修复 Bug、添加新功能，还是改进文档，都非常欢迎提交 Pull Request。


## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=LangQi99/NeoFish&type=Date)](https://star-history.com/#LangQi99/NeoFish&Date)

---
<div align="center">
  <sub>Built with ❤️ by LangQi99 & the Open Source Community.</sub>
</div>