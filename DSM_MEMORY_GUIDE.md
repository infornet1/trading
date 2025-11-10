# dsm - DeepSeek with Memory 🧠

## ✅ **YES! We Now Have Working Conversation Memory!**

The `dsm` command maintains **true conversation context** across multiple questions!

---

## 🎯 **What Makes `dsm` Different:**

| Feature | `ds` | `dsm` (NEW!) |
|---------|------|--------------|
| **Memory** | ❌ None | ✅ **Full memory** |
| **Context** | ❌ Each Q independent | ✅ **Remembers everything** |
| **Conversations** | ❌ Single | ✅ **Multiple separate** |
| **Sessions** | ❌ Lost on close | ✅ **Persistent** |
| **Speed** | Fast | Slightly slower |

---

## 🚀 **Quick Start:**

### **Basic Usage (Default Conversation):**

```bash
# First question
dsm "My name is Alice and I work on Bitcoin trading"

# Second question - IT REMEMBERS!
dsm "What is my name and what do I work on?"
# Response: "Your name is Alice and you work on Bitcoin trading"
```

### **Multiple Conversations:**

```bash
# Trading conversation
dsm -c trading "I have a Bitcoin bot with ADX strategy"
dsm -c trading "How do I improve it?"  # Remembers the bot!

# Cooking conversation (separate)
dsm -c cooking "I love making pasta"
dsm -c cooking "Give me a recipe"  # Remembers pasta!

# Back to trading
dsm -c trading "What strategy does my bot use?"  # Still remembers ADX!
```

---

## 📖 **Complete Usage:**

### **Command Format:**

```bash
# Default conversation
dsm "your question"

# Named conversation
dsm -c <conversation_name> "your question"

# Interactive mode
dsm -i [conversation_name]

# Show history
dsm -h [conversation_name]

# List all conversations
dsm -l

# Clear conversation
dsm -x [conversation_name]
```

---

## 💡 **Practical Examples:**

### **Example 1: Trading Bot Development**

```bash
# Start a trading project conversation
dsm -c trading "I'm developing a Bitcoin trading bot at /var/www/dev/trading"

# Ask follow-ups (all remember context!)
dsm -c trading "The bot uses ADX strategy with 5-minute timeframe"
dsm -c trading "Current issue: no signals in 6 hours"
dsm -c trading "BTC moved from $106k to $110k"
dsm -c trading "What could be wrong?"

# Later (even after closing terminal)
dsm -c trading "Remind me what issue I was facing"
# It remembers everything!
```

### **Example 2: Multiple Projects**

```bash
# Project 1
dsm -c project1 "This is a Flask web app"
dsm -c project1 "Uses PostgreSQL database"
dsm -c project1 "How do I add authentication?"

# Project 2
dsm -c project2 "This is a Django REST API"
dsm -c project2 "Uses MongoDB"
dsm -c project2 "How do I add authentication?"

# Each gets contextual answers!
```

### **Example 3: Interactive Chat**

```bash
# Start interactive mode
dsm -i trading

# Then chat naturally:
👤 You: I'm working on a Bitcoin bot
🤖 AI: Great! Tell me more about it...

👤 You: It uses ADX strategy
🤖 AI: ADX is excellent for trend following...

👤 You: How do I add trailing stop-loss?
🤖 AI: For your ADX Bitcoin bot, here's how...
# (Remembers it's Bitcoin + ADX!)

# Special commands:
👤 You: history        # Show conversation
👤 You: clear          # Clear memory
👤 You: exit           # Quit
```

---

## 🎯 **Use Cases:**

### **Use Case 1: Debugging Session**

```bash
dsm -c debug "My trading bot has an error"
dsm -c debug "Error message: 'Connection timeout'"
dsm -c debug "It happens when fetching BTC price"
dsm -c debug "Using BingX API"
dsm -c debug "Show me the fix"
# All context accumulated for better answer!
```

### **Use Case 2: Learning Journey**

```bash
dsm -c learning "What is the ADX indicator?"
dsm -c learning "How is it calculated?"
dsm -c learning "What's the difference between ADX and RSI?"
dsm -c learning "Which is better for crypto?"
# Builds on previous answers!
```

### **Use Case 3: Code Development**

```bash
dsm -c feature "I want to add Telegram notifications"
dsm -c feature "My bot is in Python"
dsm -c feature "Show me the code"
dsm -c feature "How do I handle errors?"
dsm -c feature "Add rate limiting"
# Each answer builds on the previous!
```

---

## 🔧 **Technical Details:**

### **How It Works:**

1. **Conversation Storage**: Each conversation is stored as a JSON file in `~/.deepseek_conversations/`
2. **Message History**: Maintains up to 10 exchanges (20 messages: 10 user + 10 assistant)
3. **API Integration**: Sends full message history with each request
4. **Persistent**: Survives terminal restarts, reboots, etc.

### **Storage Location:**

```bash
# View stored conversations
ls -la ~/.deepseek_conversations/

# Example:
# default.json      - Default conversation
# trading.json      - Trading conversation
# debug.json        - Debug conversation
```

### **Message Format:**

```json
[
  {"role": "user", "content": "My name is Alice"},
  {"role": "assistant", "content": "Nice to meet you, Alice!"},
  {"role": "user", "content": "What is my name?"},
  {"role": "assistant", "content": "Your name is Alice"}
]
```

---

## 📊 **Comparison with Other Tools:**

| Feature | `ds` | `dsc` | `dsm` |
|---------|------|-------|-------|
| **Memory** | ❌ None | ⚠️ Session only | ✅ **Persistent** |
| **Multiple conversations** | ❌ No | ❌ No | ✅ **Yes** |
| **Survives restart** | ❌ No | ❌ No | ✅ **Yes** |
| **Interactive mode** | ❌ No | ❌ No | ✅ **Yes** |
| **History viewing** | ❌ No | ❌ No | ✅ **Yes** |
| **Speed** | Fast | Medium | Slightly slower |
| **API calls** | Direct | Direct | Direct |

---

## 🎨 **Interactive Mode Details:**

```bash
# Start interactive chat
dsm -i trading

# You'll see:
💬 Interactive mode (Conversation: 'trading')
Commands: 'exit' to quit, 'history' to show history, 'clear' to clear
============================================================

👤 You: _
```

### **Interactive Commands:**

- **Type normally**: Chat with AI
- **`history`**: Show conversation history
- **`clear`**: Clear current conversation
- **`exit`**, **`quit`**, **`q`**: Exit interactive mode

---

## 💾 **Managing Conversations:**

### **View All Conversations:**

```bash
dsm -l

# Output:
📝 Available conversations:
  - default (3 exchanges)
  - trading (7 exchanges)
  - debug (2 exchanges)
```

### **View Conversation History:**

```bash
# Default conversation
dsm -h

# Specific conversation
dsm -h trading

# Output:
📜 Conversation 'trading' history:
============================================================

👤 You:
I'm developing a Bitcoin trading bot at /var/www/dev/trading
----------------------------------------

🤖 AI:
Great! Bitcoin trading bots are fascinating projects...
----------------------------------------
```

### **Clear Conversations:**

```bash
# Clear default conversation
dsm -x

# Clear specific conversation
dsm -x trading

# Output:
✅ Cleared conversation 'trading'
```

---

## 🚀 **Best Practices:**

### **1. Use Named Conversations for Different Topics:**

```bash
# Don't mix topics in one conversation
❌ dsm "How do I fix my bot?"
❌ dsm "What's a good pasta recipe?"  # AI confused!

# Use separate conversations
✅ dsm -c bot "How do I fix my bot?"
✅ dsm -c cooking "What's a good pasta recipe?"
```

### **2. Clear When Starting New Topics:**

```bash
# When done with debugging
dsm -x debug

# Start fresh debugging session
dsm -c debug "New issue: bot won't start"
```

### **3. Use Interactive Mode for Long Sessions:**

```bash
# Instead of:
dsm -c trading "Question 1"
dsm -c trading "Question 2"
dsm -c trading "Question 3"

# Use interactive:
dsm -i trading
# Then type questions naturally
```

### **4. Check History Before Continuing:**

```bash
# If you forgot where you left off
dsm -h trading

# Then continue
dsm -c trading "Based on what we discussed, how do I..."
```

---

## ⚡ **Performance Tips:**

### **Memory Limit:**

- **Default**: Keeps last 10 exchanges (20 messages)
- **Why**: Balance between context and API cost/speed
- **Older messages**: Automatically removed

### **When to Clear:**

```bash
# Clear when:
# - Switching to unrelated topic
# - Conversation getting too long (>10 exchanges)
# - AI seems confused by old context
# - Starting fresh debugging session

dsm -x conversation_name
```

---

## 🐛 **Troubleshooting:**

### **Problem: AI doesn't remember context**

```bash
# Check if conversation exists
dsm -l

# View history
dsm -h conversation_name

# If empty, make sure you're using same conversation name
dsm -c trading "First message"
dsm -c trading "Second message"  # Must use same name!
```

### **Problem: Conversation too long/slow**

```bash
# Clear old messages
dsm -x conversation_name

# Start fresh
dsm -c conversation_name "New question"
```

### **Problem: API errors**

```bash
# Check API balance
ds "test"  # Use simple ds to test API

# If balance issue, check DeepSeek dashboard
# If works with ds but not dsm, check conversation file:
cat ~/.deepseek_conversations/conversation_name.json
```

---

## 📋 **Quick Reference Card:**

```bash
# BASIC USAGE
dsm "question"                    # Default conversation
dsm -c name "question"            # Named conversation

# INTERACTIVE
dsm -i [name]                     # Start chat

# MANAGEMENT
dsm -l                            # List all
dsm -h [name]                     # Show history
dsm -x [name]                     # Clear conversation

# EXAMPLES
dsm "My name is Alice"
dsm "What is my name?"            # Remembers!

dsm -c bot "I have a Python bot"
dsm -c bot "How do I add logging?" # Remembers bot!
```

---

## 🎯 **Real-World Workflow Example:**

### **Scenario: Debugging Bitcoin Trading Bot**

```bash
# Day 1: Start debugging session
dsm -c botdebug "My Bitcoin bot at /var/www/dev/trading stopped generating signals"
dsm -c botdebug "It uses ADX strategy with 5-min timeframe"
dsm -c botdebug "Last signal was 6 hours ago"
dsm -c botdebug "BTC moved from $106k to $110k in that time"

# Response suggests checking ADX threshold settings

dsm -c botdebug "The ADX threshold is set to 25, is that too high?"
# Get detailed answer about ADX thresholds for crypto

# Day 2: Continue where you left off (even after reboot!)
dsm -c botdebug "I lowered ADX threshold to 20, still no signals"
# AI remembers entire context from yesterday!

dsm -c botdebug "Can you show me how to add debug logging?"
# AI provides code specific to your ADX bot

# View full conversation
dsm -h botdebug

# When issue resolved, clear for next debugging session
dsm -x botdebug
```

---

## ✅ **Summary:**

### **What `dsm` Gives You:**

✅ **True memory** - Remembers everything in a conversation
✅ **Multiple conversations** - Keep different topics separate
✅ **Persistent** - Survives terminal/system restarts
✅ **Interactive mode** - Natural chat experience
✅ **History management** - View and clear conversations
✅ **Easy to use** - Same simple syntax as `ds`

### **When to Use:**

- **Use `dsm`** when you need context/memory across questions
- **Use `ds`** for quick one-off questions
- **Use `dsm -i`** for long interactive sessions

---

## 🎉 **You're Ready!**

Start using `dsm` now for conversations that remember context!

```bash
# Test it right now:
dsm "My name is [YOUR NAME] and I work on Bitcoin trading"
dsm "What is my name and what do I work on?"

# It will remember! 🎉
```

---

**For more help:**
- General usage: `/var/www/dev/trading/DS_COMMAND_GUIDE.md`
- File access: `/var/www/dev/trading/DS_FILE_ACCESS_GUIDE.md`
- CLI status: `/var/www/dev/trading/CLI_STATUS_REPORT.md`