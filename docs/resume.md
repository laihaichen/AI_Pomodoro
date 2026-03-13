# 项目介绍 — 简历用

## 版本 A：适合投递给游戏公司

**智能番茄钟 × 文字 RPG 系统** — 全栈独立项目 | [GitHub](https://github.com/laihaichen/AI_Pomodoro)

设计并独立开发了一套将番茄钟时间管理与文字 RPG 深度耦合的桌面应用系统。玩家的每次学习记录触发一次命运判定（基于概率函数、状态衰减惩罚、超时检测等多维状态机），驱动模拟人生式的角色叙事。系统包含完整的游戏设计：命运值区间映射事件体系、幸运系统（双卡储蓄机制，玩家可干预未来事件或强制触发指定事件）、阶段性里程碑与难度分级，以及基于 Gemini API 的 AI NPC 助手系统——支持多轮上下文对话，角色性格由 Markdown 档案驱动，实时注入 20+ 项游戏状态作为 prompt 上下文。助手系统采用模块化架构，以 Condition + Effect 策略模式定义技能，支持三维限制体系（全局触发次数、冷却回合、效果持续时间），并实现了运行时深拷贝机制（动态克隆相邻角色的完整技能树）。系统还内置了独立的多智能体治理机制：3 名 AI 助手作为陪审员并行投票评审玩家学习成果，配合在场助手自动生成角色化辩护词，支持悬置追问轮次，审议结果直接管控核心状态指标与学习进度，形成了多 Agent 协作的学习评估闭环。架构采用**三运行模式渐进解耦设计**（Alfred工作流模式/无Alfred工作流模式/ 全沙盒自治），其中沙盒模式内置完整的 Gemini 多轮对话引擎，将 AI 主持人嵌入 Web 端，实现 system prompt 热加载、对话历史持久化与 Markdown 实时渲染的自治聊天系统，消除外部平台依赖。技术实现覆盖了 **后端状态计算 → 本地双写持久化 → prompt 自动组装 → AI 对话引擎集成** 的全链路自动化管线，使用 Python/Flask、原生 JavaScript 实时仪表盘（含内置聊天 UI）、SQLite、macOS 原生脚本自动化，以及 800+ 行游戏规则文档作为 AI system prompt 的工程化管理。

## 版本 B：适合投递给非游戏企业

**智能番茄钟学习管理系统** — 全栈独立项目 | [GitHub](https://github.com/laihaichen/AI_Pomodoro)

独立设计并开发了一套基于 Flask 的实时学习追踪系统，通过低心智负担的轻量化激励机制解决长时间学习场景下的拖延与疲劳问题。系统核心是一个多维状态引擎：实时计算时间偏移、状态衰减惩罚、阶段性里程碑校验等 20+ 项运行时指标，并通过轮询将全量状态同步至前端实时仪表盘。集成 Google Gemini API 实现 AI 对话助手，支持多轮上下文管理（含 token 预算控制与历史截断）、角色化 system prompt 工程、以及运行时状态的实时上下文注入。系统还内置了分布式 AI 评审管线：3 个独立 AI Agent 并行评估学习成果，支持悬置追问轮次与自动辩护生成，评审结果直接管控状态引擎的核心指标与学习进度，形成多 Agent 协作的学习评估闭环。系统通过本地持久化引擎（SQLite + JSON 双写一致性）管理全量运行时状态，实现后端状态计算 → 本地持久化 → prompt 组装 → AI 对话引擎集成的全链路自动化管线。架构采用**三运行模式渐进解耦设计**（Alfred工作流模式/无Alfred工作流模式/ 全沙盒自治），沙盒模式将 Gemini 多轮对话引擎完整内置于 Web 端，实现 system prompt 热加载、对话历史持久化与 Markdown 实时渲染，消除外部平台依赖，达成**零外部依赖的全栈自闭环**。AI 对话目标 URL 可通过 Dashboard 动态配置，并提供 prompt 历史备份与一键恢复机制。前端使用原生 JavaScript 构建，无框架依赖，包含实时仪表盘、内置 AI 聊天界面（Markdown 渲染 + 语法高亮）、多步骤 Modal 交互和响应式布局。

---

## LaTeX 版本 B：适合投递给非游戏企业

```latex
\cventry{2025.12 -- 至今}
{智能番茄钟学习管理系统}
{全栈独立项目 \normalfont{\textbar} \href{https://github.com/laihaichen/AI_Pomodoro}{GitHub链接} \newline Python / Flask / JavaScript / SQLite}
{}
{}
{
\begin{itemize}
    \item \textbf{项目概述}：独立设计并开发基于 Flask 的实时学习追踪系统，通过轻量化激励机制解决长时间学习场景下的拖延与疲劳问题。
    \item \textbf{多维状态引擎与前端渲染}：核心构建多维状态引擎，实时计算时间偏移、健康度衰减、阶段性里程碑校验等 20+ 项运行时指标，并通过轮询同步至原生 JavaScript 构建的无框架依赖仪表盘（含实时图表、内置 AI 聊天界面与多步骤 Modal 交互）。
    \item \textbf{大模型协同 (AI Integration)}：集成 Google Gemini API 实现智能对话助手，支持多轮上下文管理（含 token 预算控制与历史截断）、角色化 System Prompt 工程及运行时状态实时注入。内置分布式 AI 评审管线：3 个独立 Agent 并行评估学习成果，支持悬置追问与自动辩护生成，形成多 Agent 协作的学习评估闭环。
    \item \textbf{全链路自动化管线}：采用 SQLite + JSON 双写一致性管理状态，实现"后端计算 $\rightarrow$ 本地持久化 $\rightarrow$ Prompt 组装 $\rightarrow$ AI 对话引擎集成"的全链路闭环。
    \item \textbf{三模式架构与跨平台}：采用三运行模式渐进解耦设计（Alfred 工作流 / 无 Alfred 独立部署 / 全沙盒自治），沙盒模式将 Gemini 多轮对话引擎完整内置于 Web 端，实现 System Prompt 热加载、对话历史持久化与 Markdown 实时渲染（含语法高亮），达成零外部依赖的全栈自闭环。
\end{itemize}
}
```

## LaTeX 版本 A：适合投递给游戏企业

```latex3
\cventry{2025.12 -- 至今}
{智能番茄钟 $\times$ 文字 RPG 系统}
{全栈独立项目 \normalfont{\textbar} \href{https://github.com/laihaichen/AI_Pomodoro}{GitHub链接} \newline Python / Flask / JavaScript / SQLite}
{}
{}
{
\begin{itemize}
    \item \textbf{系统与玩法设计}：独立开发番茄钟与文字 RPG 深度耦合的桌面应用。每次学习记录触发命运判定（概率函数、状态衰减、超时惩罚等多维状态机），驱动模拟人生式叙事。包含命运值事件映射体系、干预卡/宿命卡双卡储蓄机制、阶段性里程碑与难度分级，以及 800+ 行游戏规则文档驱动的 AI System Prompt 工程化管理。
    \item \textbf{Mod 化架构与 AI 系统}：助手系统以 Condition + Effect 策略模式定义技能，支持三维限制体系（触发次数/冷却/持续时间）与运行时深拷贝（动态克隆相邻角色技能树）。AI NPC 由 Markdown 角色档案 + 20+ 项实时游戏状态注入驱动多轮对话；3 名 AI 陪审员并行投票评审学习成果，支持角色化辩护与悬置追问。
    \item \textbf{全链路管线与三模式架构}：覆盖\textbf{后端状态计算 $\rightarrow$ 双写持久化 $\rightarrow$ Prompt 组装 $\rightarrow$ AI 引擎集成}的自动化闭环。采用三模式渐进解耦（Alfred 工作流 / 独立部署 / 全沙盒自治），沙盒模式内置 Gemini 对话引擎与 Markdown 实时渲染，实现零外部依赖的 Web 端自治聊天系统。
\end{itemize}
}
```
