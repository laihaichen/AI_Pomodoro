# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Pomodoro AI Learning RPG.

Build:  pyinstaller pomodoro.spec
Output: dist/PomodoroRPG.exe  (Windows)  /  dist/PomodoroRPG  (macOS)
"""

import sys
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "dashboard.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # ── 只读资源（打包进 exe）──
        (str(ROOT / "templates"),           "templates"),
        (str(ROOT / "static"),              "static"),
        (str(ROOT / "docs"),                "docs"),
        (str(ROOT / "workflow" / "templates"), "workflow/templates"),
        (str(ROOT / "snippets_and_workflows"), "snippets_and_workflows"),
        # config 和其他 Python 模块由 Analysis 自动发现
    ],
    hiddenimports=[
        "flask",
        "google.generativeai",
        "anthropic",
        "openai",
        "config",
        "host_ai",
        "update_h",
        "update_stage",
        "actions.move",
        "actions.pause",
        "actions.continue_",
        "actions.stay_backup",
        "actions.reset",
        "workflow.engine",
        "workflow.move_workflow",
        "workflow.pause_workflow",
        "workflow.continue_workflow",
        "workflow.stay_workflow",
        "workflow.usecard_workflow",
        "game.engine",
        "game.models",
        "game.prompts",
        "jury.engine",
        "jury.providers",
        "jury.prompts",
        "mod.companions",
        "mod.effects",
        "mod.skills",
        "complaint_manager.complaint_manage",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PomodoroRPG",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,          # True = 显示控制台（调试用），发布时可改 False
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
