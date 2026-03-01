# 运行
lsof -ti :5050 | xargs kill -9 && python3 /Users/haichenlai/Desktop/Prompt/dashboard.py

# 查看代码行数
cloc .