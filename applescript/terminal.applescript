-- 1. 激活 Terminal
tell application "Terminal"
    activate
end tell

-- 增加等待时间，确保终端完全启动并准备好接收输入
delay 0.3

tell application "System Events"
    -- 强制将 Terminal 进程置于最前，防止焦点丢失
    set frontmost of process "Terminal" to true
    
    -- 2. 模拟按下 Command + V
    keystroke "v" using {command down}
    
    delay 0.3
    
    -- 3. 模拟按下 Return 键 (发送/执行)
    key code 36
end tell