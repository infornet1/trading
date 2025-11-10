# Using `ds` Command for Trading Bot Development

## Overview

The `ds` command is your AI assistant for understanding, developing, and troubleshooting your Bitcoin trading bot at `/var/www/dev/trading`.

---

## 1. Understanding Your Project

### Get Project Overview

First, read the README to understand the context:

```bash
cd /var/www/dev/trading
cat README.md | head -100

# Then ask DeepSeek to explain it
ds "I have a Bitcoin trading bot with ADX v2.0 strategy. The README shows it's live trading with systemd services. Explain what this project does."
```

### Understand Specific Components

```bash
# Understand the ADX strategy
ds "Explain the ADX (Average Directional Index) strategy for Bitcoin trading. How does it use +DI, -DI, and trend strength?"

# Understand the database schema
ds "Explain this SQL schema and what each table is for: $(cat schema_adx_v2.sql | head -50)"

# Understand the live trader
ds "What should a live_trader.py file do in a cryptocurrency trading bot? What are the key components?"
```

---

## 2. Code Analysis

### Analyze Specific Files

```bash
cd /var/www/dev/trading/adx_strategy_v2

# Analyze the main trading logic
ds "Analyze this Python code and explain what it does: $(cat live_trader.py | head -100)"

# Get a full code review
ds "Review this trading bot code for bugs, security issues, and improvements: $(cat live_trader.py)"

# Understand the dashboard
ds "Explain what this Flask dashboard code does: $(cat dashboard_web.py | head -80)"
```

### Analyze Small Code Snippets

```bash
# For specific functions (use grep to extract)
ds "Explain this function: $(grep -A 20 'def calculate_position_size' live_trader.py)"

# For specific classes
ds "What does this class do: $(grep -A 30 'class PositionManager' live_trader.py)"
```

---

## 3. Development Help

### Adding New Features

```bash
# Add Telegram notifications
ds "I want to add Telegram notifications to my Bitcoin trading bot. The bot is in Python and currently sends email alerts. Show me how to integrate python-telegram-bot library."

# Add new indicator
ds "How do I add the MACD indicator to complement my ADX strategy? I'm using Python with technical analysis. Show me the calculation and integration."

# Add trailing stop-loss
ds "I have a fixed stop-loss in my trading bot. How do I implement a trailing stop-loss that moves up as price increases? Show Python code example."

# Add WebSocket for real-time data
ds "My bot currently polls the BingX API every 5 minutes. How can I use WebSockets for real-time price updates? Show Python example with BingX."
```

### Improving Existing Code

```bash
# Optimize database queries
ds "I have this SQL query that runs every minute: $(grep -A 5 'SELECT.*FROM adx_signals' live_trader.py). How can I optimize it?"

# Improve error handling
ds "My trading bot crashes when the API connection fails. How should I implement proper error handling and retry logic in Python?"

# Add logging
ds "What's the best way to implement comprehensive logging in a Python trading bot? Show me a practical example."

# Refactor code
ds "This function is too long: $(grep -A 50 'def process_signal' live_trader.py). How can I refactor it into smaller, testable functions?"
```

---

## 4. Troubleshooting & Debugging

### Debug Issues

```bash
# Bot not generating signals
ds "My ADX trading bot hasn't generated any signals in 6 hours. BTC price moved from 106k to 110k. The ADX threshold is 25. What could be wrong? How do I debug this?"

# Database connection errors
ds "I'm getting 'Lost connection to MySQL server during query' error. My bot queries the database every 5 minutes. How do I fix this in Python with mysql-connector?"

# Memory leaks
ds "My Python trading bot's memory usage keeps growing from 100MB to 2GB over 24 hours. What causes memory leaks in long-running Python processes? How do I find and fix them?"

# API rate limits
ds "I'm getting 'rate limit exceeded' from BingX API. My bot makes requests every 5 minutes. How can I implement proper rate limiting and backoff in Python?"
```

### Analyze Errors

```bash
# When you get an error, paste it:
ds "I'm getting this error in my trading bot: 'KeyError: last_price' in line 145. Here's the code: $(sed -n '140,150p' live_trader.py). What's wrong and how do I fix it?"

# Understand stack traces
ds "Explain this error and how to fix it: $(journalctl -u adx-trading-bot.service -n 20 --no-pager)"
```

---

## 5. Learning & Best Practices

### Learn Concepts

```bash
# Trading concepts
ds "Explain position sizing in trading. What is the Kelly Criterion and should I use it for crypto trading?"

# Technical indicators
ds "What's the difference between ADX and RSI? When should I use each one?"

# Risk management
ds "Explain risk management best practices for automated trading bots. What is maximum drawdown?"

# Python concepts
ds "Explain Python asyncio and when I should use it in a trading bot"
```

### Code Quality

```bash
# Get best practices
ds "What are best practices for writing production-ready Python trading bots? Cover error handling, logging, testing, and monitoring."

# Security review
ds "Review this code for security issues: $(cat config/.env.example). How should I securely store API keys in production?"

# Performance optimization
ds "My trading bot processes signals slowly. How can I optimize Python code for better performance? What profiling tools should I use?"
```

---

## 6. Practical Workflows

### Morning Check Routine

```bash
cd /var/www/dev/trading

# 1. Check what changed overnight
ds "I modified the stop-loss calculation yesterday. What should I test before deploying to production?"

# 2. Review recent trades
ds "I have 3 losing trades in a row. Here's the data: $(tail -20 logs/trades.log). What patterns should I look for?"

# 3. Check system health
ds "My trading bot service restarted 5 times overnight. How do I diagnose the cause using systemd logs?"
```

### Before Deployment

```bash
# Pre-deployment checklist
ds "I'm about to deploy new code to my live trading bot. Create a pre-deployment checklist covering: testing, backup, rollback plan, monitoring."

# Review changes
ds "I changed this code: $(git diff live_trader.py | head -50). What risks should I be aware of?"

# Test plan
ds "I added trailing stop-loss feature. Create a test plan to verify it works correctly before going live."
```

### Adding a New Feature (Complete Example)

```bash
# Step 1: Understand the requirement
ds "I want to add support for multiple timeframes (1m, 5m, 15m) to my ADX strategy. Explain the architecture I need."

# Step 2: Get implementation guidance
ds "Show me how to implement multi-timeframe analysis in Python. I need to track ADX on 5-minute and 15-minute charts simultaneously."

# Step 3: Database changes
ds "I need to modify my database schema to support multiple timeframes. Current schema: $(cat schema_adx_v2.sql | grep 'CREATE TABLE adx_signals'). What changes do I need?"

# Step 4: Code review
ds "Review this multi-timeframe implementation: $(cat new_feature.py). Are there any bugs or improvements?"

# Step 5: Testing strategy
ds "How should I test multi-timeframe support? Create unit tests and integration test scenarios."
```

---

## 7. Advanced Usage

### Combine with Your Code

```bash
# Create analysis script
cat > /var/www/dev/trading/scripts/analyze_with_ai.sh << 'EOF'
#!/bin/bash
# Analyze recent trading performance

echo "Getting AI analysis of recent trades..."

# Get last 10 trades
trades=$(tail -10 logs/trades.log)

# Ask AI to analyze
ds "Analyze these recent trades and tell me what patterns you see, what's working, and what needs improvement: $trades"
EOF

chmod +x /var/www/dev/trading/scripts/analyze_with_ai.sh
./scripts/analyze_with_ai.sh
```

### Create Custom Helpers

```bash
# File: /var/www/dev/trading/scripts/ai_helper.sh

#!/bin/bash

case "$1" in
  "debug")
    # Debug the bot
    logs=$(journalctl -u adx-trading-bot.service -n 50 --no-pager)
    ds "My trading bot has issues. Analyze these logs and tell me what's wrong: $logs"
    ;;

  "analyze-code")
    # Analyze specific file
    file="$2"
    ds "Review this trading bot code: $(cat $file)"
    ;;

  "explain")
    # Explain concept
    ds "$2"
    ;;

  *)
    echo "Usage: $0 {debug|analyze-code|explain} [args]"
    ;;
esac
```

---

## 8. Real Examples from Your Project

### Example 1: Understanding Why No Signals Generated

```bash
cd /var/www/dev/trading

# Check the situation
ds "My ADX trading bot hasn't generated signals in 6 hours. According to the README, it should generate 5-10 signals per hour. BTC price: $110,923 (+3.37% today). The strategy requires ADX > 25 and +DI/-DI crossover. Why might this happen?"

# Expected response will explain:
# - Market might be consolidating (no strong trend)
# - ADX might be below 25 despite price movement
# - Bot correctly waiting for confirmed signals
# - How to verify ADX values
```

### Example 2: Adding Database Backup

```bash
ds "I need to add automatic database backup for my trading bot's MariaDB. The database is 'bitcoin_trading' and I want daily backups with 7-day retention. Show me the bash script and cron setup."

# You'll get a complete solution with script and cron configuration
```

### Example 3: Optimizing the Dashboard

```bash
cd adx_strategy_v2

ds "My Flask dashboard at dashboard_web.py is slow when loading. It queries the database every time someone refreshes. How can I implement caching to improve performance? Show Python code."
```

### Example 4: Understanding Market Conditions

```bash
ds "BTC moved from $106k to $110k but my ADX bot didn't trade. Explain: 1) What ADX measures, 2) Why price movement doesn't always mean trend, 3) How to verify if ADX strategy is working correctly"
```

---

## 9. Tips for Effective Use

### Be Specific

❌ **Bad:** "How do I improve my code?"

✅ **Good:** "This function in live_trader.py line 145 is slow: $(sed -n '145,160p' live_trader.py). How can I optimize it?"

### Provide Context

Always mention:
- What you're trying to achieve
- What's not working
- Any error messages (full text)
- Relevant code snippets

### Break Complex Questions

Instead of:
```bash
ds "Help me add multi-timeframe support, fix the database issue, and optimize performance"
```

Do:
```bash
ds "First question: Explain multi-timeframe analysis architecture"
# Read response, then:
ds "How do I implement the data structure for storing 1m, 5m, 15m data?"
# Continue iteratively
```

---

## 10. Quick Command Reference

```bash
# Understanding
ds "Explain [concept/file/error]"
ds "What does this code do: $(cat file.py)"

# Development
ds "How do I implement [feature]?"
ds "Show me example code for [task]"

# Troubleshooting
ds "I'm getting [error]. How do I fix it?"
ds "Why is [component] not working?"

# Code Review
ds "Review this code: $(cat file.py)"
ds "What's wrong with: $(grep -A 10 'function' file.py)"

# Best Practices
ds "What are best practices for [topic]?"
ds "How should I test [feature]?"
```

---

## 11. Integration with Development Workflow

### Git Workflow

```bash
# Before committing
ds "Review my changes before commit: $(git diff)"

# Understanding commits
ds "Explain what this commit does: $(git show HEAD)"

# Code review
ds "Review this pull request diff: $(git diff main..feature-branch)"
```

### Testing

```bash
# Create tests
ds "Create unit tests for this function: $(grep -A 20 'def calculate_position_size' live_trader.py)"

# Understand test failures
ds "This test is failing: $(pytest -v test_live_trader.py 2>&1 | tail -20). Why and how to fix?"
```

---

## Summary

The `ds` command is your **AI pair programmer** for this trading bot project. Use it to:

1. ✅ Understand existing code and architecture
2. ✅ Get help implementing new features
3. ✅ Debug issues and errors
4. ✅ Learn trading concepts and best practices
5. ✅ Review code quality and security
6. ✅ Optimize performance

**Remember:**
- Be specific with your questions
- Provide relevant code snippets
- Ask follow-up questions to dive deeper
- Use it iteratively during development

---

**Start using it now!**

```bash
cd /var/www/dev/trading
ds "Explain the current status of my trading bot based on the README"
```
