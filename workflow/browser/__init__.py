#!/usr/bin/env python3
"""浏览器驱动工厂 + 包初始化。"""
from __future__ import annotations

import platform

from workflow.browser.base import BrowserDriver


def get_browser_driver() -> BrowserDriver:
    """根据当前平台返回合适的浏览器驱动。"""
    if platform.system() == "Darwin":
        from workflow.browser.applescript_driver import AppleScriptDriver
        return AppleScriptDriver()

    raise NotImplementedError(
        f"暂不支持 {platform.system()} 平台的浏览器自动化。"
        "未来将通过 Selenium/Playwright 驱动实现跨平台支持。"
    )
