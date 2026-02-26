import os
import re
import json

import glob

def extract_stories():
    output_dir = "/Users/haichenlai/Desktop/Prompt/output/"
    out_file = "/Users/haichenlai/Desktop/Prompt/story_today.txt"

    # 寻找以 Gemini 开头的 .md 文件
    search_pattern = os.path.join(output_dir, "Gemini*.md")
    matching_files = glob.glob(search_pattern)

    if len(matching_files) == 0:
        print(f"错误：在 {output_dir} 找不到以 Gemini 开头的 md 文件")
        return
    elif len(matching_files) > 1:
        print(f"错误：在 {output_dir} 找到多个以 Gemini 开头的 md 文件，无法确定使用哪一个:")
        for file in matching_files:
            print(f"  - {file}")
        return
    
    md_file = matching_files[0]
    print(f"找到目标文件：{md_file}")

    with open(md_file, "r", encoding="utf-8") as f:
        content = f.read()

    stories = []
    
    # 1. 优先尝试匹配新的 <story_event> 格式
    events = list(re.finditer(r'<story_event>\s*(.*?)\s*</story_event>', content, re.DOTALL))
    if events:
        for match in events:
            event_text = match.group(1).strip()
            # 在此标签的前面（最多1500字符内）寻找最近的角色年龄
            preceding_text = content[max(0, match.start() - 1500) : match.start()]
            # 匹配“角色年龄：15岁”或“角色年龄：[15岁]”等
            age_match = list(re.finditer(r'角色年龄：.*?(\d+)\s*岁', preceding_text))
            
            if age_match:
                age = age_match[-1].group(1) # 取最后一个最接近的
            else:
                # 备用方案：寻找“第X条”
                record_match = list(re.finditer(r'\[?第(\d+)条记录\]?', preceding_text))
                age = record_match[-1].group(1) if record_match else "?"
                
            stories.append(f"{age}岁：\n{event_text}\n")
    else:
        # 2. 如果没有找到新格式，尝试兼容旧的 JSON 格式
        code_blocks = re.findall(r'```(?:json)?\n(.*?)\n```', content, re.DOTALL)
        for block in code_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict) and "this_age" in data and "current_event" in data:
                    age = data["this_age"]
                    event = data["current_event"]
                    stories.append(f"{age}岁：\n{event}\n")
            except Exception:
                continue

    if stories:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(stories))
        print(f"✅ 成功提取了 {len(stories)} 条模拟人生故事，并保存到 {out_file}")
    else:
        print("未能在 Markdown 文件中找到符合格式的故事内容。")

if __name__ == "__main__":
    extract_stories()
