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

    # 匹配所有的代码块
    # 使用正则非贪婪匹配获取 ``` 和 ``` 之间的内容
    code_blocks = re.findall(r'```(?:json)?\n(.*?)\n```', content, re.DOTALL)

    stories = []
    for block in code_blocks:
        try:
            # 尝试解析 JSON
            data = json.loads(block)
            # 检查是否包含模拟人生特有的键
            if isinstance(data, dict) and "this_age" in data and "current_event" in data:
                age = data["this_age"]
                event = data["current_event"]
                stories.append(f"{age}岁：\n{event}\n")
        except json.JSONDecodeError:
            # 不是合法的 JSON 或不需要的块
            continue

    if stories:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(stories))
        print(f"✅ 成功提取了 {len(stories)} 条模拟人生故事，并保存到 {out_file}")
    else:
        print("未能在 Markdown 文件中找到符合格式的故事内容。")

if __name__ == "__main__":
    extract_stories()
