/* ══════════════════════════════════════════════════════════════════
   jury.js — 陪审团系统前端逻辑
   ══════════════════════════════════════════════════════════════════ */

// ── 状态 ──
let juryState = {};
let suspensionTimer = null;
let suspensionSeconds = 120;  // 每个追问 2 分钟

// ── 初始化 ──
document.addEventListener("DOMContentLoaded", async () => {
    await loadJuryStatus();
    restoreLastState();
    // 每 5 秒刷新状态（轻量）
    setInterval(loadJuryStatus, 5000);
});

// ── 恢复上次状态（持久化） ──
async function restoreLastState() {
    // 如果当前是悬置中，恢复悬置 UI
    if (juryState.status === "suspended" && juryState.suspension_queue && juryState.suspension_queue.length > 0) {
        const idx = juryState.suspension_index || 0;
        const queue = juryState.suspension_queue;
        document.getElementById("suspension-area").style.display = "block";
        showNextSuspension(
            queue.map(q => ({juror_name: q.juror_name, question: q.suspension_question || q.question || ""})),
            0, queue.length
        );
        document.getElementById("suspension-progress").textContent = `(${idx + 1}/${queue.length})`;
        // 同时显示已有投票气泡
        if (juryState.votes && juryState.votes.length > 0) {
            renderVoteIndicators(juryState.votes);
        }
        showVerdictReport("", "suspended");
        return;
    }

    // 否则恢复上次判决结果
    try {
        const r = await fetch("/api/jury/report");
        const d = await r.json();
        if (d.ok && d.report && d.report !== "暂无审议记录。") {
            // 恢复辩护
            showDefense(juryState.defender, juryState.defense);
            // 恢复气泡
            if (d.votes && d.votes.length > 0) {
                renderVoteIndicators(d.votes);
            }
            // 恢复判决
            showVerdictReport(d.report, d.outcome);
        }
    } catch (e) {
        console.error("restoreLastState:", e);
    }
}

// ── 加载陪审团状态 ──
let _lastJurorKey = "";

async function loadJuryStatus() {
    try {
        const r = await fetch("/api/jury/status");
        const d = await r.json();
        juryState = d;

        // 仅当陪审员列表变化时才重渲染头像（避免销毁气泡）
        const jurorKey = (d.jurors || []).map(j => j.name).join(",");
        if (jurorKey !== _lastJurorKey) {
            renderAvatars(d.jurors);
            _lastJurorKey = jurorKey;
        }

        document.getElementById("jury-status-text").textContent =
            ({idle: "待命", deliberating: "审议中", suspended: "悬置追问中"})[d.status] || d.status;
        document.getElementById("history-count").textContent = d.history_count || 0;

        // 渲染投票状态到头像（仅在有当前投票时）
        if (d.votes && d.votes.length > 0) {
            renderVoteIndicators(d.votes);
        }
    } catch (e) {
        console.error("loadJuryStatus:", e);
    }
}

// ── 渲染头像 ──
function renderAvatars(jurors) {
    const container = document.getElementById("jury-avatars");
    if (!jurors || jurors.length === 0) {
        container.innerHTML = `
            <div class="jury-avatar-slot placeholder"><div class="jury-avatar-circle">?</div><span>未初始化</span></div>
            <div class="jury-avatar-slot placeholder"><div class="jury-avatar-circle">?</div><span>锁定阵容后自动分配</span></div>
            <div class="jury-avatar-slot placeholder"><div class="jury-avatar-circle">?</div><span>—</span></div>
        `;
        return;
    }
    container.innerHTML = jurors.map(j => `
        <div class="jury-avatar-slot" data-juror="${j.name}">
            <div class="jury-avatar-circle">
                ${j.avatar_url ? `<img src="${j.avatar_url}" alt="${j.name}">` : "?"}
            </div>
            <span>${j.name}</span>
        </div>
    `).join("");
}

// ── 投票气泡 + 头像指示器 ──
function renderVoteIndicators(votes) {
    const emojis = { approve: "🟢", reject: "🔴", suspend: "🟡" };
    const labels = { approve: "赞成", reject: "反对", suspend: "悬置" };
    const classes = { approve: "vote-approve", reject: "vote-reject", suspend: "vote-suspend" };

    for (const v of votes) {
        const slot = document.querySelector(`.jury-avatar-slot[data-juror="${v.juror_name}"]`);
        if (!slot) continue;

        // 头像边框颜色
        slot.classList.remove("vote-approve", "vote-reject", "vote-suspend");
        slot.classList.add(classes[v.vote] || "");

        // 投票 emoji 指示器
        let indicator = slot.querySelector(".vote-indicator");
        if (!indicator) {
            indicator = document.createElement("div");
            indicator.className = "vote-indicator";
            slot.appendChild(indicator);
        }
        indicator.textContent = emojis[v.vote] || "";

        // 气泡（在头像上方）
        let bubble = slot.querySelector(".speech-bubble");
        if (!bubble) {
            bubble = document.createElement("div");
            bubble.className = "speech-bubble";
            slot.insertBefore(bubble, slot.firstChild);
        }
        bubble.className = `speech-bubble bubble-${v.vote || "approve"}`;
        bubble.innerHTML = `
            <div class="bubble-header">${emojis[v.vote] || ""} ${labels[v.vote] || v.vote}</div>
            <div class="bubble-text">${v.reasoning || ""}</div>
            ${v.suspension_question ? `<div class="bubble-question">追问：${v.suspension_question}</div>` : ""}
        `;
    }
}

// ── 清除气泡 ──
function clearBubbles() {
    document.querySelectorAll(".speech-bubble").forEach(el => el.remove());
    document.querySelectorAll(".vote-indicator").forEach(el => el.remove());
    document.querySelectorAll(".jury-avatar-slot").forEach(el => {
        el.classList.remove("vote-approve", "vote-reject", "vote-suspend");
    });
}

// ── 提交审议 ──
async function submitTrial() {
    const question = document.getElementById("jury-question").value.trim();
    const answer = document.getElementById("jury-answer").value.trim();
    if (!question || !answer) {
        alert("问题和答案不能为空");
        return;
    }

    const btn = document.getElementById("jury-submit-btn");
    const loading = document.getElementById("jury-loading");
    btn.disabled = true;
    loading.style.display = "flex";

    // 隐藏旧结果 + 清除旧气泡
    clearBubbles();
    document.getElementById("verdict-area").style.display = "none";
    document.getElementById("suspension-area").style.display = "none";

    try {
        const r = await fetch("/api/jury/submit", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({question, answer}),
        });
        const d = await r.json();

        if (!d.ok) {
            alert(d.msg || "提交失败");
            return;
        }

        if (d.outcome === "suspended") {
            handleSuspension(d);
        } else {
            showVerdict(d);
        }

        loadJuryStatus();
    } catch (e) {
        alert("网络错误：" + e.message);
    } finally {
        btn.disabled = false;
        loading.style.display = "none";
    }
}

// ── 悬置处理 ──
function handleSuspension(data) {
    const area = document.getElementById("suspension-area");
    area.style.display = "block";
    document.getElementById("verdict-area").style.display = "none";

    // 找到第一个有实际问题的追问
    const queue = data.suspension_queue || [];
    showNextSuspension(queue, 0, queue.length);

    // 同时显示报告（部分）
    showVerdictReport(data.report, "suspended");
}

function showNextSuspension(queue, idx, total) {
    if (idx >= queue.length) return;

    const current = queue[idx];
    document.getElementById("suspension-progress").textContent = `(${idx + 1}/${total})`;
    document.getElementById("suspension-juror-name").textContent = `${current.juror_name} 追问：`;
    document.getElementById("suspension-question-text").textContent = current.question || "（无追问内容）";
    document.getElementById("suspension-reply").value = "";

    // 重置断网声明勾选
    const chk = document.getElementById("disconnect-check");
    if (chk) { chk.checked = false; }
    document.getElementById("suspension-reply-btn").disabled = true;

    // 启动计时器（2分钟/每个追问）
    suspensionSeconds = 120;
    clearInterval(suspensionTimer);
    updateTimerDisplay();
    suspensionTimer = setInterval(() => {
        suspensionSeconds--;
        updateTimerDisplay();
        if (suspensionSeconds <= 0) {
            clearInterval(suspensionTimer);
            // 超时自动提交空回答
            submitSuspensionReply();
        }
    }, 1000);
}

// ── 断网声明勾选控制 ──
function toggleReplyBtn() {
    const checked = document.getElementById("disconnect-check").checked;
    document.getElementById("suspension-reply-btn").disabled = !checked;
}

function updateTimerDisplay() {
    const m = Math.floor(suspensionSeconds / 60);
    const s = suspensionSeconds % 60;
    const el = document.getElementById("suspension-timer");
    el.textContent = `${m}:${s.toString().padStart(2, "0")}`;
    if (suspensionSeconds <= 30) {
        el.style.color = "#f87171";
    } else {
        el.style.color = "#fbbf24";
    }
}

// ── 提交悬置回答 ──
async function submitSuspensionReply() {
    clearInterval(suspensionTimer);
    const reply = document.getElementById("suspension-reply").value.trim();
    const btn = document.getElementById("suspension-reply-btn");
    btn.disabled = true;

    try {
        const r = await fetch("/api/jury/suspend-reply", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({reply}),
        });
        const d = await r.json();

        if (!d.ok) {
            alert(d.msg || "提交失败");
            btn.disabled = false;
            return;
        }

        if (d.done) {
            // 全部追问回答完毕
            document.getElementById("suspension-area").style.display = "none";
            showVerdict(d);
        } else {
            // 还有下一个追问
            const next = d.next;
            showNextSuspension(
                [{juror_name: next.juror_name, question: next.question}],
                0, next.total
            );
            document.getElementById("suspension-progress").textContent = `(${next.index + 1}/${next.total})`;
        }

        loadJuryStatus();
    } catch (e) {
        alert("网络错误：" + e.message);
    } finally {
        btn.disabled = false;
    }
}

// ── 显示辩护意见 ──
function showDefense(defender, defense) {
    const area = document.getElementById("defense-area");
    if (defense && defender) {
        document.getElementById("defender-name").textContent = defender;
        document.getElementById("defense-text").textContent = defense;
        area.style.display = "block";
    } else {
        area.style.display = "none";
    }
}

// ── 显示判决 ──
async function showVerdict(data) {
    document.getElementById("suspension-area").style.display = "none";
    const area = document.getElementById("verdict-area");
    area.style.display = "block";

    // 显示辩护
    showDefense(data.defender, data.defense);

    // 渲染投票气泡到头像上方
    if (data.votes && data.votes.length > 0) {
        renderVoteIndicators(data.votes);
    }

    // 判决标签
    const banner = document.getElementById("verdict-banner");
    banner.className = "verdict-banner";
    if (data.outcome === "health_unchanged") {
        banner.classList.add("outcome-pass");
        banner.textContent = "✅ 通过";
    } else if (data.outcome === "health_minus_1") {
        banner.classList.add("outcome-fail");
        banner.textContent = `❌ 未通过 · 健康度 -1${data.new_health != null ? ` (${data.new_health})` : ""}`;
    }

    showVerdictReport(data.report, data.outcome);
    loadJuryStatus();

    // 清除提问和回答文本框，为下次提交做准备
    document.getElementById("jury-question").value = "";
    document.getElementById("jury-answer").value = "";
}

function showVerdictReport(report, outcome) {
    const area = document.getElementById("verdict-area");
    area.style.display = "block";
    document.getElementById("verdict-report").textContent = report || "";

    const banner = document.getElementById("verdict-banner");
    banner.className = "verdict-banner";
    if (outcome === "health_unchanged") {
        banner.classList.add("outcome-pass");
        banner.textContent = "✅ 通过";
    } else if (outcome === "health_minus_1") {
        banner.classList.add("outcome-fail");
        banner.textContent = "❌ 未通过 · 健康度 -1";
    } else if (outcome === "suspended") {
        banner.classList.add("outcome-suspend");
        banner.textContent = "🟡 悬置中";
    }
}




// ── 复制报告到剪贴板 ──
async function copyReport() {
    const report = document.getElementById("verdict-report").textContent;
    const msg = document.getElementById("copy-msg");
    if (!report) { msg.textContent = "报告为空"; return; }

    try {
        await navigator.clipboard.writeText(report);
        msg.textContent = "✅ 已复制到剪贴板";
    } catch (e) {
        // fallback
        const ta = document.createElement("textarea");
        ta.value = report;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        msg.textContent = "✅ 已复制到剪贴板";
    }
    setTimeout(() => { msg.textContent = ""; }, 3000);
}
