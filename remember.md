# 运行
lsof -ti :5050 | xargs kill -9 && APP_MODE=alfred python3 dashboard.py

# 以non-Alfred模式运行
lsof -ti :5050 | xargs kill -9 && APP_MODE=standalone python3 dashboard.py

# 查看代码行数
cloc .

# ⚠️ 重要规则：开发与使用分离
- **番茄钟记录启动期间，不进行任何功能开发或测试**
- 功能开发、调试、测试全部放在学习结束后（reset 之后或第二天开始前）
- **AI 助手绝对不能运行 reset.py、move.py 等会修改游戏状态的脚本**