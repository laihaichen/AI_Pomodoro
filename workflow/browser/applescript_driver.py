#!/usr/bin/env python3
"""AppleScript 浏览器驱动 — macOS Chrome 自动化。

复用 applescript/move.applescript 的核心逻辑：
  1. 找到 Chrome 中所有 Gemini 标签页
  2. JS 聚焦输入框 → 直接注入完整文本（替代 keystroke + Alfred 展开）
  3. JS 点击发送按钮

文本通过 Base64 编码传输，避免特殊字符破坏 AppleScript/JS 语法。
"""
from __future__ import annotations

import base64
import subprocess
import textwrap

import config
from workflow.browser.base import BrowserDriver


class AppleScriptDriver(BrowserDriver):
    """macOS AppleScript → Chrome 自动化驱动。"""

    def inject_and_send(self, text: str) -> bool:
        config.backup_prompt(text)
        script = self._build_script(text)
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0

    def _build_script(self, text: str) -> str:
        # Base64 编码文本，避免任何特殊字符破坏 AppleScript/JS 语法
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")

        # URL 匹配条件
        url_conditions = " or ".join(
            f'tabURL contains "{u}"' for u in config.TARGET_URLS
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

                        -- 聚焦输入框 + Base64 解码注入完整文本
                        tell tab tab_idx of window win_idx
                            execute javascript "
                                (function() {{
                                    var el = document.querySelector('.ql-editor, #prompt-textarea, textarea:not([readonly]), div[contenteditable=\\"true\\"]');
                                    if (!el) return;
                                    el.focus();
                                    el.click();

                                    var b64 = '{b64}';
                                    var text = decodeURIComponent(escape(atob(b64)));

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
