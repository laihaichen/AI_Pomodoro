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

    // Current story
    const last = data.history && data.history.length > 0
        ? data.history[data.history.length - 1] : null;
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

    // Card buttons
    const intCount = parseInt(data.countinterventioncard || "0", 10);
    const desCount = parseInt(data.countcard || "0", 10);
    const hasHistory = data.history && data.history.length > 0;
    document.getElementById("btn-use-intervention").disabled = intCount <= 0 || !hasHistory;
    document.getElementById("btn-use-destiny").disabled = desCount <= 0 || !hasHistory;

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
        const preview = (t.story_text || "").substring(0, 40) + "…";

        entry.innerHTML = `
            <div class="timeline-header" onclick="this.parentElement.classList.toggle('open')">
                <span class="timeline-arrow">▶</span>
                <span>${t.age}岁</span>
                <span style="color:var(--dim);font-size:12px;">${escHtml(preview)}</span>
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

async function useIntervention() {
    const zone = await pickZone("选择要替换的区间");
    if (!zone) return;
    const text = prompt("输入自定义事件文本（将替换该区间的事件）：");
    if (!text || !text.trim()) return;

    const res = await fetch("/api/story/use-card", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "intervention", zone, event_text: text.trim() }),
    });
    const data = await res.json();
    alert(data.msg || (data.ok ? "成功" : "失败"));
    pollStoryState();
}

async function useDestiny() {
    const zone = await pickZone("选择要强制触发的区间");
    if (!zone) return;

    const res = await fetch("/api/story/use-card", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "destiny", zone }),
    });
    const data = await res.json();
    alert(data.msg || (data.ok ? "成功" : "失败"));
    pollStoryState();
}

function pickZone(title) {
    const options = ZONE_OPTIONS.map((o, i) => `${i + 1}. ${o.label}`).join("\n");
    const choice = prompt(`${title}\n\n${options}\n\n输入编号（1-${ZONE_OPTIONS.length}）：`);
    if (!choice) return null;
    const idx = parseInt(choice, 10) - 1;
    if (idx >= 0 && idx < ZONE_OPTIONS.length) return ZONE_OPTIONS[idx].key;
    alert("无效选择");
    return null;
}

// ── utils ───────────────────────────────────────────────────────────────────

function escHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}
