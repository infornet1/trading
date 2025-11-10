# DeepSeek AI Assistant - Trading Project Usage Guide

## Overview

The DeepSeek CLI wrapper is now installed system-wide and can help you understand, develop, and troubleshoot this Bitcoin trading system.

---

## Quick Start

### Step 1: Configure API Key (One-Time Setup)

```bash
# IMPORTANT: First rotate your API key at https://platform.deepseek.com/api_keys
# Then run:
/opt/configure_deepseek.sh
```

### Step 2: Test the Installation

```bash
# Simple test
deepseek-python chat "Hello, are you working?"

# Test with this project
deepseek-python project /var/www/dev/trading
```

---

## Common Use Cases for This Trading Project

### 1. Understanding the Project

#### Get Overall Project Overview
```bash
deepseek-python project /var/www/dev/trading
```

**What this does:**
- Analyzes README.md and all documentation
- Identifies project type and technology stack
- Explains the ADX trading strategy
- Lists key components and architecture

#### Full Analysis with Code Review
```bash
deepseek-python project /var/www/dev/trading --full
```

**What this does:**
- Everything from basic analysis PLUS
- Reviews key Python files (live_trader.py, dashboard_web.py, etc.)
- Analyzes code quality and structure
- Provides specific improvement suggestions

---

### 2. Understanding Specific Components

#### Ask About the ADX Strategy
```bash
deepseek-python chat "Explain how the ADX trading strategy works in this project at /var/www/dev/trading"
```

#### Understand the Live Trader
```bash
deepseek-python chat "Explain what live_trader.py does in the ADX v2 strategy"
```

#### Learn About Risk Management
```bash
deepseek-python chat "How does the risk management system work in this trading bot?"
```

#### Understand the Database Schema
```bash
deepseek-python chat "Explain the database schema in /var/www/dev/trading/schema_adx_v2.sql"
```

---

### 3. Code Analysis and Review

#### Analyze a Specific File
```bash
cd /var/www/dev/trading/adx_strategy_v2

# Analyze the live trader
deepseek-python code "$(cat live_trader.py)" --language python
```

#### Review Dashboard Code
```bash
deepseek-python code "$(cat dashboard_web.py)" --language python
```

#### Analyze SQL Schema
```bash
deepseek-python code "$(cat ../schema_adx_v2.sql)" --language sql
```

---

### 4. Development Assistance

#### Add a New Feature
```bash
deepseek-python chat "I want to add Telegram notifications to my trading bot at /var/www/dev/trading/adx_strategy_v2. How should I implement this?"
```

#### Improve Existing Code
```bash
deepseek-python chat "How can I improve the error handling in live_trader.py?"
```

#### Add New Technical Indicators
```bash
deepseek-python chat "I want to add MACD indicator to complement ADX. How should I integrate it into the existing strategy?"
```

#### Optimize Performance
```bash
deepseek-python chat "How can I optimize the database queries in the trading dashboard?"
```

---

### 5. Troubleshooting

#### Debug an Error
```bash
# If you get an error, paste it:
deepseek-python chat "I'm getting 'Connection refused' error when running live_trader.py. The error is: [paste your error here]. Project location: /var/www/dev/trading"
```

#### Understand a Bug
```bash
deepseek-python chat "My trading bot is not generating signals. What could be wrong? The last signal was 6 hours ago."
```

#### Fix Database Issues
```bash
deepseek-python chat "I'm getting 'Table doesn't exist' error in MariaDB for table adx_signals. How do I fix this?"
```

#### Service Management Issues
```bash
deepseek-python chat "My systemd service for adx-trading-bot keeps restarting. How do I debug this?"
```

---

### 6. Learning and Documentation

#### Understand Trading Concepts
```bash
deepseek-python explain "ADX indicator" --context "cryptocurrency trading"
```

#### Learn About Technical Indicators
```bash
deepseek-python explain "Directional Movement Index" --context "Python trading bots"
```

#### Understand Code Patterns
```bash
deepseek-python chat "Explain how the position management works in live_trader.py"
```

---

## Practical Examples

### Example 1: Adding a New Feature

**Scenario:** You want to add stop-loss trailing functionality

```bash
deepseek-python chat "I want to add trailing stop-loss to my trading bot at /var/www/dev/trading/adx_strategy_v2. Currently, I have fixed stop-loss in place_stop_loss.py. How should I implement trailing stops?"
```

**Expected Response:**
- Explanation of trailing stop-loss concept
- Code modifications needed in place_stop_loss.py
- Database schema updates required
- Risk management considerations
- Testing recommendations

---

### Example 2: Understanding a Complex File

**Scenario:** You need to understand how live_trader.py works

```bash
# Get overview
deepseek-python chat "Explain the main workflow in /var/www/dev/trading/adx_strategy_v2/live_trader.py"

# Deep dive
deepseek-python code "$(cat /var/www/dev/trading/adx_strategy_v2/live_trader.py)" --language python
```

---

### Example 3: Debugging Production Issues

**Scenario:** Trading bot stopped generating signals

```bash
deepseek-python chat "My trading bot hasn't generated signals in 6 hours. Current BTC price moved from $106,000 to $110,000. The ADX strategy should have triggered. What could be wrong?

Context:
- Project: /var/www/dev/trading/adx_strategy_v2
- Service status: Running (systemd active)
- No errors in logs
- Database connection OK
- BingX API working"
```

---

### Example 4: Code Review Before Deployment

**Scenario:** You modified risk management code and want review

```bash
# First, show the modified code
deepseek-python code "$(cat /var/www/dev/trading/adx_strategy_v2/place_stop_loss.py)" --language python

# Then ask for specific review
deepseek-python chat "I modified place_stop_loss.py to add dynamic stop-loss based on volatility. Can you review this code for potential issues before I deploy to production?"
```

---

## Advanced Usage

### Batch Analysis

Create a script to analyze multiple files:

```bash
#!/bin/bash
# analyze_all.sh

cd /var/www/dev/trading/adx_strategy_v2

echo "Analyzing key trading components..."

for file in live_trader.py dashboard_web.py place_stop_loss.py; do
    echo "=== Analyzing $file ==="
    deepseek-python code "$(cat $file)" --language python
    echo ""
done
```

### Integration with Python Scripts

Use DeepSeek in your development workflow:

```python
#!/usr/bin/env python3
# trading_dev_helper.py

from deepseek_wrapper import DeepSeek

ds = DeepSeek()

# Ask about best practices
best_practices = ds.chat("""
What are the best practices for handling API rate limits
in a crypto trading bot that makes requests every 5 minutes?
""")

print("Best Practices for API Rate Limits:")
print(best_practices)

# Analyze code snippet
code = '''
def calculate_position_size(balance, risk_percent, stop_loss_percent):
    risk_amount = balance * (risk_percent / 100)
    position_size = risk_amount / (stop_loss_percent / 100)
    return position_size
'''

analysis = ds.process_code(code, "python")
print("\nCode Analysis:")
print(analysis)
```

---

## Tips for Effective Usage

### 1. Be Specific

❌ **Bad:** "How do I improve my code?"

✅ **Good:** "How can I improve error handling in /var/www/dev/trading/adx_strategy_v2/live_trader.py specifically for BingX API connection failures?"

### 2. Provide Context

Always mention:
- Project location: `/var/www/dev/trading`
- Specific file: `adx_strategy_v2/live_trader.py`
- What you're trying to achieve
- Any error messages (full text)

### 3. Iterative Refinement

```bash
# First, get general understanding
deepseek-python chat "Explain the ADX strategy"

# Then, ask specific questions
deepseek-python chat "In the ADX strategy, what does +DI crossing -DI mean for a LONG signal?"

# Finally, apply to your code
deepseek-python chat "Show me where in live_trader.py the +DI/-DI crossover is detected"
```

### 4. Use for Learning

```bash
# Learn concepts
deepseek-python explain "ATR indicator" --context "risk management"

# Apply to your project
deepseek-python chat "How is ATR used in /var/www/dev/trading for stop-loss calculation?"

# Verify understanding
deepseek-python chat "Can you explain the ATR calculation in the context of my trading bot's risk management?"
```

---

## Common Questions

### Q: Can DeepSeek access my trading account?
**A:** No. DeepSeek only analyzes code and provides advice. It cannot execute trades or access your accounts.

### Q: Will it understand my specific trading strategy?
**A:** Yes, if you provide context. The README.md in your project already explains the ADX strategy, so DeepSeek can reference that.

### Q: Can it help with backtesting?
**A:** Yes! Ask questions like:
```bash
deepseek-python chat "How should I implement backtesting for the ADX strategy? I want to test against historical BTC data from the past 3 months."
```

### Q: Can it help optimize parameters?
**A:** Yes! Example:
```bash
deepseek-python chat "My ADX strategy uses ADX > 25 as threshold. How can I optimize this parameter using historical data?"
```

---

## Security Considerations

### DO:
✅ Use DeepSeek to review code for security issues
✅ Ask about best practices for API key storage
✅ Get advice on secure database connections

### DON'T:
❌ Paste actual API keys in prompts
❌ Share sensitive trading credentials
❌ Copy production .env file contents

**Example of safe usage:**
```bash
deepseek-python chat "What's the best way to securely store BingX API keys in a Python trading bot?"
```

---

## Integration with Your Workflow

### Daily Development Routine

1. **Morning:** Check what changed
```bash
deepseek-python chat "I modified live_trader.py to add trailing stops. What should I test before deploying?"
```

2. **During Development:** Code review as you write
```bash
deepseek-python code "$(cat my_new_feature.py)" --language python
```

3. **Before Deployment:** Final checks
```bash
deepseek-python chat "I'm about to deploy changes to production trading bot. What pre-deployment checks should I perform?"
```

4. **Troubleshooting:** Quick debugging
```bash
deepseek-python chat "Bot stopped trading. Last log: [paste log]. What's wrong?"
```

---

## Getting Help

### For DeepSeek Installation Issues:
```bash
# Read installation guide
cat /opt/DEEPSEEK_INSTALLATION_GUIDE.md

# Test installation
/opt/test_deepseek_installation.sh
```

### For Trading Project Questions:
```bash
# Use DeepSeek!
deepseek-python chat "Your question about the trading project"
```

---

## Next Steps

1. **Configure API Key** (if not done):
   ```bash
   /opt/configure_deepseek.sh
   ```

2. **Analyze Your Project**:
   ```bash
   deepseek-python project /var/www/dev/trading --full
   ```

3. **Start Asking Questions**:
   ```bash
   deepseek-python chat "How does the ADX strategy work?"
   ```

4. **Review Code**:
   ```bash
   cd /var/www/dev/trading/adx_strategy_v2
   deepseek-python code "$(cat live_trader.py)" --language python
   ```

---

## Quick Reference

```bash
# Project analysis
deepseek-python project /var/www/dev/trading
deepseek-python project /var/www/dev/trading --full

# Documentation analysis
deepseek-python docs /var/www/dev/trading

# Ask questions
deepseek-python chat "Your question"

# Code analysis
deepseek-python code "your code" --language python

# Explain concepts
deepseek-python explain "concept" --context "trading"

# Help
deepseek-python --help
```

---

**Happy Trading Development! 🚀**

For more information:
- Installation Guide: `/opt/DEEPSEEK_INSTALLATION_GUIDE.md`
- Project README: `/var/www/dev/trading/README.md`
- Test Script: `/opt/test_trading_project_analysis.py`
