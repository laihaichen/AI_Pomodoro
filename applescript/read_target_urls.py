#!/usr/bin/env python3
"""读取 api_config.json 中的 target_urls，每行输出一个 URL。"""
import json, sys
try:
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    urls = cfg.get("target_urls", ["gemini.google.com", "aistudio.google.com"])
except Exception:
    urls = ["gemini.google.com"]
print("\n".join(urls))
