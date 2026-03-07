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
后端状态计算 → SQLite + JSON 双写持久化 → prompt 自动组装 → AppleScript 浏览器注入 → AI 对话会话
```

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3 / Flask |
| 前端 | 原生 JavaScript（无框架），HTML/CSS |
| 持久化 | SQLite（Alfred snippet DB）+ JSON 文件双写 |
| AI | Google Gemini API（`google-generativeai` SDK） |
| 桌面自动化 | macOS AppleScript、Alfred Powerpack（snippet + workflow） |
| AI 前端 | Google Chrome（Gemini Web / AI Studio） |

### 项目结构

```
Prompt/
├── config.py                          # 全局配置：路径、snippet UID 注册表
├── dashboard.py                       # Flask Web 仪表盘（主入口）
├── move.py                            # 番茄钟核心：提交记录、命运值计算、幸运系统
├── pause.py / continue.py             # 暂停 / 继续
├── update_h.py                        # 超时惩罚计算
├── update_stage.py                    # 阶段性里程碑推进
├── reset.py                           # 全量状态重置
├── prompt.md                          # 800+ 行游戏规则 system prompt
├── increment_card_snippet.py          # 宿命卡 +1
├── decrement_card_snippet.py          # 宿命卡 -1
├── increment_intervention_card_snippet.py  # 干预卡 +1
├── decrement_intervention_card_snippet.py  # 干预卡 -1
├── increment_violation_count_snippet.py    # 违规计数 +1
│
├── mod/                               # 学习助手（伴侣）模块
│   ├── companions.py                  # 角色管理、对话管线
│   ├── skills.py                      # 技能定义
│   ├── conditions.py                  # 技能触发条件
│   └── effects.py                     # 技能效果
│
├── applescript/                       # macOS 自动化脚本
│   ├── move.applescript               # 提交记录 → AI 发送
│   ├── stay.applescript               # 干预卡/违规报告 → AI 发送
│   ├── getcard.applescript            # 获得宿命卡 → AI 发送
│   ├── usecard.applescript            # 使用宿命卡 → AI 发送
│   ├── getinterventioncard.applescript # 获得干预卡 → AI 发送
│   ├── pause.applescript / continue.applescript
│   └── terminal.applescript
│
├── snippets_and_workflows/            # Alfred 导入包
│   ├── 学习时间追踪系统.alfredsnippets
│   └── 学习时间追踪系统.alfredworkflow
│
├── templates/dashboard.html           # 仪表盘页面
├── static/                            # 前端资源
│   ├── dashboard.js
│   └── dashboard.css
│
├── data/                              # 运行时数据（时间戳、JSON 状态等）
├── output/                            # 故事导出工具
├── Agent_Workspace/                   # 违规检测工作区
└── complaint_manager/                 # 投诉归档模块
```

---

## 📋 前置条件

| 依赖 | 说明 |
|---|---|
| **macOS** | 系统强依赖 AppleScript 进行桌面自动化，不支持 Windows/Linux |
| **Python 3.10+** | 后端运行时 |
| **Google Chrome** | AppleScript 自动操控的目标浏览器 |
| **Alfred Powerpack** ⚠️ | **付费软件**（[alfredapp.com](https://www.alfredapp.com)），必须购买 Powerpack 以启用 Snippet 和 Workflow 功能。系统使用 Alfred 的 SQLite 数据库作为核心持久化层 |
| **Gemini API Key** | 从 [Google AI Studio](https://aistudio.google.com/apikey) 获取 |

---

## 🚀 安装指南

### 1. 克隆仓库

```bash
git clone https://github.com/laihaichen/prompt.git
cd prompt
```

### 2. 安装 Python 依赖

```bash
pip install flask google-generativeai
```

### 3. 安装 Alfred & 导入配置

1. 安装 [Alfred](https://www.alfredapp.com) 并购买 **Powerpack**
2. 双击 `snippets_and_workflows/学习时间追踪系统.alfredsnippets` → 导入所有 snippet
3. 双击 `snippets_and_workflows/学习时间追踪系统.alfredworkflow` → 导入工作流

> [!IMPORTANT]
> 导入后，Alfred 会为每个 snippet 分配唯一的 UUID。当前版本的 `config.py` 中 snippet UID 是硬编码的（见下方 [已知限制](#-已知限制--改进方向)），你可能需要手动更新 `config.py` 中的 UID 使其与你本地 Alfred 数据库中的值匹配。
>
> 查看你本地的 snippet UID：
> ```bash
> ls ~/Library/Application\ Support/Alfred/Alfred.alfredpreferences/snippets/学习时间追踪系统/
> ```
> 每个 `.json` 文件名中包含 UID，格式如 `-snippetname [UUID].json`。

### 4. 配置 Gemini API

在项目根目录创建 `api_config.json`（已被 `.gitignore` 排除）：

```json
{
    "gemini_api_key": "你的API密钥",
    "gemini_model": "gemini-3-flash-preview"
}
```

### 5. 配置 AI 对话页面

在 Google Chrome 中打开以下任一 AI 聊天页面：
- [Gemini](https://gemini.google.com)（推荐使用 Gem，可预设 system prompt）
- [Google AI Studio](https://aistudio.google.com)

将 `prompt.md` 的完整内容设置为对话的 system prompt。

### 6. 启动仪表盘

```bash
python3 dashboard.py
```

打开浏览器访问 **http://localhost:5050**

---

## 📖 使用指南

### 基本循环

1. **开始学习** → 在 Dashboard 点击"番茄钟"按钮，系统记录开始时间
2. **提交记录** → 学习结束后，在 AI 对话中发送带有原始随机数的消息（由 Alfred snippet 自动组装）
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
| 使用一张干预卡 | 选择区间 + 自定义事件描述，写入 AI 预判 JSON |
| 重置所有状态 | 清空全量数据（二次确认） |

### AI 伴侣

在 Dashboard 底部的聊天框中与 AI 角色对话。角色的性格、语气和技能效果由 `static/companions/` 下的 Markdown 档案定义，系统会将当前游戏状态实时注入对话上下文。

---

## ⚙️ 配置说明

| 文件 | 用途 |
|---|---|
| `api_config.json` | Gemini API 密钥和模型名称 |
| `config.py` | 全局路径、snippet UID 注册表、默认值和面板标签 |
| `prompt.md` | 800+ 行的完整游戏规则，作为 AI 的 system prompt |
| `static/companions/*.md` | 角色档案（性格、背景、语气范例） |
| `mod/skills.py` | 技能定义（触发条件、效果、持续时间） |

---

## ⚠️ 已知限制 & 改进方向

> [!WARNING]
> 当前版本包含多处硬编码，移植到其他机器需要手动调整。

| 限制 | 说明 | 改进方向 |
|---|---|---|
| **Snippet UID 硬编码** | `config.py` 中所有 snippet 的 UUID 是写死的 | 应在安装时动态扫描 Alfred DB 读取 |
| **文件路径硬编码** | `BASE` 路径固定为 `/Users/haichenlai/Desktop/Prompt` | 应使用 `Path(__file__).parent` 动态获取 |
| **仅支持 macOS** | 强依赖 AppleScript + Alfred Powerpack | 可考虑抽象自动化层以支持跨平台 |
| **仅支持 Chrome** | AppleScript 中 `tell application "Google Chrome"` 写死 | 可扩展支持其他浏览器 |
| **Alfred 为付费依赖** | 必须购买 Powerpack（约 $34） | 可考虑替代持久化方案 |

---

## 📄 License

MIT
