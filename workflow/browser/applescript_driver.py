#!/usr/bin/env python3
"""AppleScript 浏览器驱动 — macOS Chrome 自动化。

复用 applescript/move.applescript 的核心逻辑：
  1. 找到 Chrome 中所有 Gemini 标签页
  2. JS 聚焦输入框 → 直接注入完整文本（替代 keystroke + Alfred 展开）
  3. JS 点击发送按钮

去掉了原 AppleScript 中的 keystroke 环节（展开由 engine.py 完成）。
"""
from __future__ import annotations

import subprocess
import textwrap

from workflow.browser.base import BrowserDriver


class AppleScriptDriver(BrowserDriver):
    """macOS AppleScript → Chrome 自动化驱动。"""

    # 可配置的目标 URL 匹配关键词
    TARGET_URLS = ("/gemini.google.com",)

    def inject_and_send(self, text: str) -> bool:
        script = self._build_script(text)
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0

    def _build_script(self, text: str) -> str:
        # AppleScript 字符串转义：反斜杠和双引号
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        # JS 字符串转义：反斜杠、单引号、换行符、反引号
        js_escaped = (
            text
            .replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("${", "\\${")
        )

        # URL 匹配条件
        url_conditions = " or ".join(
            f'tabURL contains "{u}"' for u in self.TARGET_URLS
        )

        return textwrap.dedent(f'''\
            tell application "Google Chrome"
                activate

                -- 收集所有符合条件的 AI 聊天标签页
                set aiPages to {{}}
                try
                    repeat with w_index from 1 to (count of windows)
                        repeat with t_index from 1 to (count of tabs of window w_index)
                            set tabURL to URL of tab t_index of window w_index
                            if {url_conditions} then
                                set end of aiPages to {{win:w_index, tab:t_index}}
                            end if
                        end repeat
                    end repeat
                on error
                end try

                if (count of aiPages) is 0 then
                    display notification "没有找到符合条件的AI聊天页面。" with title "执行终止"
                    return "No AI pages found."
                end if

                repeat with pageInfo in aiPages
                    try
                        set win_idx to win of pageInfo
                        set tab_idx to tab of pageInfo
                        tell window win_idx
                            set active tab index to tab_idx
                            set index to 1
                        end tell

                        tell application "System Events" to set frontmost of process "Google Chrome" to true
                        delay 0.02

                        -- 聚焦输入框 + 直接注入完整文本（替代 keystroke + Alfred 展开）
                        tell tab tab_idx of window win_idx
                            execute javascript "
                                (function() {{
                                    var el = document.querySelector('.ql-editor, #prompt-textarea, textarea:not([readonly]), div[contenteditable=\\"true\\"]');
                                    if (!el) return;
                                    el.focus();
                                    el.click();

                                    var text = `{js_escaped}`;

                                    if (el.value !== undefined) {{
                                        el.value = text;
                                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                                    }} else {{
                                        el.textContent = text;
                                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                                    }}
                                }})();
                            "
                        end tell

                        delay 0.1

                        -- 点击发送按钮（复用原 AppleScript 逻辑）
                        tell tab tab_idx of window win_idx
                            execute javascript "
                                var sendButtonSelectors = [
                                    'button[aria-label=\\"Run\\"]',
                                    'button[data-testid=\\"send-button\\"]',
                                    'button[aria-label=\\"Send message\\"]',
                                    'button[aria-label=\\"Send Message\\"]',
                                    'button[type=\\"submit\\"]:not([disabled])',
                                    'button.btn-widget[type=\\"submit\\"]',
                                    'button[class*=\\"send\\"]'
                                ];

                                function tryClickSendButton() {{
                                    for (var i = 0; i < sendButtonSelectors.length; i++) {{
                                        var btn = document.querySelector(sendButtonSelectors[i]);
                                        if (btn && !btn.disabled) {{
                                            btn.click();
                                            return true;
                                        }}
                                    }}
                                    return false;
                                }}

                                var retries = 0;
                                var maxRetries = 20;
                                var interval = setInterval(function() {{
                                    if (tryClickSendButton() || retries >= maxRetries) {{
                                        clearInterval(interval);
                                    }}
                                    retries++;
                                }}, 50);
                            "
                        end tell

                        delay 0.03

                    on error errMsg
                    end try

                    delay 0.18
                end repeat

                display notification "Attempted to send on " & (count of aiPages) & " pages." with title "Task Completed"
            end tell

            return "Script finished successfully."
        ''')
