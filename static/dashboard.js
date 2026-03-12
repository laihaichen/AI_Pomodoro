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
                    juryId: `jury_${i}`,
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
        hint: "请将 Prompt 复制给 AI 聊天工具开始今天的学习。",
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

// ── AI 对话 URL 编辑器 ──────────────────────────────────────────────────────
function openTargetUrlEditor() {
    fetch("/api/target-urls")
        .then(r => r.json())
        .then(d => {
            document.getElementById("target-url-input").value = (d.urls || []).join("\n");
            document.getElementById("url-editor-overlay").classList.add("open");
        })
        .catch(() => {
            document.getElementById("target-url-input").value = "gemini.google.com";
            document.getElementById("url-editor-overlay").classList.add("open");
        });
}
function closeTargetUrlEditor() {
    document.getElementById("url-editor-overlay").classList.remove("open");
}
function saveTargetUrls() {
    const btn = document.getElementById("url-save-btn");
    const text = document.getElementById("target-url-input").value.trim();
    const urls = text.split("\n").map(s => s.trim()).filter(Boolean);
    if (!urls.length) { alert("请至少输入一个 URL"); return; }
    btn.textContent = "⏳ 保存中...";
    btn.disabled = true;
    fetch("/api/target-urls", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls })
    })
        .then(r => r.json())
        .then(d => {
            btn.textContent = d.ok ? "✅ 已保存" : "❌ " + d.error;
            setTimeout(() => { btn.textContent = "保存"; btn.disabled = false; }, 2000);
            if (d.ok) setTimeout(closeTargetUrlEditor, 1500);
        })
        .catch(() => {
            btn.textContent = "❌ 网络错误";
            setTimeout(() => { btn.textContent = "保存"; btn.disabled = false; }, 2000);
        });
}


// ── 历史备份查看器 ──────────────────────────────────────────────────────────
function openBackupViewer() {
    const list = document.getElementById("backup-list");
    list.innerHTML = '<p style="color:var(--dim);text-align:center;">加载中...</p>';
    document.getElementById("backup-viewer-overlay").classList.add("open");
    fetch("/api/prompt-backup")
        .then(r => r.json())
        .then(d => {
            const backups = d.backups || [];
            if (!backups.length) {
                list.innerHTML = '<p style="color:var(--dim);text-align:center;">暂无备份记录</p>';
                return;
            }
            const typeLabels = { move: "🔄 推进", stay: "💬 消息", divine: "⚡ 神圣干预", violation: "⚠️ 违规通告", init: "🚀 初始化", unknown: "📝 其他" };
            list.innerHTML = backups.map((b, i) => {
                const text = b.prompt_text || b.text || "";
                const preview = text.substring(0, 80).replace(/\n/g, " ") + (text.length > 80 ? "..." : "");
                const tag = typeLabels[b.type] || typeLabels.unknown;
                const s = b.state || {};
                const stateInfo = s.final_fate !== undefined
                    ? `命运值 ${s.final_fate} · HP ${s.health} · 分 ${s.total_score}`
                    : "";
                return `<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;">
                    <div style="flex:1;min-width:0;">
                        <div style="font-size:12px;font-weight:600;margin-bottom:4px;display:flex;gap:8px;align-items:center;">
                            <span style="color:var(--text);">🕐 ${b.time}</span>
                            <span style="font-size:10px;padding:2px 6px;background:rgba(255,255,255,0.06);border-radius:4px;">${tag}</span>
                            ${stateInfo ? `<span style="font-size:10px;color:var(--dim);">${stateInfo}</span>` : ""}
                        </div>
                        <div style="font-size:12px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${preview}</div>
                    </div>
                    <button onclick="copyBackup(${i})" id="backup-copy-${i}"
                        style="flex-shrink:0;padding:6px 14px;background:var(--border);color:var(--text);border:1px solid #3a3a3a;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;">复制</button>
                </div>`;
            }).join("");
            window._backupData = backups;
        })
        .catch(() => {
            list.innerHTML = '<p style="color:var(--dim);text-align:center;">加载失败</p>';
        });
}
function closeBackupViewer() {
    document.getElementById("backup-viewer-overlay").classList.remove("open");
}
function copyBackup(idx) {
    const b = window._backupData[idx];
    if (!b) return;
    const text = b.prompt_text || b.text || "";
    const btn = document.getElementById(`backup-copy-${idx}`);
    navigator.clipboard.writeText(text).then(() => {
        btn.textContent = "✅ 已复制";
        setTimeout(() => { btn.textContent = "复制"; }, 2000);
    }).catch(() => {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        btn.textContent = "✅ 已复制";
        setTimeout(() => { btn.textContent = "复制"; }, 2000);
    });
}


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
        const juryChecked = wData[step.juryId] ? "checked" : "";
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
          </div>
          <label style="margin-top:12px;display:flex;align-items:center;gap:6px;cursor:pointer;">
            <input type="checkbox" id="w-jury" ${juryChecked}
              style="accent-color:var(--bright);cursor:pointer;width:16px;height:16px;" />
            <span style="font-size:12px;color:var(--bright);font-weight:700;">⚖️ 经过陪审团系统</span>
          </label>`;
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
        wData[step.juryId] = document.getElementById("w-jury")?.checked || false;
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
    const juryFlags = [];
    wSteps.forEach(s => {
        if (s.id.startsWith("milestone_")) milestones.push(wData[s.id] || "");
        if (s.type === "milestone_combo") {
            denominators.push(Number(wData[s.denomId]) || 0);
            juryFlags.push(!!wData[s.juryId]);
        }
    });

    fetch("/api/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            hours: wData.hours,
            max_rest: wData.max_rest,
            difficulty: wData.difficulty,
            milestones: milestones,
            denominators: denominators,
            jury_flags: juryFlags,
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
    const el = document.getElementById("w-result");
    if (!el) return;
    const text = el.value;
    const msg = document.getElementById("copy-msg");

    function afterCopy() {
        if (msg) msg.textContent = "✅ 已复制！正在发送…";
        fetch("/api/stay-pomodoro", { method: "POST" })
            .then(r => r.json())
            .then(d => {
                if (msg) msg.textContent = d.ok ? "✅ 已复制并发送！" : "✅ 已复制（发送失败）";
                setTimeout(() => { if (msg) msg.textContent = ""; }, 3000);
            })
            .catch(() => {
                if (msg) msg.textContent = "✅ 已复制（AppleScript 调用失败）";
                setTimeout(() => { if (msg) msg.textContent = ""; }, 3000);
            });
    }

    // 首选 Clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(afterCopy).catch(() => {
            // fallback: execCommand
            el.select();
            document.execCommand("copy");
            afterCopy();
        });
    } else {
        // 极端 fallback
        el.select();
        document.execCommand("copy");
        afterCopy();
    }
}

// ── Alfred triggers ──────────────────────────────────────────────────────────
function _alfredTrigger(btn, endpoint, onSuccess) {
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = "⏳ 发送中...";
    fetch(endpoint, { method: "POST" })
        .then(r => r.json())
        .then(d => {
            btn.innerHTML = d.ok ? "✅ 完成" : "❌ 失败：" + d.error;
            if (d.ok && typeof onSuccess === "function") onSuccess();
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
function triggerGetCard(btn) {
    _alfredTrigger(btn, "/api/getcard", function () {
        // 领卡后清除幸运奖励
        fetch("/api/claim-lucky-card", { method: "POST" });
    });
}
function triggerGetInterventionCard(btn) {
    _alfredTrigger(btn, "/api/getinterventioncard", function () {
        fetch("/api/claim-lucky-card", { method: "POST" });
    });
}

function triggerReset(btn) {
    const noArchive = document.getElementById("chk-no-archive")?.checked;
    const msg = noArchive
        ? "⚠️ 你确定要重置所有状态吗？\n\n⚡ 已勾选「不保存」：将直接清空，不归档任何数据。"
        : "⚠️ 你确定要重置所有状态吗？\n\n这将清空所有番茄钟记录、时间戳、Snippets 数据，操作无法撤销。";
    if (!window.confirm(msg)) return;

    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = "⏳ 重置中...";

    fetch("/api/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ no_archive: !!noArchive })
    })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                btn.innerHTML = "✅ 已重置";
                btn.style.color = "#4ade80";
                setTimeout(() => {
                    btn.innerHTML = orig;
                    btn.style.color = "#f87171";
                    btn.disabled = false;
                    refreshData();
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

// ── 违规报告辅助填写器 ────────────────────────────────────────────────────────
let _violationExpected = "";
let _violationTimer = null;

function openViolationModal() {
    _violationExpected = "";
    _clearViolationTimer();
    document.getElementById("violation-step0").style.display = "";
    document.getElementById("violation-step1").style.display = "none";
    document.getElementById("violation-step2").style.display = "none";
    document.getElementById("violation-step3").style.display = "none";
    document.getElementById("violation-source").value = "";
    document.getElementById("violation-violations").value = "";
    const btn = document.getElementById("violation-send-btn");
    if (btn) { btn.textContent = "📋 复制并发送"; btn.disabled = false; }
    document.getElementById("violation-overlay").style.display = "flex";
}

function violationNextStep0() {
    const src = document.getElementById("violation-source").value.trim();
    if (!src) { alert("请先粘贴 AI 输出中违规的那段话"); return; }
    document.getElementById("violation-step0").style.display = "none";
    document.getElementById("violation-step1").style.display = "";
}

function violationBackToStep0() {
    document.getElementById("violation-step1").style.display = "none";
    document.getElementById("violation-step0").style.display = "";
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
    const src = document.getElementById("violation-source").value.trim();

    document.getElementById("violation-step1").style.display = "none";
    document.getElementById("violation-step2").style.display = "";
    document.getElementById("violation-wait-msg").textContent = "请等待游戏规则调查 Agent 返还结果…";

    fetch("/api/violation-start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ violations: v, source: src }),
    }).catch(() => {
        document.getElementById("violation-wait-msg").textContent = "❌ 启动失败，请关闭重试";
    });

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
                    const violations = document.getElementById("violation-violations").value.trim();
                    const source = document.getElementById("violation-source").value.trim();
                    document.getElementById("violation-preview-source").textContent = source.length > 120 ? source.slice(0, 120) + "…" : source;
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
    const source = document.getElementById("violation-source").value.trim();
    const btn = document.getElementById("violation-send-btn");
    btn.textContent = "发送中…";
    btn.disabled = true;
    fetch("/api/violation-report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ violations, source, expected: _violationExpected }),
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

            // fortune (is_time_within_limit)
            const fortune = d.is_time_within_limit || "";
            setVal("val-is_time_within_limit", fortune);
            applyClass("val-is_time_within_limit",
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
            setVal("val-countinterventioncard", d.countinterventioncard);
            setVal("val-violationcount", d.violationcount);
            applyClass("val-violationcount",
                parseInt(d.violationcount) > 0 ? "val-red" : "val-green"
            );

            // 吉凶结果
            const fam = d.fortune_and_misfortune || "";
            setVal("val-fortune-and-misfortune", fam);
            applyClass("val-fortune-and-misfortune",
                fam.includes("凶") ? "val-red" : fam.includes("吉") ? "val-green" : null
            );

            // 是否触发幸运系统
            const rewardEl = document.getElementById("val-is_eligible_for_reward");
            if (rewardEl) {
                const reward = d.is_eligible_for_reward || "—";
                const isTriggered = reward.includes("幸运系统已触发");
                const canExchange = reward.includes("[SCORE_EXCHANGE_AVAILABLE]");

                // 显示文本（去掉内部标记）
                const displayText = reward.replace("[SCORE_EXCHANGE_AVAILABLE]", "").trim();
                rewardEl.textContent = displayText;
                rewardEl.style.color = isTriggered ? "#f5c842" : "var(--dim)";
                rewardEl.style.fontWeight = isTriggered ? "700" : "600";

                // 换分按钮
                const btnId = "btn-claim-lucky-score";
                let existingBtn = document.getElementById(btnId);
                if (canExchange && !existingBtn) {
                    const btn = document.createElement("button");
                    btn.id = btnId;
                    btn.textContent = "💰 换取5积分（不拿卡）";
                    btn.style.cssText = "margin-top:8px;padding:6px 14px;border:1px solid #f5c842;border-radius:6px;background:rgba(245,200,66,0.15);color:#f5c842;cursor:pointer;font-size:0.85rem;font-weight:600;display:block;";
                    btn.addEventListener("click", () => {
                        btn.disabled = true;
                        btn.textContent = "⏳ 兑换中...";
                        fetch("/api/claim-lucky-score", { method: "POST" })
                            .then(r => r.json())
                            .then(res => {
                                if (res.ok) {
                                    btn.textContent = "✅ 已兑换 +5 积分";
                                    btn.style.borderColor = "#4ade80";
                                    btn.style.color = "#4ade80";
                                    setTimeout(() => btn.remove(), 2500);
                                } else {
                                    btn.textContent = "❌ " + (res.error || "失败");
                                    btn.disabled = false;
                                }
                            })
                            .catch(() => { btn.textContent = "❌ 网络错误"; btn.disabled = false; });
                    });
                    rewardEl.parentNode.appendChild(btn);
                } else if (!canExchange && existingBtn) {
                    existingBtn.remove();
                }

                // 获得卡按钮：仅在幸运系统触发且未被消耗时可点
                const btnCard = document.getElementById("btn-get-card");
                const btnICard = document.getElementById("btn-get-icard");
                const scoreClaimBtn = document.getElementById(btnId);
                const luckyClaimable = isTriggered && !scoreClaimBtn?.disabled;
                if (btnCard) {
                    btnCard.disabled = !luckyClaimable;
                    btnCard.style.opacity = luckyClaimable ? "1" : "0.35";
                    btnCard.style.cursor = luckyClaimable ? "pointer" : "not-allowed";
                }
                if (btnICard) {
                    btnICard.disabled = !luckyClaimable;
                    btnICard.style.opacity = luckyClaimable ? "1" : "0.35";
                    btnICard.style.cursor = luckyClaimable ? "pointer" : "not-allowed";
                }
            }

            // current clipboard (当前学习正文) — 纯文本显示
            const clipEl = document.getElementById("val-current-clipboard");
            if (clipEl && d.current_clipboard) {
                const raw = d.current_clipboard;
                if (clipEl.dataset.raw !== raw) {
                    clipEl.dataset.raw = raw;
                    clipEl.textContent = raw;
                }
            }

            // milestones overview — 今日里程碑任务总览（非默认值的组）
            const msEl = document.getElementById("val-milestones-set");
            if (msEl) {
                const set = d.milestones_set || [];
                let newHTML;
                if (set.length === 0) {
                    newHTML = "暂无已设置的阶段性任务";
                } else {
                    newHTML = set.map(m =>
                        `<span style="display:block;">
              <span style="color:var(--dim);font-size:10px;">${m.label}</span>
              &nbsp;${m.text}
            </span>`
                    ).join("");
                }
                // 仅在内容变化时更新 DOM，避免破坏用户文本选区
                if (msEl.innerHTML !== newHTML) {
                    msEl.innerHTML = newHTML;
                    msEl.style.color = set.length === 0 ? "var(--dim)" : "";
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
                const pi = d.current_progress_indicator || "0/1 未到达进度";
                piEl.textContent = pi;
                piEl.style.color = pi.startsWith("0/0") ? "var(--dim)"
                    : pi.includes("已到达") ? "var(--green, #4ade80)"
                        : "var(--bright)";
            }
            // 陪审团管控模式：隐藏手动按钮，显示标签
            const manualBtns = document.getElementById("progress-manual-btns");
            const juryLabel = document.getElementById("progress-jury-label");
            if (manualBtns && juryLabel) {
                if (d.current_milestone_jury) {
                    manualBtns.style.display = "none";
                    juryLabel.style.display = "inline";
                } else {
                    manualBtns.style.display = "flex";
                    juryLabel.style.display = "none";
                }
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

            // 今日故事主题
            const themeEl = document.getElementById("val-theme");
            const themeCard = document.getElementById("card-theme");
            const themeVal = (d.theme || "").trim();
            const themeNew = themeVal || "—";
            if (themeEl && themeEl.textContent !== themeNew) themeEl.textContent = themeNew;
            if (themeCard) themeCard.style.display = themeVal ? "" : "none";

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

// ── Companion Slot System ─────────────────────────────────────────────────────

function renderSlot(comp, locked) {
    const slot = document.createElement("div");
    slot.className = "companion-slot loaded" + (locked ? " locked-slot" : "");

    // header: name + remove button
    const hdr = document.createElement("div");
    hdr.className = "companion-slot-header";
    hdr.innerHTML = `
        <span class="companion-slot-name">${comp.name}</span>
        <button class="companion-remove-btn"
                ${locked ? "disabled" : ""}
                onclick="removeCompanion('${comp.name}')">✕</button>
    `;
    slot.appendChild(hdr);

    // avatar row: avatar + chat button
    const avatarRow = document.createElement("div");
    avatarRow.className = "companion-avatar-row";

    const av = document.createElement("div");
    av.className = "companion-avatar-area";
    if (comp.avatar_url) {
        av.innerHTML = `<img src="${comp.avatar_url}" alt="${comp.name}">`;
    } else {
        av.textContent = "🤖";
    }
    avatarRow.appendChild(av);

    const chatBtn = document.createElement("button");
    chatBtn.className = "companion-chat-btn";
    chatBtn.textContent = "💬";
    chatBtn.title = `与${comp.name}对话`;
    chatBtn.onclick = () => openChatModal(comp.name, comp.last_reply || "");
    avatarRow.appendChild(chatBtn);

    slot.appendChild(avatarRow);

    // last reply bubble (if exists)
    if (comp.last_reply) {
        const bubble = document.createElement("div");
        bubble.className = "companion-reply-bubble";
        bubble.textContent = comp.last_reply;
        slot.appendChild(bubble);
    }

    // skills
    const skillsDiv = document.createElement("div");
    skillsDiv.className = "companion-skills";
    (comp.skills || []).forEach(sk => {
        const wrapper = document.createElement("div");
        wrapper.className = "skill-wrapper";

        if (sk.type === "passive") {
            const tag = document.createElement("div");
            tag.className = "skill-tag";
            tag.textContent = sk.name;
            wrapper.appendChild(tag);
        } else {
            const btn = document.createElement("button");
            btn.className = "skill-btn";
            const disabled = sk.status !== "available";
            btn.disabled = disabled;
            btn.innerHTML = sk.name +
                (disabled ? `<span class="skill-status-label">${sk.label}</span>` : "");
            btn.onclick = () => useSkill(sk.name);
            wrapper.appendChild(btn);
        }

        if (sk.description) {
            const desc = document.createElement("div");
            desc.className = "skill-description";
            desc.textContent = sk.description;
            wrapper.appendChild(desc);
        }

        skillsDiv.appendChild(wrapper);
    });
    slot.appendChild(skillsDiv);
    return slot;
}

// ── Companion Chat ───────────────────────────────────────────────────────────
let _chatCompanionName = "";

function openChatModal(name, lastReply) {
    _chatCompanionName = name;
    document.getElementById("chat-modal-title").textContent = `💬 与${name}对话`;
    document.getElementById("chat-message-input").value = "";
    document.getElementById("chat-reply-area").style.display = "none";
    // 显示上次回复（如有）
    const lastArea = document.getElementById("chat-last-reply-area");
    if (lastReply) {
        document.getElementById("chat-last-reply").textContent = lastReply;
        lastArea.style.display = "";
    } else {
        lastArea.style.display = "none";
    }
    const btn = document.getElementById("chat-send-btn");
    btn.textContent = "发送 →";
    btn.disabled = false;
    document.getElementById("chat-overlay").style.display = "flex";
    document.getElementById("chat-message-input").focus();
}

function closeChatModal() {
    document.getElementById("chat-overlay").style.display = "none";
}

function sendChat() {
    const message = document.getElementById("chat-message-input").value.trim();
    if (!message) { alert("请输入消息"); return; }
    const btn = document.getElementById("chat-send-btn");
    btn.textContent = "⏳ 角色思考中…";
    btn.disabled = true;
    fetch("/api/companion-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: _chatCompanionName, message }),
    })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                document.getElementById("chat-reply-text").textContent = d.reply;
                document.getElementById("chat-reply-area").style.display = "";
                btn.textContent = "✅ 已收到回复";
                // 刷新槽位以显示气泡
                refreshCompanionSlots();
            } else {
                btn.textContent = "❌ " + (d.error || "未知错误");
                btn.disabled = false;
            }
        })
        .catch(() => { btn.textContent = "发送 →"; btn.disabled = false; });
}

function renderEmptySlot() {
    const slot = document.createElement("div");
    slot.className = "companion-slot";
    slot.innerHTML = `<div class="companion-slot-empty">空槽位</div>`;
    return slot;
}

function refreshCompanionSlots() {
    fetch("/api/companion-status")
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById("companion-slots");
            if (!container) return;

            // 指纹对比：数据没变就不重建 DOM，避免选区丢失
            const fingerprint = JSON.stringify(data);
            if (container.dataset.fingerprint === fingerprint) return;
            container.dataset.fingerprint = fingerprint;

            container.innerHTML = "";

            const comps = data.companions || [];
            const locked = data.locked;

            // render loaded companions
            comps.forEach(c => container.appendChild(renderSlot(c, locked)));
            // fill remaining slots as empty
            for (let i = comps.length; i < 3; i++) {
                container.appendChild(renderEmptySlot());
            }

            // update controls
            const addBtn = document.getElementById("companion-add-btn");
            const selectEl = document.getElementById("companion-select");
            const lockBtn = document.getElementById("companion-lock-btn");
            const controlsEl = document.getElementById("companion-controls");

            if (locked) {
                if (controlsEl) {
                    controlsEl.innerHTML = `<span class="companion-locked-badge">🔒 阵容已锁定</span>`;
                }
            } else {
                if (addBtn) addBtn.disabled = comps.length >= 3;
                if (selectEl) selectEl.disabled = comps.length >= 3;
            }
        })
        .catch(() => { });
}

function loadCompanionRegistry() {
    fetch("/api/companion-registry")
        .then(r => r.json())
        .then(list => {
            const sel = document.getElementById("companion-select");
            if (!sel) return;
            // preserve first option
            sel.innerHTML = `<option value="">选择助手…</option>`;
            list.forEach(c => {
                const opt = document.createElement("option");
                opt.value = c.name;
                const skillText = (c.skills && c.skills.length)
                    ? c.skills.join(" / ")
                    : "无技能";
                opt.textContent = `${c.name} — ${skillText}`;
                sel.appendChild(opt);
            });
        })
        .catch(() => { });
}

function addCompanion() {
    const sel = document.getElementById("companion-select");
    const name = sel ? sel.value : "";
    if (!name) return;
    fetch("/api/companion-add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
    })
        .then(r => r.json())
        .then(() => {
            refreshCompanionSlots();
            loadCompanionRegistry();
        })
        .catch(() => { });
}

function removeCompanion(name) {
    fetch("/api/companion-remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
    })
        .then(r => r.json())
        .then(() => {
            refreshCompanionSlots();
            loadCompanionRegistry();
        })
        .catch(() => { });
}

function lockCompanions() {
    if (!confirm("锁定阵容后无法更改助手，确认？")) return;
    fetch("/api/companion-lock", { method: "POST" })
        .then(r => r.json())
        .then(() => refreshCompanionSlots())
        .catch(() => { });
}

function useSkill(skillName) {
    fetch("/api/companion-use-skill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skill: skillName }),
    })
        .then(r => r.json())
        .then(() => refreshCompanionSlots())
        .catch(() => { });
}

// Initial load + periodic refresh
loadCompanionRegistry();
refreshCompanionSlots();
setInterval(refreshCompanionSlots, 3000);

// ── Companion skill Toast 通知 ────────────────────────────────────────────────

function showCompanionToast(entry) {
    const container = document.getElementById("companion-toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = "companion-toast";
    toast.innerHTML = `
        <div class="companion-toast-header">
            <span class="companion-toast-icon">✨</span>
            <span class="companion-toast-name">${entry.companion}</span>
            <span class="companion-toast-skill">· ${entry.skill}</span>
            <span class="companion-toast-time">${entry.ts}</span>
        </div>
        <div class="companion-toast-body">${entry.description}</div>
    `;

    container.appendChild(toast);

    // 触发进场动画
    requestAnimationFrame(() => toast.classList.add("companion-toast-enter"));

    // 4秒后退场
    setTimeout(() => {
        toast.classList.add("companion-toast-exit");
        setTimeout(() => toast.remove(), 500);
    }, 4000);
}

function pollCompanionLog() {
    fetch("/api/companion-log")
        .then(r => r.json())
        .then(entries => {
            entries.forEach((entry, i) => {
                // 多条时错开显示，避免堆叠
                setTimeout(() => showCompanionToast(entry), i * 600);
            });
        })
        .catch(() => { }); // 静默失败
}

// 每3秒检查一次 companion log（比 refreshData 稍慢，避免冲突）
setInterval(pollCompanionLog, 3000);
