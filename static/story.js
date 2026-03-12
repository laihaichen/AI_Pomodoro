/* story.js — Narrative panel frontend logic */

const TIER_KEYS = ["FAIL","NEG_HIGH","NEG_MID","NEG_LOW","POS_LOW","POS_MID","POS_HIGH"];
// Display order: best → worst (FAIL excluded from normal display)
const DISPLAY_ORDER = ["POS_HIGH","POS_MID","POS_LOW","NEG_LOW","NEG_MID","NEG_HIGH","FAIL"];
const TIER_LABELS = {
    POS_HIGH: "🟣 高度正面 (85~100)",
    POS_MID:  "🔵 中等正面 (50~84)",
    POS_LOW:  "🟢 轻度正面 (1~49)",
    NEG_LOW:  "🟡 轻度负面 (-1~-29)",
    NEG_MID:  "🟠 中等负面 (-30~-59)",
    NEG_HIGH: "🔴 严重负面 (-60~-89)",
    FAIL:     "💀 FAIL (-90~-100)",
};
const ZONE_OPTIONS = [
    { key: "POS_HIGH", label: "高度正面 (85~100)" },
    { key: "POS_MID",  label: "中等正面 (50~84)" },
    { key: "POS_LOW",  label: "轻度正面 (0~49)" },
    { key: "NEG_LOW",  label: "轻度负面 (-1~-29)" },
    { key: "NEG_MID",  label: "中等负面 (-30~-59)" },
    { key: "NEG_HIGH", label: "严重负面 (-60~-89)" },
];

let lastHistoryLen = 0;

// ── polling ─────────────────────────────────────────────────────────────────

async function pollStoryState() {
    try {
        const res = await fetch("/api/story/state");
        const data = await res.json();
        renderPanel(data);
    } catch (e) {
        console.error("story poll error:", e);
    }
}

setInterval(pollStoryState, 5000);
pollStoryState();  // initial load

// ── render ──────────────────────────────────────────────────────────────────

function renderPanel(data) {
    // Status bar — always live snippet data
    document.getElementById("s-character").textContent = data.character_name || "—";
    document.getElementById("s-age").textContent = data.age && data.age !== "0" ? data.age + "岁" : "—";
    document.getElementById("s-fate").textContent = data.fate_value && data.fate_value !== "0" ? data.fate_value : "—";
    document.getElementById("s-type").textContent = data.story_type || "—";
    document.getElementById("s-intervention").textContent = data.countinterventioncard || "0";
    document.getElementById("s-destiny").textContent = data.countcard || "0";

    // Story disabled state
    const disableBtn = document.getElementById("btn-disable-story");
    if (disableBtn) {
        if (data.story_disabled) {
            disableBtn.textContent = "🚫 故事生成已关闭";
            disableBtn.disabled = true;
            disableBtn.style.opacity = "0.5";
            disableBtn.style.cursor = "not-allowed";
            disableBtn.style.borderColor = "rgba(220,50,50,0.4)";
            disableBtn.style.color = "#f87171";
        }
    }

    // Current story
    const last = data.history && data.history.length > 0
        ? data.history[data.history.length - 1] : null;

    // Foretold badge — which tier was looked up + the actual event text
    const foretoldBadge = document.getElementById("story-foretold-badge");
    const foretoldText = document.getElementById("story-foretold-text");
    const ft = last ? last.fate_tier : (data.foretold || "");
    if (ft && TIER_LABELS[ft]) {
        // Look up the actual event text from the previous turn's registry
        let eventText = "";
        const hist = data.history || [];
        if (hist.length >= 2) {
            const prevRegistry = hist[hist.length - 2].event_registry;
            if (prevRegistry && prevRegistry[ft]) {
                eventText = prevRegistry[ft];
            }
        }
        foretoldText.innerHTML = TIER_LABELS[ft] +
            (eventText ? `<br><span style="color:var(--text);font-weight:400;font-size:13px;line-height:1.6;">「${escHtml(eventText)}」</span>` : "");
        foretoldBadge.style.display = "block";
    } else if (ft && ft.includes("第一条")) {
        foretoldText.textContent = "首轮 — 无上一轮事件（自由发挥出生故事）";
        foretoldBadge.style.display = "block";
    } else {
        foretoldBadge.style.display = "none";
    }
    const storyArea = document.getElementById("story-text-area");
    const loadingEl = document.getElementById("story-loading");
    const rerunBtn  = document.getElementById("btn-rerun");

    if (data.generating) {
        loadingEl.style.display = "flex";
        rerunBtn.style.display = "none";
    } else {
        loadingEl.style.display = "none";
        if (last) {
            rerunBtn.style.display = "inline-flex";
        }
    }

    if (last) {
        const isNew = data.history.length > lastHistoryLen;
        storyArea.textContent = last.story_text;
        storyArea.classList.remove("new-story");
        if (isNew) {
            lastHistoryLen = data.history.length;
            void storyArea.offsetWidth;  // force reflow
            storyArea.classList.add("new-story");
        }
    }

    // Event registry
    renderEventRegistry(last ? last.event_registry : null);

    // Card buttons — disabled when no cards, no history, OR generating
    const intCount = parseInt(data.countinterventioncard || "0", 10);
    const desCount = parseInt(data.countcard || "0", 10);
    const hasHistory = data.history && data.history.length > 0;
    const generating = data.generating;
    document.getElementById("btn-use-intervention").disabled = intCount <= 0 || !hasHistory || generating;
    document.getElementById("btn-use-destiny").disabled = desCount <= 0 || !hasHistory || generating;

    // Pending destiny badge
    const badge = document.getElementById("pending-destiny-badge");
    if (data.pending_destiny) {
        badge.textContent = `⏳ 宿命卡已排队：${data.pending_destiny}`;
        badge.style.display = "inline";
    } else {
        badge.style.display = "none";
    }

    // Timeline
    renderTimeline(data.history || []);
    document.getElementById("history-count").textContent = (data.history || []).length;
}

function renderEventRegistry(registry) {
    const grid = document.getElementById("event-registry-grid");
    if (!registry) {
        grid.innerHTML = '<div class="event-slot placeholder-slot">暂无事件预判</div>';
        return;
    }
    grid.innerHTML = "";
    for (const key of DISPLAY_ORDER) {
        const val = registry[key] || "—";
        const tier = key.toLowerCase();
        const slot = document.createElement("div");
        slot.className = `event-slot tier-${tier}`;
        slot.innerHTML = `<div class="slot-key">${TIER_LABELS[key] || key}</div><div>${escHtml(val)}</div>`;
        grid.appendChild(slot);
    }
}

function renderTimeline(history) {
    const container = document.getElementById("story-timeline");
    if (!history.length) {
        container.innerHTML = '<p class="placeholder-text">暂无故事历史</p>';
        return;
    }
    // Only rebuild if count changed
    if (container.dataset.len === String(history.length)) return;
    container.dataset.len = String(history.length);

    container.innerHTML = "";
    for (let i = history.length - 1; i >= 0; i--) {
        const t = history[i];
        const entry = document.createElement("div");
        entry.className = "timeline-entry" + (i === history.length - 1 ? " open" : "");

        const fateClass = (t.fate_value || 0) >= 0 ? "positive" : "negative";

        // 梗概：显示 fate tier 标签 + 引用的事件文本
        let preview = "";
        const tierLabel = TIER_LABELS[t.fate_tier] || "";
        if (i === 0 || !tierLabel) {
            preview = "出生";
        } else if (i > 0) {
            const prevReg = history[i - 1].event_registry;
            const eventText = prevReg && prevReg[t.fate_tier] ? prevReg[t.fate_tier] : "";
            preview = tierLabel + (eventText ? " — " + eventText : "");
        }

        entry.innerHTML = `
            <div class="timeline-header" onclick="this.parentElement.classList.toggle('open')">
                <span class="timeline-arrow">▶</span>
                <span>${t.age}岁</span>
                <span style="color:var(--bright);font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escHtml(preview)}</span>
                <span class="timeline-fate ${fateClass}">${t.fate_value}</span>
            </div>
            <div class="timeline-body">${escHtml(t.story_text || "")}</div>
        `;
        container.appendChild(entry);
    }
}

// ── actions ─────────────────────────────────────────────────────────────────

async function rerunStory() {
    if (!confirm("确定要重新生成当前故事吗？")) return;
    const btn = document.getElementById("btn-rerun");
    btn.disabled = true;
    btn.textContent = "⏳ 生成中…";
    try {
        const res = await fetch("/api/story/rerun", { method: "POST" });
        const data = await res.json();
        if (data.ok) {
            pollStoryState();
        } else {
            alert("重新生成失败：" + (data.error || data.msg || "未知错误"));
        }
    } catch (e) {
        alert("网络错误：" + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = "🔄 重新生成";
    }
}

// ── intervention card modal ─────────────────────────────────────────────────

function openInterventionModal() {
    document.getElementById("intv-step1").style.display = "block";
    document.getElementById("intv-step2").style.display = "none";
    document.getElementById("intv-event-text").value = "";
    document.getElementById("intervention-overlay").style.display = "flex";
}
function closeInterventionModal() {
    document.getElementById("intervention-overlay").style.display = "none";
}
function intvNextStep() {
    const sel = document.getElementById("intv-zone-select");
    document.getElementById("intv-zone-display").textContent = sel.options[sel.selectedIndex].text;
    document.getElementById("intv-step1").style.display = "none";
    document.getElementById("intv-step2").style.display = "block";
}
function intvBackStep() {
    document.getElementById("intv-step1").style.display = "block";
    document.getElementById("intv-step2").style.display = "none";
}
async function intvSubmit() {
    const zone = document.getElementById("intv-zone-select").value;
    const text = document.getElementById("intv-event-text").value.trim();
    if (!text) { alert("请输入自定义事件描述"); return; }
    await fetch("/api/story/use-card", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "intervention", zone, event_text: text }),
    });
    closeInterventionModal();
    pollStoryState();
}

// ── destiny card modal ──────────────────────────────────────────────────────

function openDestinyModal() {
    document.getElementById("destiny-overlay").style.display = "flex";
}
function closeDestinyModal() {
    document.getElementById("destiny-overlay").style.display = "none";
}
async function destinySubmit() {
    const zone = document.getElementById("destiny-zone-select").value;
    await fetch("/api/story/use-card", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "destiny", zone }),
    });
    closeDestinyModal();
    pollStoryState();
}

// ── disable story ───────────────────────────────────────────────────────────

function disableStoryGeneration(btn) {
    if (!confirm("⚠️ 确认关闭本局故事生成？\n\n关闭后番茄钟推进不再生成故事，仅可通过「重置所有状态」恢复。")) return;
    btn.disabled = true;
    btn.textContent = "⏳ 写入中...";
    fetch("/api/story/disable", { method: "POST" })
        .then(r => r.json())
        .then(d => {
            if (d.ok) {
                btn.textContent = "🚫 故事生成已关闭";
                btn.style.opacity = "0.5";
                btn.style.cursor = "not-allowed";
                btn.style.borderColor = "rgba(220,50,50,0.4)";
                btn.style.color = "#f87171";
            } else {
                btn.textContent = "❌ 失败";
                btn.disabled = false;
            }
        })
        .catch(() => { btn.textContent = "❌ 网络错误"; btn.disabled = false; });
}

// ── utils ───────────────────────────────────────────────────────────────────

function escHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}
