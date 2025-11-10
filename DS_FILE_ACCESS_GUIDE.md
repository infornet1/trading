# How to Make `ds` Read, Analyze, and Help Modify Your Project Files

## 🔑 Key Understanding

The `ds` command **CANNOT directly access your files**, but you **CAN feed file contents to it** using bash commands!

---

## 📖 New Helper Commands Created

### 1. `ds-read` - Read and Analyze Files

```bash
# Basic usage
ds-read <file> [optional question]

# Examples
ds-read live_trader.py
ds-read live_trader.py "Explain the main logic"
ds-read schema_adx_v2.sql "What tables are defined?"
```

### 2. `ds-review` - Code Review

```bash
# Get comprehensive code review
ds-review <file>

# Examples
cd /var/www/dev/trading/adx_strategy_v2
ds-review live_trader.py
ds-review dashboard_web.py
```

### 3. `ds-function` - Analyze Specific Functions

```bash
# Analyze a specific function
ds-function <file> <function_name>

# Examples
ds-function live_trader.py calculate_position_size
ds-function dashboard_web.py update_dashboard
```

---

## 🛠️ Manual Methods (More Control)

### Method 1: Read Entire Files

```bash
cd /var/www/dev/trading

# Read and analyze
ds "Analyze this Python file: $(cat adx_strategy_v2/live_trader.py)"

# For large files, read first N lines
ds "Explain this code: $(head -100 adx_strategy_v2/live_trader.py)"

# Read specific sections
ds "What does this code do: $(sed -n '50,100p' adx_strategy_v2/live_trader.py)"
```

### Method 2: Extract Specific Parts

```bash
# Extract a function
ds "Review this function: $(grep -A 30 'def calculate_position_size' live_trader.py)"

# Extract a class
ds "Explain this class: $(grep -A 50 'class PositionManager' live_trader.py)"

# Extract imports
ds "Are these imports correct: $(head -20 live_trader.py | grep import)"
```

### Method 3: Compare Files

```bash
# Compare two versions
ds "What changed between these files:

OLD VERSION:
$(git show HEAD~1:live_trader.py | head -50)

NEW VERSION:
$(head -50 live_trader.py)"
```

### Method 4: Analyze Multiple Files

```bash
# Show relationship between files
ds "Explain how these files work together:

live_trader.py:
$(head -30 live_trader.py)

dashboard_web.py:
$(head -30 dashboard_web.py)"
```

---

## 📁 Project Structure Analysis

### Show Directory Structure

```bash
# Analyze project layout
ds "Based on this structure, what type of project is this: $(ls -la)"

# Deeper analysis
ds "Analyze this project structure: $(tree -L 3 || find . -maxdepth 3 -type d)"

# File organization
ds "Is this a well-organized project: $(ls -R)"
```

---

## 🔧 Practical Examples for Your Trading Bot

### Example 1: Understand Main Trading Logic

```bash
cd /var/www/dev/trading/adx_strategy_v2

# Quick overview
ds-read live_trader.py

# Specific question
ds-read live_trader.py "How does this bot decide when to open a trade?"

# Deep dive
ds "Analyze the trading logic in detail: $(cat live_trader.py | grep -A 100 'def check_signals')"
```

### Example 2: Review Database Schema

```bash
cd /var/www/dev/trading

# Analyze schema
ds-read schema_adx_v2.sql "Explain each table and its purpose"

# Check relationships
ds "What are the relationships between tables: $(cat schema_adx_v2.sql)"
```

### Example 3: Debug Configuration

```bash
# Review config
ds "Is this configuration correct for production: $(cat config.json)"

# Security check
ds "Check for security issues in this config: $(cat adx_strategy_v2/config/.env.example)"
```

### Example 4: Analyze Error Logs

```bash
# Get error analysis
ds "What's wrong based on these logs: $(journalctl -u adx-trading-bot.service -n 50 --no-pager)"

# Specific error
ds "Debug this error: $(grep -A 10 'ERROR' logs/trading.log | tail -20)"
```

---

## 📝 Modifying Files with `ds` Help

While `ds` **cannot directly modify files**, it can **generate code for you to paste**:

### Workflow for Modifications:

#### 1. Get Current Code
```bash
ds-read live_trader.py "Show me the calculate_position_size function"
```

#### 2. Ask for Modified Version
```bash
ds "Modify this function to add trailing stop-loss:

$(grep -A 30 'def calculate_position_size' live_trader.py)

Show me the complete modified function."
```

#### 3. Apply Changes
- DeepSeek gives you the new code
- You copy and paste it into the file
- Or save to a new file and compare

```bash
# Save AI's suggestion
ds "Improve this function: $(cat my_function.py)" > my_function_improved.py

# Compare
diff my_function.py my_function_improved.py
```

---

## 🚀 Advanced Workflows

### Workflow 1: Complete Feature Addition

```bash
# Step 1: Understand current implementation
ds-read live_trader.py "How does the bot currently handle stop-loss?"

# Step 2: Get requirements
ds "I want to add trailing stop-loss. What do I need to change in this file: $(head -200 live_trader.py)"

# Step 3: Get specific code
ds "Show me the exact code to add trailing stop-loss to this function: $(grep -A 40 'def manage_positions' live_trader.py)"

# Step 4: Review before applying
ds "Review this modified code for bugs: [paste the code DeepSeek gave you]"

# Step 5: Apply manually
nano live_trader.py  # paste the changes
```

### Workflow 2: Refactoring

```bash
# Analyze current structure
ds-review live_trader.py

# Get refactoring suggestions
ds "This file is 800 lines. Suggest how to split it into modules: $(cat live_trader.py)"

# Get specific module code
ds "Create a separate risk_manager.py module with this code: $(grep -A 100 'def calculate_risk' live_trader.py)"
```

### Workflow 3: Bug Fixing

```bash
# Find the bug
ds "There's a bug in this code where positions aren't closing. Debug it: $(grep -A 50 'def close_position' live_trader.py)"

# Get fix
ds "Provide the corrected version of this buggy function: [paste function]"

# Verify fix
ds "Will this fix work? Review: [paste corrected code]"
```

---

## 📊 Real Examples You Can Try Now

### Example 1: Analyze Your Main Bot

```bash
cd /var/www/dev/trading/adx_strategy_v2

# What does it do?
ds-read live_trader.py

# How does it work?
ds "Explain the main workflow of this bot: $(head -200 live_trader.py)"

# What can improve?
ds-review live_trader.py
```

### Example 2: Understand Database

```bash
cd /var/www/dev/trading

# Schema analysis
ds-read schema_adx_v2.sql "Create a visual diagram description of this database schema"

# Check for optimization
ds "Can this schema be optimized: $(cat schema_adx_v2.sql)"
```

### Example 3: Security Audit

```bash
# Check main file
ds-review live_trader.py

# Check config security
ds "Security audit this configuration: $(cat config.json)"

# Check API key handling
ds "Is the API key handled securely: $(grep -A 10 'API_KEY' adx_strategy_v2/*.py)"
```

---

## 💡 Pro Tips

### Tip 1: Handle Large Files

```bash
# For files >1000 lines, analyze in sections
ds "Analyze the imports and configuration: $(head -50 large_file.py)"
ds "Analyze the main logic: $(sed -n '100,200p' large_file.py)"
ds "Analyze the helper functions: $(tail -100 large_file.py)"
```

### Tip 2: Use with Git

```bash
# Review changes before commit
ds "Review these changes: $(git diff)"

# Understand old code
ds "Explain what this old version did: $(git show HEAD~5:live_trader.py | head -100)"

# Generate commit message
ds "Generate a commit message for these changes: $(git diff --staged)"
```

### Tip 3: Create Project Documentation

```bash
# Auto-generate docs
ds "Create documentation for this module: $(cat live_trader.py)" > docs/live_trader.md

# Create API reference
ds "Create API reference for these functions: $(grep 'def ' live_trader.py)"
```

---

## ⚡ Quick Reference

```bash
# Read file
ds-read <file>

# Code review
ds-review <file>

# Analyze function
ds-function <file> <function_name>

# Custom analysis
ds "your question: $(cat file.py)"

# Extract specific parts
ds "analyze: $(grep -A 20 'pattern' file.py)"

# Compare files
ds "compare: old=$(cat old.py) new=$(cat new.py)"
```

---

## 🎯 Your Next Steps

1. **Try the commands:**
```bash
cd /var/www/dev/trading
ds-read README.md
ds-review adx_strategy_v2/live_trader.py
```

2. **Analyze your code:**
```bash
ds-read adx_strategy_v2/live_trader.py "What are the main functions?"
```

3. **Get improvement suggestions:**
```bash
ds "How can I improve this project: $(ls -la)"
```

---

## ✅ Summary

| What You Want | Command |
|---------------|---------|
| Read and analyze file | `ds-read file.py` |
| Code review | `ds-review file.py` |
| Analyze function | `ds-function file.py function_name` |
| Custom question | `ds "question: $(cat file.py)"` |
| Extract parts | `ds "question: $(grep pattern file.py)"` |
| Multiple files | `ds "question: $(cat file1.py) $(cat file2.py)"` |

**Remember:** `ds` doesn't modify files directly - it helps you understand and generates code that YOU apply manually!

---

**Start using it now!**

```bash
cd /var/www/dev/trading
ds-read README.md "Summarize this project"
```
