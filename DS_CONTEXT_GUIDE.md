# Understanding `ds` Context and Memory

## ❌ **Short Answer: NO - `ds` Does NOT Remember Previous Questions**

Each `ds` command is a **completely independent** API call with **no memory** of previous conversations.

---

## 🧪 **Proof Test:**

```bash
ds "My name is John"
# Response: "Nice to meet you, John!"

ds "What is my name?"
# Response: "I don't have access to your name"
```

**Each command starts fresh** - like talking to someone with amnesia after every sentence.

---

## 🔍 **Why This Happens:**

The `ds` command:
1. Takes your question
2. Sends it to DeepSeek API
3. Gets a response
4. Displays it
5. **Forgets everything** ← This is the key point

No conversation history is stored anywhere.

---

## ✅ **Solution: Provide Context in EVERY Question**

### ❌ **Won't Work:**
```bash
ds "I'm building a trading bot"
ds "How do I add stop-loss?"  # ← Doesn't know about trading bot
ds "What about take-profit?"   # ← Doesn't know about anything
```

### ✅ **Will Work:**
```bash
# Include context every time
ds "I'm building a Bitcoin trading bot. How do I add stop-loss?"
ds "I'm building a Bitcoin trading bot. How do I add take-profit?"
```

---

## 💡 **Best Practices**

### Method 1: Set a Context Variable

```bash
# Define your context once
CONTEXT="I'm developing a Bitcoin trading bot using Python with ADX strategy at /var/www/dev/trading"

# Use it in every question
ds "$CONTEXT. How do I add Telegram notifications?"
ds "$CONTEXT. Why aren't signals being generated?"
ds "$CONTEXT. Review this code: $(cat live_trader.py | head -50)"
```

### Method 2: Create Project-Specific Alias

```bash
# Add to ~/.bashrc
alias ds-trading='ds "Context: Bitcoin ADX trading bot at /var/www/dev/trading. Question:"'

# Then use
ds-trading "How do I improve performance?"
ds-trading "Debug this error: ..."
```

### Method 3: Include Context in Question

```bash
# Always mention what you're working on
ds "In my Python trading bot project, how do I add error logging?"

# Not just
ds "How do I add error logging?"  # ← Too vague, no context
```

---

## 🎯 **Practical Examples**

### Example 1: Development Session

```bash
# Start with full context
ds "I'm working on a Bitcoin trading bot at /var/www/dev/trading.
The bot uses ADX strategy.
Current issue: No signals generated in 6 hours.
BTC moved from $106k to $110k (+3.8%).
What could be wrong?"

# Next question - include context again
ds "Same Bitcoin ADX bot.
How do I verify the ADX calculation is correct?
Show me how to manually calculate ADX for debugging."

# Another question
ds "Bitcoin ADX bot at /var/www/dev/trading.
I want to add trailing stop-loss.
Here's my current stop-loss code: $(grep -A 20 'def set_stop_loss' live_trader.py)
How do I modify it?"
```

### Example 2: Code Review Session

```bash
# First review
ds "Review this Python trading bot code for bugs:
$(cat adx_strategy_v2/live_trader.py | head -100)"

# Follow-up (need to repeat context)
ds "This is from a Python trading bot (same file as before).
You mentioned there's a risk of division by zero in line 145.
Show me the corrected code for that section:
$(sed -n '140,150p' adx_strategy_v2/live_trader.py)"
```

---

## 🛠️ **Helper Script Created: `dsc`**

I created a **context-aware wrapper** called `dsc` (DeepSeek with Context), but it has limitations:

```bash
# Try the context version
dsc "My name is Bob"
dsc "What's my name?"  # Attempts to remember

# Clear context
dsc --clear

# Show history
dsc --show
```

**NOTE:** This only works **within the same terminal session** and has limitations due to API constraints.

---

## 📋 **Comparison:**

| Feature | `ds` | `dsc` |
|---------|------|-------|
| **Speed** | Fast | Slower (sends more text) |
| **Memory** | None | Limited (same session only) |
| **Reliability** | High | Medium (context may confuse AI) |
| **Use case** | Independent questions | Multi-question debugging |

---

## 💡 **When to Use Each:**

### Use `ds` (no context) for:
- Independent questions
- Code reviews
- Learning concepts
- Quick lookups

```bash
ds "What is the ADX indicator?"
ds "Show Python asyncio example"
ds-read README.md
```

### Use `dsc` (with context) for:
- Debugging sessions (multiple related questions)
- Step-by-step tutorials
- Iterative code improvement

```bash
dsc "I'm debugging my trading bot"
dsc "The error is about database connection"
dsc "Show me the fix"
dsc --clear  # When done
```

### Best Approach: Manual Context

**Most reliable:** Include context in every question

```bash
PROJ="Bitcoin trading bot at /var/www/dev/trading with ADX strategy"

ds "$PROJ. Question: How do I add logging?"
ds "$PROJ. Question: Why no signals in 6 hours?"
ds "$PROJ. Question: Optimize this code: $(cat file.py)"
```

---

## 🎓 **Key Takeaways**

1. ❌ **`ds` has NO memory** between commands
2. ✅ **Include context in EVERY question**
3. 💡 **Use variables** to avoid retyping context
4. 🔄 **`dsc` attempts context** but is limited
5. 📝 **Be explicit** - assume AI knows nothing from before

---

## 📚 **Examples for Your Trading Bot:**

### Good Context Examples:

```bash
# Excellent - full context
ds "I'm working on /var/www/dev/trading Bitcoin trading bot.
Uses ADX strategy, Python, MariaDB, BingX API.
Current issue: [your issue]
How do I fix it?"

# Good - enough context
ds "In my Python trading bot, how do I add Telegram notifications?"

# Okay - some context
ds "Trading bot: add error handling to this: $(cat file.py)"
```

### Bad Context Examples:

```bash
# Bad - no context
ds "How do I fix this?"

# Bad - assumes memory from previous command
ds "I'm working on a trading bot"
ds "How do I improve it?"  # ← Doesn't remember trading bot

# Bad - too vague
ds "My bot isn't working"
```

---

## ✅ **Recommended Workflow:**

```bash
# 1. Define your project context
export MY_PROJECT="Bitcoin ADX trading bot at /var/www/dev/trading. Python, MariaDB, BingX API."

# 2. Create a helper function in ~/.bashrc
ds-project() {
    ds "$MY_PROJECT. $*"
}

# 3. Use it
ds-project "How do I add Telegram alerts?"
ds-project "Debug this: $(cat error.log)"
ds-project "Review: $(cat live_trader.py | head -100)"
```

---

## 🆘 **TL;DR**

**Question:** Does `ds` remember previous questions?

**Answer:** **NO** - Each `ds` command is independent.

**Solution:** Include context in EVERY question, or use a bash variable to store your project context.

---

**Example Session:**

```bash
# Set context once
CTX="Working on /var/www/dev/trading Bitcoin trading bot"

# Use in all questions
ds "$CTX. How do I add logging?"
ds "$CTX. Optimize this: $(cat file.py)"
ds "$CTX. Debug error: [paste error]"
```

This is the most reliable approach! 🎯
