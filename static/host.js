/* host.js — Sandbox mode host page logic */

(function () {
    "use strict";

    const APP_MODE = document.body.dataset.appMode || "";
    const isSandbox = APP_MODE === "sandbox";

    // ── Elements ────────────────────────────────────────────────────────────
    const messagesEl   = document.getElementById("host-messages");
    const typingEl     = document.getElementById("host-typing");
    const textareaEl   = document.getElementById("host-input");
    const btnMove      = document.getElementById("host-btn-move");
    const btnStay      = document.getElementById("host-btn-stay");
    const idleOverlay  = document.getElementById("host-idle-overlay");
    const disabledOverlay = document.getElementById("host-disabled-overlay");

    // ── Idle mode ───────────────────────────────────────────────────────────
    if (!isSandbox) {
        if (idleOverlay) idleOverlay.style.display = "flex";
        return; // exit — no polling, no functionality
    } else {
        if (idleOverlay) idleOverlay.style.display = "none";
    }

    // ── Check if host is disabled → show shutdown overlay ────────────────
    function showDisabledOverlay() {
        if (disabledOverlay) disabledOverlay.style.display = "flex";
    }
    fetch("/api/host/status")
        .then(r => r.json())
        .then(d => { if (d.disabled) showDisabledOverlay(); })
        .catch(() => {});

    // ── State ───────────────────────────────────────────────────────────────
    let lastHistoryLen = 0;
    let sending = false;

    // ── Markdown rendering config ────────────────────────────────────────
    if (typeof marked !== "undefined") {
        marked.setOptions({
            breaks: true,
            gfm: true,
            highlight: function (code, lang) {
                if (typeof hljs !== "undefined") {
                    if (lang && hljs.getLanguage(lang)) {
                        return hljs.highlight(code, { language: lang }).value;
                    }
                    return hljs.highlightAuto(code).value;
                }
                return code;
            },
        });
    }

    // ── Chat rendering ─────────────────────────────────────────────────────
    function renderMessage(role, text) {
        const div = document.createElement("div");
        div.className = "host-msg " + role;
        if (role === "model" && typeof marked !== "undefined") {
            div.innerHTML = marked.parse(text);
        } else {
            div.textContent = text;
        }
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function renderSystemMessage(text) {
        const div = document.createElement("div");
        div.className = "host-msg system";
        div.textContent = text;
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    // ── Load history on page load ──────────────────────────────────────────
    function loadHistory() {
        fetch("/api/host/history")
            .then(r => r.json())
            .then(data => {
                if (!data.ok) return;
                const history = data.history || [];
                messagesEl.innerHTML = "";
                for (const msg of history) {
                    const role = msg.role || "model";
                    const text = (msg.parts || []).join("\n");
                    renderMessage(role, text);
                }
                lastHistoryLen = history.length;
            })
            .catch(() => {});
    }

    loadHistory();

    // ── Send logic ─────────────────────────────────────────────────────────
    function sendToHost(endpoint) {
        const msg = (textareaEl.value || "").trim();
        if (sending) return;

        if (msg) {
            // 对话框有内容 → 直接发送
            _doSend(endpoint, msg, { message: msg });
        } else {
            // 对话框为空 → 读剪贴板后发送
            navigator.clipboard.readText()
                .then(clip => {
                    const clipText = (clip || "").trim();
                    const displayMsg = clipText
                        ? "📋 " + clipText
                        : "📋 (剪贴板为空)";
                    _doSend(endpoint, displayMsg, {});
                })
                .catch(() => {
                    // 剪贴板权限被拒 → 仍然发送，后端用 pbpaste 读
                    _doSend(endpoint, "📋 (读取剪贴板中…)", {});
                });
        }
    }

    function _doSend(endpoint, displayMsg, body) {
        sending = true;
        btnMove.disabled = true;
        btnStay.disabled = true;
        typingEl.classList.add("active");

        renderMessage("user", displayMsg);
        textareaEl.value = "";
        textareaEl.style.height = "42px";

        fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        })
            .then(r => r.json())
            .then(data => {
                typingEl.classList.remove("active");
                if (data.ok && data.reply) {
                    renderMessage("model", data.reply);
                } else if (data.error) {
                    renderSystemMessage("⚠️ " + data.error);
                }
            })
            .catch(err => {
                typingEl.classList.remove("active");
                renderSystemMessage("❌ 网络错误：" + err.message);
            })
            .finally(() => {
                sending = false;
                btnMove.disabled = false;
                btnStay.disabled = false;
            });
    }

    // ── Button handlers ────────────────────────────────────────────────────
    if (btnMove) {
        btnMove.addEventListener("click", () => sendToHost("/api/next-pomodoro"));
    }
    if (btnStay) {
        btnStay.addEventListener("click", () => sendToHost("/api/stay-pomodoro"));
    }

    // Enter to send (Shift+Enter for newline)
    if (textareaEl) {
        textareaEl.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendToHost("/api/next-pomodoro");
            }
        });

        // Auto-resize textarea
        textareaEl.addEventListener("input", () => {
            textareaEl.style.height = "42px";
            textareaEl.style.height = Math.min(textareaEl.scrollHeight, 160) + "px";
        });
    }

    // ── Control buttons (side panel) ────────────────────────────────────────
    function hostControlAction(endpoint, btn) {
        const orig = btn.textContent;
        btn.disabled = true;
        btn.textContent = "⏳ ...";
        fetch(endpoint, { method: "POST" })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    btn.textContent = "✅ 完成";
                    setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 1500);
                } else {
                    btn.textContent = "❌ " + (data.error || "失败");
                    setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 2000);
                }
            })
            .catch(() => {
                btn.textContent = "❌ 网络错误";
                setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 2000);
            });
    }

    // Pause button
    const btnPause = document.getElementById("host-btn-pause");
    if (btnPause) {
        btnPause.addEventListener("click", function () {
            hostControlAction("/api/pause", this);
        });
    }

    // Continue button
    const btnContinue = document.getElementById("host-btn-continue");
    if (btnContinue) {
        btnContinue.addEventListener("click", function () {
            hostControlAction("/api/continue", this);
        });
    }

    // Disable host response
    const btnDisable = document.getElementById("host-btn-disable");
    if (btnDisable) {
        btnDisable.addEventListener("click", function () {
            if (!confirm("确定关闭主持人回应？关闭后需要重置才能恢复。")) return;
            btnDisable.disabled = true;
            btnDisable.textContent = "⏳ ...";
            fetch("/api/host/disable", { method: "POST" })
                .then(r => r.json())
                .then(data => {
                    if (data.ok) {
                        showDisabledOverlay();
                    } else {
                        btnDisable.textContent = "❌ " + (data.error || "失败");
                        setTimeout(() => { btnDisable.textContent = "🚫 关闭主持人回应"; btnDisable.disabled = false; }, 2000);
                    }
                })
                .catch(() => {
                    btnDisable.textContent = "❌ 网络错误";
                    setTimeout(() => { btnDisable.textContent = "🚫 关闭主持人回应"; btnDisable.disabled = false; }, 2000);
                });
        });
    }

    // Reset
    const btnReset = document.getElementById("host-btn-reset");
    if (btnReset) {
        btnReset.addEventListener("click", function () {
            const noArchive = document.getElementById("chk-no-archive")?.checked;
            const msg = noArchive
                ? "⚠️ 你确定要重置所有状态吗？\n\n⚡ 已勾选「不保存」：将直接清空，不归档任何数据。"
                : "⚠️ 你确定要重置所有状态吗？\n\n这将清空所有番茄钟记录和对话历史，操作无法撤销。";
            if (!confirm(msg)) return;
            const orig = this.textContent;
            this.disabled = true;
            this.textContent = "⏳ 重置中...";
            fetch("/api/reset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ no_archive: !!noArchive }),
            })
                .then(r => r.json())
                .then(data => {
                    if (data.ok) {
                        this.textContent = "✅ 已重置";
                        messagesEl.innerHTML = "";
                        lastHistoryLen = 0;
                        setTimeout(() => { this.textContent = orig; this.disabled = false; }, 1500);
                    } else {
                        this.textContent = "❌ " + (data.error || "失败");
                        setTimeout(() => { this.textContent = orig; this.disabled = false; }, 2000);
                    }
                })
                .catch(() => {
                    this.textContent = "❌ 网络错误";
                    setTimeout(() => { this.textContent = orig; this.disabled = false; }, 2000);
                });
        });
    }

    // ── Status panel polling ────────────────────────────────────────────────
    let hostTsRaw = null;

    function pollState() {
        fetch("/api/state")
            .then(r => r.json())
            .then(d => {
                setText("host-val-count", d.current_prompt_count);
                setText("host-val-total", d.total_count);
                setText("host-val-health", d.healthy);
                setText("host-val-offset", d.offset);
                setText("host-val-score", d.total_score);
                setText("host-val-stage", d.stage);
                setText("host-val-boss", d.bossfight_stage);
                setText("host-val-rest", d.total_rest_time);
                setText("host-val-victory", d.is_victory);
                setText("host-val-interval", d.interval);
                hostTsRaw = d.curr_ts_raw || null;
            })
            .catch(() => {});
    }

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value || "—";
    }

    pollState();
    setInterval(pollState, 2000);

    // ── Tomato timer (1-second tick) ────────────────────────────────────────
    setInterval(() => {
        if (!hostTsRaw) return;
        const startDt = new Date(hostTsRaw);
        const nowDt = new Date();
        const diffSecs = Math.floor((nowDt - startDt) / 1000);
        const timerEl = document.getElementById("host-tomato-timer");
        if (diffSecs >= 0 && timerEl) {
            if (diffSecs < 60) {
                timerEl.textContent = `${diffSecs}秒`;
            } else {
                const m = Math.floor(diffSecs / 60);
                const s = diffSecs % 60;
                timerEl.textContent = `${m}分钟${s}秒`;
            }
        }
    }, 1000);

})();
