# 运行
lsof -ti :5050 | xargs kill -9 && python3 /Users/haichenlai/Desktop/Prompt/dashboard.py

# 以non-Alfred模式运行
lsof -ti :5050 | xargs kill -9 && APP_MODE=standalone python3 dashboard.py

# 查看代码行数
cloc .