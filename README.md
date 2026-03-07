# 🍅 番茄钟学习管理系统

> 将番茄钟时间管理与文字 RPG 深度耦合的桌面学习辅助系统。每一次学习记录都会触发命运判定，驱动角色叙事，用低心智负担的游戏化激励解决长时间学习场景下的拖延与疲劳问题。

---

## ✨ 功能概览

| 模块 | 说明 |
|---|---|
| **番茄钟追踪** | 精确记录每条学习的时间戳、间隔、暂停/继续，自动计算进度偏移量 |
| **命运值系统** | 6 级命运值区间（高度正面 → 失败事件），基于概率、健康度衰减、超时惩罚的多维状态机 |
| **幸运系统** | 干预卡 / 宿命卡双卡储蓄机制，命运值 ≥ 85 时触发 |
| **里程碑任务** | 阶段性进度目标与难度分级（探索者 / 平衡 / 硬核） |
| **AI 伴侣** | 基于 Gemini API 的角色扮演对话，角色性格由 Markdown 档案定义，实时注入游戏状态上下文 |
| **实时仪表盘** | Web Dashboard（`localhost:5050`），轮询刷新 20+ 项状态指标 |
| **违规检测** | AI 审计系统，自动检测游戏规则违规并存档 |

---

## 🏗️ 技术架构

### 数据流管线

```
后端状态计算 → 持久化（JSON / SQLite） → prompt 模板展开 → 浏览器注入 → AI 对话会话
```

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3 / Flask |
| 前端 | 原生 JavaScript（无框架），HTML/CSS |
| 持久化 | 本地 JSON（standalone）/ SQLite + JSON 双写（Alfred 模式） |
| AI | Google Gemini API（`google-generativeai` SDK） |
| 桌面自动化 | macOS AppleScript（Chrome 注入） |
| AI 前端 | Google Chrome（Gemini Web / AI Studio） |

### 运行模式

系统支持两种运行模式，通过环境变量 `APP_MODE` 切换：

| | Standalone 模式 | Alfred 模式 |
|---|---|---|
| 环境变量 | `APP_MODE=standalone` | `APP_MODE=alfred`（默认） |
| 存储 | 本地 JSON（`data/snippets_local.json`） | Alfred SQLite + JSON 双写 |
| 触发方式 | Dashboard 按钮 → Python workflow 引擎 → 浏览器注入 | Dashboard 按钮 → Alfred trigger |
| 需要 Alfred | ❌ 不需要 | ✅ 需要安装 Alfred Powerpack |
| 推荐场景 | **新用户 / 无 Alfred** | 已有 Alfred 的用户 |

### 项目结构

```
Prompt/
├── config.py                          # 全局配置：路径、snippet 注册表
├── dashboard.py                       # Flask Web 仪表盘（主入口）
├── move.py                            # 番茄钟核心：提交记录、命运值计算、幸运系统
├── pause.py / continue.py             # 暂停 / 继续
├── update_h.py                        # 超时惩罚计算
├── update_stage.py                    # 阶段性里程碑推进
├── reset.py                           # 全量状态重置
├── prompt.md                          # 800+ 行游戏规则 system prompt
├── install.sh                         # 一键安装脚本
├── requirements.txt                   # Python 依赖
│
├── workflow/                          # Non-Alfred 版本编排引擎
│   ├── engine.py                      # 模板展开引擎（替代 Alfred snippet 展开）
│   ├── *_workflow.py                  # 7 个 workflow 编排脚本
│   ├── templates/                     # 7 个 prompt 模板
│   └── browser/                       # 浏览器驱动（AppleScript / 未来 Selenium）
│
├── mod/                               # 学习助手（伴侣）模块
│   ├── companions.py                  # 角色管理、对话管线
│   ├── skills.py                      # 技能定义
│   ├── conditions.py                  # 技能触发条件
│   └── effects.py                     # 技能效果
│
├── applescript/                       # macOS 自动化脚本（Alfred 模式使用）
├── templates/dashboard.html           # 仪表盘页面
├── static/                            # 前端资源
│   ├── dashboard.js / dashboard.css
│   └── companions/                    # 角色档案 + 头像
│
├── data/                              # 运行时数据
└── output/                            # 故事导出工具
```

---

## 📋 前置条件

### Standalone 模式（推荐新用户）

| 依赖 | 说明 |
|---|---|
| **macOS** | 需要 AppleScript 进行浏览器自动化 |
| **Python 3.10+** | 后端运行时 |
| **Google Chrome** | 自动化目标浏览器 |
| **Gemini API Key**（可选） | AI 伴侣功能需要，从 [Google AI Studio](https://aistudio.google.com/apikey) 获取 |

### Alfred 模式（进阶）

以上全部，加上：

| 依赖 | 说明 |
|---|---|
| **Alfred Powerpack** ⚠️ | **付费软件**（[alfredapp.com](https://www.alfredapp.com)），需购买 Powerpack  |

---

## 🚀 快速开始

### 1. 克隆 & 安装

```bash
git clone https://github.com/laihaichen/AI_Pomodoro.git
cd AI_Pomodoro
bash install.sh
```

安装脚本会自动：
- 检查 Python 3 环境
- 安装 Flask 和 google-generativeai
- 初始化 `data/` 目录和 `snippets_local.json`
- 创建 `api_config.json` 模板

### 2.（可选）配置 Gemini API

编辑 `api_config.json`，填入 API Key：

```json
{
    "gemini_api_key": "你的API密钥",
    "gemini_model": "gemini-3-flash-preview"
}
```

> 不配置 API Key 也可以使用核心功能（番茄钟、命运值系统），仅 AI 伴侣对话功能需要。

### 3. 配置 AI 对话页面

在 Google Chrome 中打开 [Gemini](https://gemini.google.com) 或 [Google AI Studio](https://aistudio.google.com)，将 `prompt.md` 的完整内容设置为 system prompt。

### 4. 启动

```bash
# Standalone 模式（无需 Alfred）
APP_MODE=standalone python3 dashboard.py

# Alfred 模式（需要 Alfred Powerpack）
python3 dashboard.py
```

打开浏览器访问 **http://localhost:5050** 🎉

---

## 📖 使用指南

### 基本循环

1. **开始学习** → 在 Dashboard 点击「番茄钟」按钮
2. **系统自动** → 计算命运值、组装 prompt、注入浏览器并发送给 AI
3. **AI 生成事件** → AI 根据命运值区间生成本轮故事事件
4. **查看面板** → Dashboard 自动刷新显示最新状态

### Dashboard 按钮

| 按钮 | 说明 |
|---|---|
| 番茄钟 Move | 提交一条学习记录 |
| 暂停 / 继续 | 暂停或恢复计时 |
| 获得一张宿命卡 | 命运值 ≥ 85 时可用，宿命卡 +1 |
| 使用一张宿命卡 | 选择命运值区间，强制触发指定事件 |
| 获得一张干预卡 | 命运值 ≥ 85 时可用，干预卡 +1 |
| 使用一张干预卡 | 选择区间 + 自定义事件描述 |
| 重置所有状态 | 清空全量数据（二次确认） |

### AI 伴侣

在 Dashboard 底部的聊天框中与 AI 角色对话。角色的性格、语气由 `static/companions/` 下的 Markdown 档案定义，系统会将当前游戏状态实时注入对话上下文。

---

## ⚙️ 配置说明

| 文件 | 用途 |
|---|---|
| `api_config.json` | Gemini API 密钥和模型名称 |
| `config.py` | 全局路径、snippet 注册表、默认值和面板标签 |
| `prompt.md` | 800+ 行的完整游戏规则，作为 AI 的 system prompt |
| `static/companions/*.md` | 角色档案（性格、背景、语气范例） |
| `mod/skills.py` | 技能定义（触发条件、效果、持续时间） |

---

## ⚠️ 已知限制 & 改进方向

| 限制 | 说明 | 状态 |
|---|---|---|
| ~~Snippet UID 硬编码~~ | ~~`config.py` 中所有 snippet 的 UUID 是写死的~~ | ✅ 已解决：启动时自动扫描 |
| ~~文件路径硬编码~~ | ~~`BASE` 路径固定~~ | ✅ 已解决：使用 `Path(__file__).parent` |
| ~~必须安装 Alfred~~ | ~~强依赖 Alfred Powerpack~~ | ✅ 已解决：Standalone 模式 |
| **仅支持 macOS** | 浏览器自动化依赖 AppleScript | 可通过 Selenium/Playwright 扩展 |
| **仅支持 Chrome** | AppleScript 中写死 Google Chrome | 可扩展支持其他浏览器 |

---

## 📄 License

MIT
