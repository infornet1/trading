# DeepSeek CLI Commands - Quick Reference

## 🎯 Quick Answer

**YES!** The `ds` command CAN help you read, analyze, and develop your Python project - you just need to feed it the file contents.

---

## 📦 Commands Available

### Basic Command
```bash
ds "your question"
```

### File Analysis Commands (NEW!)
```bash
ds-read <file>              # Read and analyze any file
ds-review <file>            # Get code review
ds-function <file> <name>   # Analyze specific function
```

---

## 🚀 Try These Right Now

```bash
cd /var/www/dev/trading

# 1. Read the README
ds-read README.md

# 2. Analyze your main trading bot
ds-read adx_strategy_v2/live_trader.py

# 3. Get code review
ds-review adx_strategy_v2/live_trader.py

# 4. Analyze database schema
ds-read schema_adx_v2.sql

# 5. Ask custom questions
ds "What improvements can I make to my trading bot?"
```

---

## 📚 Full Guides

| Guide | Location | What It Covers |
|-------|----------|----------------|
| **Quick Start** | `/var/www/dev/trading/QUICK_START_DS.md` | Start here! Try commands in 5 minutes |
| **File Access** | `/var/www/dev/trading/DS_FILE_ACCESS_GUIDE.md` | How to make `ds` read your files |
| **Complete Guide** | `/var/www/dev/trading/DS_COMMAND_GUIDE.md` | All features and workflows |
| **Usage Guide** | `/var/www/dev/trading/DEEPSEEK_USAGE_GUIDE.md` | Original comprehensive guide |

---

## 💡 Common Tasks

### Understand Code
```bash
ds-read live_trader.py
ds-read live_trader.py "Explain the main logic"
```

### Code Review
```bash
ds-review live_trader.py
```

### Debug Issues
```bash
ds "Why isn't my bot generating signals: $(journalctl -u adx-trading-bot -n 30 --no-pager)"
```

### Add Features
```bash
ds "Show me how to add Telegram notifications to my Python trading bot"
```

### Learn Concepts
```bash
ds "Explain the ADX indicator and how it generates trading signals"
```

---

## ⚡ Power User Tips

```bash
# Read specific lines
ds "Analyze: $(sed -n '100,150p' file.py)"

# Extract function
ds "Review: $(grep -A 30 'def my_function' file.py)"

# Compare files
ds "What changed: OLD=$(git show HEAD~1:file.py) NEW=$(cat file.py)"

# Multiple files
ds "How do these work together: $(cat file1.py) and $(cat file2.py)"
```

---

## 🎓 Learning Path

1. **Start Here** → `QUICK_START_DS.md`
2. **Learn File Access** → `DS_FILE_ACCESS_GUIDE.md`
3. **Master It** → `DS_COMMAND_GUIDE.md`

---

## 🆘 Need Help?

```bash
# Ask ds itself!
ds "How can I use the ds command to analyze my Python trading bot?"
```

---

## ✅ What You Can Do

| Task | Possible? | How |
|------|-----------|-----|
| Read files | ✅ YES | `ds-read file.py` or `ds "$(cat file.py)"` |
| Analyze code | ✅ YES | `ds-review file.py` |
| Modify files | ⚠️ MANUAL | `ds` suggests code, you apply it |
| Debug errors | ✅ YES | `ds "error: $(logs)"` |
| Learn concepts | ✅ YES | `ds "explain ADX"` |
| Get code examples | ✅ YES | `ds "show me how to..."` |

---

**Start now:**

```bash
cd /var/www/dev/trading
ds-read README.md
```
