-- *****************************************************************
-- ** AI Chat Broadcaster for Chrome                              **
-- ** Function: Focus input field, expand snippet, wait for      **
-- ** button activation, then automatically click send           **
-- ** Customizable: All delay parameters and target URLs can     **
-- ** be modified to suit different hardware and requirements    **
-- *****************************************************************

-- Main script execution
-- 动态读取目标 URL（从 api_config.json）
set scriptPath to POSIX path of (path to me)
set projectRoot to do shell script "dirname " & quoted form of scriptPath & " | xargs dirname"
set targetURLs to paragraphs of (do shell script "python3 " & quoted form of (projectRoot & "/applescript/read_target_urls.py") & " " & quoted form of (projectRoot & "/api_config.json"))

tell application "Google Chrome"
    -- 1. Activate Chrome browser
    activate
    
    -- 2. Collect all eligible AI chat pages
    -- CUSTOMIZABLE: Add or remove URLs in the condition below to target specific AI platforms
    set aiPages to {}
    try
        repeat with w_index from 1 to (count of windows)
            repeat with t_index from 1 to (count of tabs of window w_index)
                set tabURL to URL of tab t_index of window w_index
                -- CUSTOMIZABLE: Modify this condition to target specific AI platforms
                set urlMatched to false
                repeat with aURL in targetURLs
                    if tabURL contains aURL then
                        set urlMatched to true
                        exit repeat
                    end if
                end repeat
                if urlMatched then
                    set end of aiPages to {win:w_index, tab:t_index}
                end if
            end repeat
        end repeat
    on error
        -- Ignore errors when retrieving URLs
    end try
    
    if (count of aiPages) is 0 then
        display notification "没有找到符合条件的AI聊天页面。" with title "执行终止"
        return "No AI pages found."
    end if
    
    -- 3. 依次处理每一个找到的AI页面
    repeat with pageInfo in aiPages
        try
            -- 激活目标标签页
            set win_idx to win of pageInfo
            set tab_idx to tab of pageInfo
            tell window win_idx
                set active tab index to tab_idx
                set index to 1
            end tell
            
            -- Ensure Chrome is in foreground
            tell application "System Events" to set frontmost of process "Google Chrome" to true
            delay 0.02 -- CUSTOMIZABLE: Window switching delay (adjust for slower systems)
            
            -- 4. Use JavaScript to focus input field
            -- CUSTOMIZABLE: Add selectors for additional AI platforms
            tell tab tab_idx of window win_idx
                execute javascript "
                    var el = document.querySelector('.ql-editor, #prompt-textarea, textarea:not([readonly]), div[contenteditable=\"true\"]');
                    if (el) {
                        el.focus();
                        el.click();
                        if (el.value !== undefined) { el.value = ''; } else { el.textContent = ''; }
                        el.focus();
                    }
                "
            end tell
            
            delay 0.1 -- CUSTOMIZABLE: JavaScript focus optimization delay
            
            -- 5. Use system-level keystrokes for input and expansion
            tell application "System Events"
                keystroke "-geticard" -- CUSTOMIZABLE: Change to match your Alfred snippet keyword
                delay 0.075 -- CUSTOMIZABLE: Critical workflow balance interval
            end tell
            
            delay 0.2 -- CUSTOMIZABLE: Snippet expansion wait time
            
            -- 6. Use JavaScript with intelligent waiting to find and click send button
            -- CUSTOMIZABLE: Add selectors for additional AI platforms
            tell tab tab_idx of window win_idx
                execute javascript "
                    var sendButtonSelectors = [
                        'button[aria-label=\"Run\"]',                  // Google AI Studio
                        'button[data-testid=\"send-button\"]',           // ChatGPT
                        'button[aria-label=\"Send message\"]',         // Gemini
                        'button[aria-label=\"Send Message\"]',         // Claude
                        'button[type=\"submit\"]:not([disabled])',       // lmarena.ai
                        'button.btn-widget[type=\"submit\"]',            // Generic widget button
                        'button[class*=\"send\"]'                        // Generic buttons with 'send' in class
                    ];

                    function tryClickSendButton() {
                        for (var i = 0; i < sendButtonSelectors.length; i++) {
                            var btn = document.querySelector(sendButtonSelectors[i]);
                            // Confirm button exists and is not disabled
                            if (btn && !btn.disabled) {
                                btn.click();
                                return true; // Successful click
                            }
                        }
                        return false; // Not found or still disabled
                    }

                    // CUSTOMIZABLE: Retry interval (50ms) and max retries (20 = 1 second)
                    var retries = 0;
                    var maxRetries = 20;
                    var interval = setInterval(function() {
                        if (tryClickSendButton() || retries >= maxRetries) {
                            clearInterval(interval);
                        }
                        retries++;
                    }, 50);
                "
            end tell
            
            delay 0.03 -- CUSTOMIZABLE: Post-send completion delay
            
        on error errMsg
            -- Ignore errors that may occur when processing individual pages
        end try
        
        -- CUSTOMIZABLE: Inter-page interval for optimal performance balance
        delay 0.18 -- Critical balance point to avoid workflow conflicts
    end repeat
    
    display notification "Attempted to send on " & (count of aiPages) & " pages." with title "Task Completed"
end tell

return "Script finished successfully."