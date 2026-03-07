#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# install.sh — 番茄钟学习管理系统 一键安装脚本
#
# 用法:
#   git clone https://github.com/laihaichen/AI_Pomodoro.git
#   cd AI_Pomodoro
#   bash install.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "🍅 番茄钟学习管理系统 — 安装脚本"
echo "──────────────────────────────────"
echo ""

# ── 1. 检查 Python 3 ──────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3.10+。"
    echo "   推荐: brew install python3"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ 检测到 Python ${PY_VER}"

# ── 2. 安装 Python 依赖 ──────────────────────────────────────────────────────
echo ""
echo "📦 安装 Python 依赖..."
pip3 install -r requirements.txt
echo "✅ Python 依赖安装完成"

# ── 3. 初始化 data 目录 ──────────────────────────────────────────────────────
echo ""
echo "📂 初始化 data 目录..."

DATA_DIR="$(dirname "$0")/data"
mkdir -p "$DATA_DIR"

# 初始化 snippets_local.json（standalone 模式使用）
if [ ! -f "$DATA_DIR/snippets_local.json" ]; then
    APP_MODE=standalone python3 -c "from config import _init_local_snippets; _init_local_snippets()"
    echo "   ✅ 已生成 data/snippets_local.json"
else
    echo "   ⏭️  data/snippets_local.json 已存在，跳过"
fi

# 初始化各 txt 数据文件（如果不存在）
for f in curr_timestamp.txt prev_timestamp.txt first_timestamp.txt \
         pause_timestamp.txt continue_timestamp.txt h_value.txt \
         penalized_rest_up_to.txt health.txt final_fate.txt \
         is_boss_defeated.txt theme.txt; do
    if [ ! -f "$DATA_DIR/$f" ]; then
        touch "$DATA_DIR/$f"
    fi
done
echo "   ✅ 数据文件就绪"

# ── 4. 配置 Gemini API（可选） ───────────────────────────────────────────────
echo ""
API_CONFIG="$(dirname "$0")/api_config.json"
if [ ! -f "$API_CONFIG" ]; then
    echo "📝 创建 api_config.json 模板..."
    cat > "$API_CONFIG" <<'EOF'
{
    "gemini_api_key": "在此填入你的 Gemini API Key",
    "gemini_model": "gemini-3-flash-preview",
    "target_urls": ["gemini.google.com", "aistudio.google.com"]
}
EOF
    echo "   ✅ 已生成 api_config.json"
    echo "   ⚠️  请稍后编辑此文件，填入你的 Gemini API Key"
    echo "      获取地址: https://aistudio.google.com/apikey"
else
    echo "⏭️  api_config.json 已存在，跳过"
fi

# ── 5. 完成 ──────────────────────────────────────────────────────────────────
echo ""
echo "──────────────────────────────────"
echo "🎉 安装完成！"
echo ""
echo "启动方式："
echo ""
echo "  # Standalone 模式（无需 Alfred，推荐新用户）"
echo "  APP_MODE=standalone python3 dashboard.py"
echo ""
echo "  # Alfred 模式（需要安装 Alfred Powerpack）"
echo "  python3 dashboard.py"
echo ""
echo "然后在浏览器打开 http://localhost:5050"
echo ""
