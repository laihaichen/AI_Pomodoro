// ── Wizard state ────────────────────────────────────────────────────────────
let wData = {};      // collected answers
let wSteps = [];     // built after hours is known
let wCurrent = 0;    // current step index

const MILESTONE_DEFS = [
    { range: "0 ~ 3小时", record: "第18条记录", hours: 3 },
    { range: "3 ~ 6小时", record: "第36条记录", hours: 6 },
    { range: "6 ~ 9小时", record: "第54条记录", hours: 9 },
    { range: "9 ~ 12小时", record: "第72条记录", hours: 12 },
];

// difficulty === "" 表示尚未选择（向导第一次构建时，不插入里程碑）
function buildSteps(hours, difficulty) {
    const steps = [];
    const needMilestones = difficulty && difficulty !== "探索者难度";
    const milestoneCount = MILESTONE_DEFS.filter(m => hours >= m.hours).length;

    // Step 0: hours
    steps.push({
        id: "hours", type: "number",
        title: "计划学习时长", heading: "今天计划学习几小时？",
        hint: "请输入 1 ~ 14 之间的整数。",
        min: 1, max: 14, placeholder: "例：10",
    });

    // Step 1: difficulty（移到最前，决定是否需要里程碑步骤）
    steps.push({
        id: "difficulty", type: "select",
        title: "游戏难度", heading: "请选择今天的游戏难度",
        hint: "硬核 / 平衡难度需要设置阶段性最低指标；探索者难度跳过此步骤。",
        options: ["硬核难度", "平衡难度", "探索者难度"],
    });

    // 里程碑步骤 — 每个 slot 合并为一页（任务文字 + 进度分母）
    if (needMilestones) {
        MILESTONE_DEFS.forEach((m, i) => {
            if (hours >= m.hours) {
                steps.push({
                    id: `milestone_${i}`,
                    denomId: `denom_${i}`,
                    type: "milestone_combo",
                    title: `阶段目标 ${i + 1} / ${milestoneCount}`,
                    heading: `${m.range} 阶段最低完成指标`,
                    hint: `${m.range}（${m.record}）达到时的任务確认。`,
                    placeholder: "例：完成 10 个简历投递",
                });
            }
        });
    }

    // 最长休息时间
    steps.push({
        id: "max_rest", type: "number",
        title: "休息设置", heading: "今天允许的最长休息时间",
        hint: "单位：分钟。",
        min: 1, max: 300, placeholder: "例：120",
    });

    // 故事主题
    steps.push({
        id: "theme", type: "textarea",
        title: "故事主题", heading: "今天的模拟人生故事主题",
        hint: "描述你希望 AI 为今天的学习旅程设定的故事背景与主角。",
        placeholder: '例：主人公是一个降生在KK诈骗园区的1岁婴儿，并且被一群诈骗犯养大。',
        required: false,
    });

    // 结果页
    steps.push({
        id: "result", type: "result",
        title: "初始化完成", heading: "你的初始化 Prompt 已生成",
        hint: "以下内容已自动写入 -max_rest_time 与 -difficulty。请将 Prompt 复制给 AI 聊天工具开始今天的学习。",
    });

    return steps;
}

// ── Modal open/close ────────────────────────────────────────────────────────
function openWizard() {
    wData = {};
    wCurrent = 0;
    wSteps = buildSteps(0, ""); // hours=0, difficulty="" → 无里程碑，直到两者都已知
    document.getElementById("wizard-overlay").classList.add("open");
    renderStep();
}
function closeWizard() {
    document.getElementById("wizard-overlay").classList.remove("open");
}
// 遮罩层点击不再关闭 Wizard（防止误触丢失进度）
// 关闭唯一方式：点击右上角 ✕ 按钮


// ── Render current step ──────────────────────────────────────────────────────
function renderProgress() {
    const prog = document.getElementById("wizard-progress");
    prog.innerHTML = wSteps.map((_, i) => {
        let cls = "wizard-dot";
        if (i < wCurrent) cls += " done";
        else if (i === wCurrent) cls += " active";
        return `<div class="${cls}"></div>`;
    }).join("");
}

function renderStep() {
    renderProgress();
    const step = wSteps[wCurrent];
    const body = document.getElementById("wizard-body");
    const isLast = wCurrent === wSteps.length - 1;
    const isFirst = wCurrent === 0;
    const savedVal = wData[step.id] ?? "";

    let inputHTML = "";
    if (step.type === "number") {
        inputHTML = `<input id="w-input" class="wizard-input" type="number"
      min="${step.min}" max="${step.max}" placeholder="${step.placeholder}"
      value="${savedVal}" />`;
    } else if (step.type === "text") {
        inputHTML = `<input id="w-input" class="wizard-input" type="text"
      placeholder="${step.placeholder}" value="${savedVal}" />`;
    } else if (step.type === "select") {
        const opts = step.options.map(o =>
            `<option value="${o}" ${o === savedVal ? "selected" : ""}>${o}</option>`
        ).join("");
        inputHTML = `<select id="w-input" class="wizard-select">${opts}</select>`;
    } else if (step.type === "textarea") {
        inputHTML = `<textarea id="w-input" class="wizard-textarea"
      placeholder="${step.placeholder}">${savedVal}</textarea>`;
    } else if (step.type === "milestone_combo") {
        const savedDenom = wData[step.denomId] ?? "";
        inputHTML = `
          <input id="w-input" class="wizard-input" type="text"
            placeholder="${step.placeholder}" value="${wData[step.id] ?? ''}" />
          <div style="margin-top:14px;display:flex;align-items:center;gap:10px;">
            <span style="font-size:12px;color:var(--dim);white-space:nowrap;">进度条分母：</span>
            <input id="w-denom" class="wizard-input" type="number" min="1" max="999"
              placeholder="例：10" value="${savedDenom}"
              style="width:120px;flex-shrink:0;"
              title="分母用于生成 -current-progress-indicator。如「完成10个简历投递」，分母为 10" />
            <span style="font-size:11px;color:var(--dim);">(完成条数)用于进度条</span>
          </div>`;
    } else if (step.type === "result") {
        inputHTML = `<textarea id="w-result" class="prompt-result" readonly></textarea>
      <div class="copy-success" id="copy-msg"></div>`;
    }

    const prevBtn = isFirst ? "" :
        `<button class="btn-prev" onclick="wizardPrev()">← 上一步</button>`;

    let nextBtn = "";
    if (step.type === "result") {
        nextBtn = `<button class="btn-copy" onclick="copyPrompt()">📋 复制 Prompt 并发送</button>`;
    } else {
        nextBtn = `<button class="btn-next" onclick="wizardNext()">
      ${isLast ? "完成" : "下一步 →"}</button>`;
    }

    body.innerHTML = `
    <div class="wizard-step-title">步骤 ${wCurrent + 1} / ${wSteps.length}</div>
    <div class="wizard-step-heading">${step.heading}</div>
    <div class="wizard-step-hint">${step.hint}</div>
    ${inputHTML}
    <div class="wizard-error" id="w-error"></div>
    <div class="wizard-btns">${prevBtn}${nextBtn}</div>
  `;

    // If result step, fetch prompt from backend
    if (step.type === "result") {
        submitSetup();
    }

    // Auto-focus input
    const inp = document.getElementById("w-input");
    if (inp) { inp.focus(); inp.addEventListener("keydown", e => { if (e.key === "Enter" && step.type !== "textarea") wizardNext(); }); }
}

// ── Validate and advance ────────────────────────────────────────────────────
function wizardNext() {
    const step = wSteps[wCurrent];
    const errEl = document.getElementById("w-error");
    errEl.textContent = "";

    if (step.type === "number") {
        const inp = document.getElementById("w-input");
        const val = parseInt(inp.value);
        if (isNaN(val) || val < step.min || val > step.max) {
            inp.classList.add("error");
            errEl.textContent = `请输入 ${step.min} ~ ${step.max} 之间的整数。`;
            return;
        }
        inp.classList.remove("error");
        wData[step.id] = val;
        // hours 确定后重建步骤（difficulty 此时可能已知或未知）
        if (step.id === "hours") {
            wSteps = buildSteps(val, wData.difficulty || "");
        }
    } else if (step.type === "text") {
        const inp = document.getElementById("w-input");
        const val = inp.value.trim();
        if (!val) {
            inp.classList.add("error");
            errEl.textContent = "请输入内容。";
            return;
        }
        inp.classList.remove("error");
        wData[step.id] = val;
    } else if (step.type === "select") {
        const val = document.getElementById("w-input").value;
        wData[step.id] = val;
        // difficulty 确定后重建步骤，动态决定是否插入里程碑步骤
        if (step.id === "difficulty") {
            wSteps = buildSteps(wData.hours || 0, val);
        }
    } else if (step.type === "milestone_combo") {
        const inp = document.getElementById("w-input");
        const denom = document.getElementById("w-denom");
        const val = inp.value.trim();
        if (!val) {
            inp.classList.add("error");
            errEl.textContent = "请输入任务内容。";
            return;
        }
        inp.classList.remove("error");
        wData[step.id] = val;
        wData[step.denomId] = parseInt(denom.value) || 0;
    } else if (step.type === "textarea") {
        wData[step.id] = (document.getElementById("w-input").value || "").trim();
    }

    wCurrent++;
    renderStep();
}

function wizardPrev() {
    wCurrent--;
    renderStep();
}

// ── Submit to backend ────────────────────────────────────────────────────────
function submitSetup() {

    const milestones = [];
    const denominators = [];
    wSteps.forEach(s => {
        if (s.id.startsWith("milestone_")) milestones.push(wData[s.id] || "");
        if (s.type === "milestone_combo") denominators.push(Number(wData[s.denomId]) || 0);

    });

    fetch("/api/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            hours: wData.hours,
            max_rest: wData.max_rest,
            difficulty: wData.difficulty,
            milestones: milestones,
            denominators: denominators,   // 新增：各阶段进度条分母
            theme: wData.theme || "",
        }),
    })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                document.getElementById("w-result").value = d.prompt;
            } else {
                document.getElementById("w-result").value = "生成失败：" + d.error;
            }
        })
        .catch(err => {
            document.getElementById("w-result").value = "网络错误：" + err;
        });
}


function copyPrompt() {
    const text = document.getElementById("w-result").value;
    navigator.clipboard.writeText(text).then(() => {
        const msg = document.getElementById("copy-msg");
        msg.textContent = "✅ 已复制！正在发送…";
        // 同时调用 stay.applescript（复用 divine-intervention 的 stay 路径）
        fetch("/api/stay-pomodoro", { method: "POST" })
            .then(r => r.json())
            .then(d => {
                msg.textContent = d.ok ? "✅ 已复制并发送！" : "✅ 已复制（发送失败）";
                setTimeout(() => { msg.textContent = ""; }, 3000);
            })
            .catch(() => {
                msg.textContent = "✅ 已复制（AppleScript 调用失败）";
                setTimeout(() => { msg.textContent = ""; }, 3000);
            });
    });
}

// ── Alfred triggers ──────────────────────────────────────────────────────────
function _alfredTrigger(btn, endpoint) {
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = "⏳ 发送中...";
    fetch(endpoint, { method: "POST" })
        .then(r => r.json())
        .then(d => {
            btn.innerHTML = d.ok ? "✅ 已发送！" : "❌ 失败：" + d.error;
            setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 2500);
        })
        .catch(() => {
            btn.innerHTML = "❌ 网络错误";
            setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 2500);
        });
}

function triggerNextPomodoro(btn) { _alfredTrigger(btn, "/api/next-pomodoro"); }
function triggerStayPomodoro(btn) { _alfredTrigger(btn, "/api/stay-pomodoro"); }
function triggerPause(btn) { _alfredTrigger(btn, "/api/pause"); }
function triggerContinue(btn) { _alfredTrigger(btn, "/api/continue"); }
function triggerGetCard(btn) { _alfredTrigger(btn, "/api/getcard"); }
function triggerUseCard(btn) { _alfredTrigger(btn, "/api/usecard"); }

function triggerReset(btn) {
    const confirmed = window.confirm("⚠️ 你确定要重置所有状态吗？\n\n这将清空所有番茄钟记录、时间戳、Snippets 数据，操作无法撤销。");
    if (!confirmed) return;

    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = "⏳ 重置中...";

    fetch("/api/reset", { method: "POST" })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                btn.innerHTML = "✅ 已重置";
                btn.style.color = "#4ade80";
                setTimeout(() => {
                    btn.innerHTML = orig;
                    btn.style.color = "#f87171";
                    btn.disabled = false;
                    refreshData();   // 立即刷新页面数据
                }, 2500);
            } else {
                btn.innerHTML = "❌ 失败";
                setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 3000);
            }
        })
        .catch(() => {
            btn.innerHTML = "❌ 网络错误";
            setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 3000);
        });
}

// ── Progress indicator stepper ───────────────────────────────────────────────
function progressStep(delta) {
    fetch("/api/progress-step", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delta: delta }),
    })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                const el = document.getElementById("val-current-progress-indicator");
                if (el) {
                    el.textContent = d.value;
                    el.style.color = d.value.startsWith("0/0") ? "var(--dim)"
                        : d.value.includes("已到达") ? "var(--green, #4ade80)"
                            : "var(--bright)";
                }
            }
        });
}

// ── Health stepper ───────────────────────────────────────────────────────────
function healthAdjust(delta) {
    fetch("/api/health-adjust", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ delta }),
    })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                const el = document.getElementById("val-health");
                if (el) {
                    el.textContent = d.health;
                    el.style.color = d.health >= 9 ? "var(--green, #4ade80)"
                        : d.health >= 6 ? "var(--yellow, #facc15)"
                            : "#f87171";
                }
            }
        });
}

function recordBossResult(result) {
    fetch("/api/boss-defeated", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result }),
    })
        .then(r => r.json())
        .then(d => {
            const statusEl = document.getElementById("val-boss-defeated");
            if (d.ok && statusEl) {
                statusEl.textContent = result === "true" ? "✅ 已录入：胜利" : "❌ 已录入：失败";
                statusEl.style.color = result === "true" ? "var(--green, #4ade80)" : "#f87171";
            }
        });
}

function declareVictory() {
    fetch("/api/declare-victory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
    })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                // 即时更新 UI，无需等待下一次轮询
                const ivEl = document.getElementById("val-is_victory");
                const ivCard = document.getElementById("card-is-victory");
                const ivBtn = document.getElementById("btn-declare-victory");
                if (ivEl) { ivEl.textContent = "已胜利"; ivEl.style.color = "var(--green, #4ade80)"; }
                if (ivCard) { ivCard.style.borderColor = "rgba(74,222,128,0.5)"; }
                if (ivBtn) { ivBtn.style.display = "none"; }
            }
        });
}

function declareDefeat() {
    const dfBtn = document.getElementById("btn-declare-defeat");
    if (dfBtn) { dfBtn.textContent = "保存中…"; dfBtn.disabled = true; }
    fetch("/api/declare-defeat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
    })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                if (dfBtn) { dfBtn.textContent = "✅ 已结算"; dfBtn.disabled = true; }
            } else {
                if (dfBtn) { dfBtn.textContent = "❌ 失败：" + (d.error || "未知"); dfBtn.disabled = false; }
            }
        })
        .catch(() => {
            if (dfBtn) { dfBtn.textContent = "📁 结算失败"; dfBtn.disabled = false; }
        });
}

// ── 神圣干预辅助填写器 ──────────────────────────────────────────────────────────
const DIVINE_RULE = `【关于神圣干预作用的游戏规则提示】

[神圣干预：玩家为角色X+1岁的事件预判栏目选择一个命运值区间（高度正面85~100、中等正面50~84、轻度正面1~49、轻度负面-1~-30、中等负面-31~-60、严重负面-61~-89），并为该区间填写一个自定义的事件描述；该描述将替换AI原本生成的该区间事件内容；实际触发仍需命运值落在玩家选择的区间；⚠️ 约束：不能在负面事件里写正面情节，或在正面事件里写负面情节]

神圣干预：
- 玩家选择一个命运值区间（对应JSON中的某个键，如 POS_HIGH、NEG_MID 等）
- 玩家提供该区间的自定义事件描述
- AI需检查玩家提供的事件描述是否符合区间性质（正面/负面），如不符则拒绝执行
- 在本轮输出末尾的 JSON 代码块中，将玩家自定义的事件文本写入对应的槽位
- 实际触发仍需角色X+1岁时的命运值落在玩家选择的区间`;

let _divineOld = "";

// ── 违规报告辅助填写器 ────────────────────────────────────────────────────────
let _violationExpected = "";   // 由 Agent 自动写入，非用户手填
let _violationTimer = null;  // 轮询 interval ID

function openViolationModal() {
    _violationExpected = "";
    _clearViolationTimer();
    document.getElementById("violation-step1").style.display = "";
    document.getElementById("violation-step2").style.display = "none";
    document.getElementById("violation-step3").style.display = "none";
    document.getElementById("violation-violations").value = "";
    const btn = document.getElementById("violation-send-btn");
    if (btn) { btn.textContent = "📋 复制并发送"; btn.disabled = false; }
    document.getElementById("violation-overlay").style.display = "flex";
}

function closeViolationModal() {
    _clearViolationTimer();
    document.getElementById("violation-overlay").style.display = "none";
}

function _clearViolationTimer() {
    if (_violationTimer !== null) { clearInterval(_violationTimer); _violationTimer = null; }
}

function violationNext() {
    const v = document.getElementById("violation-violations").value.trim();
    if (!v) { alert("请先填写违规描述"); return; }

    // 显示等待界面
    document.getElementById("violation-step1").style.display = "none";
    document.getElementById("violation-step2").style.display = "";
    document.getElementById("violation-wait-msg").textContent = "请等待游戏规则调查 Agent 返还结果…";

    // 后台启动：清空文件 → 写入违规 → 复制 prompts.txt → 触发 terminal.applescript
    fetch("/api/violation-start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ violations: v }),
    }).catch(() => {
        document.getElementById("violation-wait-msg").textContent = "❌ 启动失败，请关闭重试";
    });

    // 开始轮询（每 5 秒，最多 60 秒 = 12 次）
    let polls = 0;
    const MAX_POLLS = 12;
    _violationTimer = setInterval(() => {
        polls++;
        fetch("/api/violation-poll")
            .then(r => r.json())
            .then(d => {
                if (d.ready) {
                    _clearViolationTimer();
                    _violationExpected = d.expected || "";
                    // 进入 Step 3 预览
                    const violations = document.getElementById("violation-violations").value.trim();
                    document.getElementById("violation-preview-violations").textContent = violations;
                    document.getElementById("violation-preview-expected").textContent = _violationExpected;
                    document.getElementById("violation-step2").style.display = "none";
                    document.getElementById("violation-step3").style.display = "";
                } else if (polls >= MAX_POLLS) {
                    _clearViolationTimer();
                    document.getElementById("violation-wait-msg").textContent =
                        "⏱ 调查超时（1分钟未收到结果），已自动关闭";
                    setTimeout(() => closeViolationModal(), 2000);
                } else {
                    document.getElementById("violation-wait-msg").textContent =
                        `请等待游戏规则调查 Agent 返还结果… (${polls * 5}s / 60s)`;
                }
            })
            .catch(() => { /* 网络抖动忽略，继续轮询 */ });
    }, 5000);
}

function violationSend() {
    const violations = document.getElementById("violation-violations").value.trim();
    const btn = document.getElementById("violation-send-btn");
    btn.textContent = "发送中…";
    btn.disabled = true;
    fetch("/api/violation-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ violations, expected: _violationExpected }),
    })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                btn.textContent = "✅ 已复制并发送";
                setTimeout(() => closeViolationModal(), 1200);
            } else {
                btn.textContent = "❌ " + (d.error || "未知错误");
                btn.disabled = false;
            }
        })
        .catch(() => { btn.textContent = "📋 复制并发送"; btn.disabled = false; });
}


function openDivineModal() {
    // 重置到第一步
    document.getElementById("divine-step1").style.display = "";
    document.getElementById("divine-step2").style.display = "none";
    document.getElementById("divine-step3").style.display = "none";
    document.getElementById("divine-new-text").value = "";
    document.getElementById("divine-overlay").style.display = "flex";
}

function closeDivineModal() {
    document.getElementById("divine-overlay").style.display = "none";
}

function divineNext() {
    _divineOld = document.getElementById("divine-zone-select").value;
    document.getElementById("divine-zone-display").textContent = _divineOld;
    document.getElementById("divine-step1").style.display = "none";
    document.getElementById("divine-step2").style.display = "";
    document.getElementById("divine-new-text").focus();
}

function divineBack() {
    document.getElementById("divine-step2").style.display = "none";
    document.getElementById("divine-step1").style.display = "";
}

function divineBack2() {
    document.getElementById("divine-step3").style.display = "none";
    document.getElementById("divine-step2").style.display = "";
}

function divineGenerate() {
    const newStory = document.getElementById("divine-new-text").value.trim();
    if (!newStory) {
        alert("请先填写自定义事件描述");
        return;
    }
    const prompt = `使用[神圣干预]修改对应的区间\n\n被修改的区间：${_divineOld}\n\n修改为：${newStory}\n\n${DIVINE_RULE}`;
    document.getElementById("divine-prompt-output").value = prompt;
    document.getElementById("divine-step2").style.display = "none";
    document.getElementById("divine-step3").style.display = "";
}

function divineSend() {
    const prompt = document.getElementById("divine-prompt-output").value;
    const btn = document.getElementById("divine-send-btn");
    btn.textContent = "发送中…";
    btn.disabled = true;
    fetch("/api/divine-intervention", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
    })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                btn.textContent = "✅ 已复制并发送";
                setTimeout(() => closeDivineModal(), 1200);
            } else {
                btn.textContent = "❌ 失败：" + (d.error || "未知错误");
                btn.disabled = false;
            }
        })
        .catch(() => {
            btn.textContent = "📋 复制并发送";
            btn.disabled = false;
        });
}

// ── Dashboard data refresh ───────────────────────────────────────────────────

const REFRESH_MS = 1000;

let countdown = REFRESH_MS / 1000;
let currTsRaw = null; // Store ISO string for the timer

function setVal(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text ?? "—";
}

function applyClass(id, cls) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = el.className.replace(/\bval-\w+/g, "");
    if (cls) el.classList.add(cls);
}

function refreshData() {
    fetch("/api/state")
        .then(r => r.json())
        .then(d => {
            // timestamps
            currTsRaw = d.curr_ts_raw;
            setVal("val-curr_ts", d.curr_ts);
            setVal("val-prev_ts", d.prev_ts);
            setVal("val-first_ts", d.first_ts);

            // elapsed
            if (d.elapsed_minutes !== null && d.elapsed_minutes !== undefined) {
                const h = Math.floor(d.elapsed_minutes / 60);
                const m = Math.round(d.elapsed_minutes % 60);
                setVal("val-elapsed_minutes", h > 0 ? `${h}h ${m}m` : `${m} 分钟`);
            } else {
                setVal("val-elapsed_minutes", "—");
            }

            // prompt count — header badge
            setVal("val-current_prompt_count-header", d.current_prompt_count);
            // total count — header badge
            const tcHeaderEl = document.getElementById("val-total_count-header");
            if (tcHeaderEl) {
                const tc = d.total_count || "—";
                tcHeaderEl.textContent = tc;
                // 当前条数达到总条数时亮绿
                const cur = parseInt(d.current_prompt_count) || 0;
                const tot = parseInt(tc) || 0;
                tcHeaderEl.style.color = (tot > 0 && cur >= tot)
                    ? "var(--green, #4ade80)" : "var(--dim)";
            }

            // difficulty — now in 阶段性节点 section
            setVal("val-difficulty", d.difficulty);

            // total_score — 总积分（正绿负红）
            const tsEl = document.getElementById("val-total_score");
            if (tsEl) {
                const ts = parseInt(d.total_score) || 0;
                tsEl.textContent = ts >= 0 ? "+" + ts : String(ts);
                tsEl.style.color = ts > 0 ? "var(--green, #4ade80)"
                    : ts < 0 ? "#f87171"
                        : "var(--dim)";
            }

            // interval — color by >15
            const ivl = parseFloat(d.interval);
            setVal("val-interval", isNaN(ivl) ? d.interval : ivl.toFixed(1) + " 分钟");
            const ivlCard = document.querySelector(".card.accent-peach");
            if (!isNaN(ivl)) {
                applyClass("val-interval", ivl > 15 ? "val-red" : "val-green");
            }

            // fortune
            const fortune = d.fortunevalue || "";
            setVal("val-fortunevalue", fortune);
            applyClass("val-fortunevalue",
                fortune.includes("凶") ? "val-red" : fortune.includes("合规") ? "val-green" : null
            );

            // offset — color by >60
            const off = parseFloat(d.offset);
            setVal("val-offset", isNaN(off) ? d.offset : off.toFixed(1));
            applyClass("val-offset",
                isNaN(off) ? null : off > 60 ? "val-red" : off > 40 ? "val-yellow" : "val-green"
            );

            // rest
            setVal("val-max_rest_time", d.max_rest_time);
            setVal("val-total_rest_time", d.total_rest_time);

            // last rest action — colour by pause/continue state
            setVal("val-last_rest_action", d.last_rest_action);
            const restCard = document.getElementById("card-last-rest");
            if (restCard) {
                restCard.className = "card " + (d.last_rest_is_paused ? "accent-yellow" : "accent-green");
            }
            applyClass("val-last_rest_action", d.last_rest_is_paused ? "val-yellow" : "val-green");

            // penalty
            const hv = parseFloat(d.h_value);
            setVal("val-h_value", isNaN(hv) ? d.h_value : hv.toFixed(1) + " 分钟");
            applyClass("val-h_value", !isNaN(hv) && hv > 0 ? "val-red" : "val-green");

            setVal("val-overtime_penalty_random_num", d.overtime_penalty_random_num);
            applyClass("val-overtime_penalty_random_num",
                d.overtime_penalty_random_num === "0" ? "val-green" : "val-red"
            );


            // cards
            setVal("val-countcard", d.countcard);
            setVal("val-violationcount", d.violationcount);
            applyClass("val-violationcount",
                parseInt(d.violationcount) > 0 ? "val-red" : "val-green"
            );

            // milestones overview — 今日里程碑任务总览（非默认值的组）
            const msEl = document.getElementById("val-milestones-set");
            if (msEl) {
                const set = d.milestones_set || [];
                if (set.length === 0) {
                    msEl.textContent = "暂无已设置的阶段性任务";
                    msEl.style.color = "var(--dim)";
                } else {
                    msEl.innerHTML = set.map(m =>
                        `<span style="display:block;">
              <span style="color:var(--dim);font-size:10px;">${m.label}</span>
              &nbsp;${m.text}
            </span>`
                    ).join("");
                    msEl.style.color = "";
                }
            }

            // current milestone — 当前阶段任务
            const cmLabel = document.getElementById("val-current-milestone-label");
            const cmText = document.getElementById("val-current-milestone-text");
            const keyLabelMap = { hour3: "0~3小时", hour6: "3~6小时", hour9: "6~9小时", hour12: "9~12小时" };
            if (cmLabel && cmText) {
                if (d.current_milestone_key && d.current_milestone_text) {
                    cmLabel.textContent = keyLabelMap[d.current_milestone_key] || d.current_milestone_key;
                    cmText.textContent = d.current_milestone_text;
                    cmText.className = "card-value small val-green";
                } else {
                    cmLabel.textContent = "";
                    cmText.textContent = "番茄钟尚未开始";
                    cmText.className = "card-value small";
                    cmText.style.color = "var(--dim)";
                }
            }

            // progress indicator — 当前阶段性任务进度指示
            const piEl = document.getElementById("val-current-progress-indicator");
            if (piEl) {
                const pi = d.current_progress_indicator || "0/0 未到达进度";
                piEl.textContent = pi;
                piEl.style.color = pi.startsWith("0/0") ? "var(--dim)"
                    : pi.includes("已到达") ? "var(--green, #4ade80)"
                        : "var(--bright)";
            }


            // stage
            const stage = d.stage || "";
            const stageEl = document.getElementById("val-stage");
            if (stageEl) {
                stageEl.textContent = stage;
                stageEl.className = "card-value small";
                if (stage.includes("达到阶段性节点") && !stage.includes("没有")) {
                    stageEl.classList.add("val-yellow");
                } else if (stage.includes("没有")) {
                    stageEl.classList.add("stage-ok");
                } else if (stage.includes("不适用")) {
                    stageEl.classList.add("stage-na");
                }
            }

            // bossfight stage
            const bfs = d.bossfight_stage || "";
            const bfsEl = document.getElementById("val-bossfight_stage");
            const bfsCard = document.getElementById("card-bossfight");
            if (bfsEl) {
                bfsEl.textContent = bfs;
                bfsEl.className = "card-value small";
                bfsEl.style.color = "";
                if (bfsCard) bfsCard.style.borderColor = "";
                if (bfs.includes("已经达到boss战节点")) {
                    bfsEl.classList.add("val-red");
                    if (bfsCard) bfsCard.style.borderColor = "rgba(255,80,80,0.6)";
                } else if (bfs.includes("不适用")) {
                    bfsEl.style.color = "var(--dim)";
                } else if (bfs.includes("等待")) {
                    bfsEl.classList.add("val-green");
                }
            }

            // boss recording buttons — 仅硬核难度且当前是最后一条记录时显示
            const bossArea = document.getElementById("boss-record-area");
            const bossStatus = document.getElementById("val-boss-defeated");
            if (bossArea) {
                const isHardcore = (d.difficulty || "") === "硬核难度";
                const curCount = parseInt(d.current_prompt_count) || 0;
                const totalCount = parseInt(d.total_count) || 0;
                const isLastEntry = totalCount > 0 && curCount >= totalCount;
                bossArea.style.display = (isHardcore && isLastEntry) ? "block" : "none";
            }
            if (bossStatus) {
                const bd = d.boss_defeated || "none";
                bossStatus.textContent = bd === "true" ? "✅ 已录入：胜利"
                    : bd === "false" ? "❌ 已录入：失败"
                        : "尚未录入";
                bossStatus.style.color = bd === "true" ? "var(--green, #4ade80)"
                    : bd === "false" ? "#f87171"
                        : "var(--dim)";
            }

            // random num
            const rnEl = document.getElementById("val-random_num");
            if (rnEl) {
                const rn = d.random_num || "0";
                rnEl.textContent = rn;
                rnEl.style.color = rn === "0" ? "var(--dim)" : "var(--bright)";
            }

            // health
            const hEl = document.getElementById("val-health");
            if (hEl && d.health !== undefined) {
                hEl.textContent = d.health;
                hEl.style.color = d.health >= 9 ? "var(--green, #4ade80)"
                    : d.health >= 6 ? "var(--yellow, #facc15)"
                        : "#f87171";
            }

            // final fate
            const ffEl = document.getElementById("val-final_fate");
            if (ffEl) {
                if (d.final_fate !== null && d.final_fate !== undefined) {
                    ffEl.textContent = d.final_fate > 0 ? "+" + d.final_fate : String(d.final_fate);
                    ffEl.style.color = d.final_fate > 0 ? "var(--green, #4ade80)"
                        : d.final_fate < -60 ? "#f87171"
                            : "var(--bright)";
                } else {
                    ffEl.textContent = "—";
                    ffEl.style.color = "var(--dim)";
                }
            }

            // foretold — 本轮加载的预设事件区间
            const ftEl = document.getElementById("val-foretold");
            if (ftEl) {
                const ft = d.foretold || "—";
                ftEl.textContent = ft;
                ftEl.style.color = ft.startsWith("FAIL") ? "#f87171"
                    : ft.startsWith("NEG_HIGH") ? "#fb923c"
                        : ft.startsWith("NEG_MID") ? "#fbbf24"
                            : ft.startsWith("NEG_LOW") ? "var(--bright)"
                                : ft.startsWith("POS") ? "var(--green, #4ade80)"
                                    : "var(--dim)";
            }

            // is_victory — 游戏胜利状态
            const ivEl = document.getElementById("val-is_victory");
            const ivCard = document.getElementById("card-is-victory");
            const ivBtn = document.getElementById("btn-declare-victory");
            const dfBtn = document.getElementById("btn-declare-defeat");
            if (ivEl) {
                const iv = d.is_victory || "尚未胜利";
                ivEl.textContent = iv;
                const isFailed = iv.startsWith("已失败");
                const isVictory = iv.startsWith("已胜利");
                ivEl.style.color = isFailed ? "#f87171"
                    : isVictory ? "var(--green, #4ade80)"
                        : "var(--dim)";
                if (ivCard) {
                    ivCard.style.borderColor = isFailed ? "rgba(248,113,113,0.5)"
                        : isVictory ? "rgba(74,222,128,0.5)"
                            : "";
                }
                // 结算胜利按钮显示条件
                if (ivBtn) {
                    const cur = parseInt(d.current_prompt_count) || 0;
                    const tot = parseInt(d.total_count) || 0;
                    const isHardcore = (d.difficulty || "") === "硬核难度";
                    const bossOk = !isHardcore || (d.boss_defeated === "true");
                    const canSettle = !isFailed && !isVictory
                        && tot > 0 && cur >= tot
                        && bossOk;
                    ivBtn.style.display = canSettle ? "inline-block" : "none";
                }
                // 结算失败按钮：当前状态是已失败时显示
                if (dfBtn) {
                    dfBtn.style.display = isFailed ? "inline-block" : "none";
                }
            }

            // update time
            document.getElementById("last-update").textContent =
                new Date().toLocaleTimeString("zh-CN");
            countdown = REFRESH_MS / 1000;

        })
        .catch(err => {
            document.getElementById("last-update").textContent = "读取失败";
        });
}

// countdown display and tomato timer
setInterval(() => {
    countdown = Math.max(0, countdown - 1);

    if (currTsRaw) {
        const startDt = new Date(currTsRaw);
        const nowDt = new Date();
        const diffSecs = Math.floor((nowDt - startDt) / 1000);

        const timerEl = document.getElementById("tomato-timer");
        if (diffSecs >= 0 && timerEl) {
            if (diffSecs < 60) {
                timerEl.textContent = `${diffSecs}秒`;
            } else {
                const m = Math.floor(diffSecs / 60);
                const s = diffSecs % 60;
                timerEl.textContent = `${m}分钟${s}秒`;
            }
        }
    }
}, 1000);

// data refresh
refreshData();
setInterval(refreshData, REFRESH_MS);
