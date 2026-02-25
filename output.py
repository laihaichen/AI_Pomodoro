import os
import glob

def main():
    # 获取当前脚本所在目录
    directory = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(directory, "output.txt")
    
    # 查找所有 .py 文件
    py_files = glob.glob(os.path.join(directory, "*.py"))
    
    count = 0
    with open(output_file, "w", encoding="utf-8") as outfile:
        for py_file in py_files:
            filename = os.path.basename(py_file)
            
            # 排除 output.py 自身，避免无限套娃
            if filename == "output.py":
                continue
                
            outfile.write(f"--- {filename} ---\n")
            
            try:
                with open(py_file, "r", encoding="utf-8") as infile:
                    outfile.write(infile.read())
            except Exception as e:
                outfile.write(f"读取文件时出错 / Error reading file: {e}\n")
                
            outfile.write("\n\n")
            count += 1
            
    print(f"✅ 成功将 {count} 个 Python 文件的内容写入到 {output_file}")

if __name__ == "__main__":
    main()
