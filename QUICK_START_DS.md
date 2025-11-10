# Quick Start: Using `ds` Command for Your Trading Bot

## 🚀 Try These Commands Right Now

### 1. Understand Your Project (5 minutes)

```bash
cd /var/www/dev/trading

# What is this project?
ds "Summarize what this Bitcoin trading bot does based on the README file"

# What's the current status?
ds "The README shows: Balance $162.95, +9.97% return, current BTC price $110,923. The ADX v2.0 strategy is live. Explain what this means."

# How does ADX work?
ds "Explain the ADX strategy for Bitcoin trading in simple terms. What is +DI, -DI, and how do they generate trading signals?"
```

---

### 2. Analyze Specific Code (10 minutes)

```bash
cd /var/www/dev/trading/adx_strategy_v2

# Understand the main trader
ds "What should I expect to find in a file called live_trader.py in a crypto trading bot?"

# Look at actual code (first 50 lines)
ds "Explain what this code does: $(head -50 live_trader.py)"

# Understand the dashboard
ds "Explain what this Flask app does: $(head -40 dashboard_web.py)"
```

---

### 3. Get Development Help (immediate)

```bash
# Add a new feature
ds "I want to add Telegram alerts to my trading bot when a trade is opened or closed. Show me step-by-step how to implement this in Python."

# Fix an issue
ds "My trading bot hasn't generated any signals in 6 hours even though BTC moved 4%. The ADX threshold is 25. What could be wrong and how do I debug it?"

# Optimize code
ds "How can I improve the performance of database queries in a Python trading bot that runs 24/7?"
```

---

### 4. Learn Trading Concepts (anytime)

```bash
# Technical indicators
ds "What's the difference between ADX and RSI? When should I use each?"

# Risk management
ds "Explain position sizing in crypto trading. What percentage of my account should I risk per trade?"

# Trading strategies
ds "What is a trend-following strategy vs mean-reversion? Which is better for Bitcoin?"
```

---

## 📋 Common Development Tasks

### Task: Adding Trailing Stop-Loss

```bash
# Step 1: Understand the concept
ds "What is a trailing stop-loss in trading? How does it work?"

# Step 2: Get implementation guidance
ds "I have a fixed stop-loss at 2% in my Python trading bot. Show me how to implement a trailing stop-loss that moves up as profit increases."

# Step 3: Review your code
# (After implementing)
ds "Review this trailing stop-loss implementation for bugs: $(cat my_trailing_stop.py)"
```

---

### Task: Debugging No Signals Issue

```bash
# Step 1: Understand the problem
ds "My ADX bot should generate 5-10 signals per hour but generated 0 in the last 6 hours. BTC is at $110k (+3% today). What conditions must be met for ADX signals?"

# Step 2: Check logs
ds "These are my bot logs: $(journalctl -u adx-trading-bot.service -n 30 --no-pager). What do they tell me?"

# Step 3: Verify indicator values
ds "How can I manually calculate ADX for Bitcoin to verify my bot's calculations are correct?"
```

---

### Task: Adding Multiple Timeframes

```bash
# Step 1: Architecture
ds "I want my ADX strategy to work on 5-minute and 15-minute timeframes simultaneously. Explain the architecture I need."

# Step 2: Database changes
ds "What database schema changes do I need to support multiple timeframes? Currently I have: $(grep 'CREATE TABLE adx_signals' schema_adx_v2.sql)"

# Step 3: Implementation
ds "Show me Python code to fetch and analyze multiple timeframes for the same symbol using the BingX API."
```

---

## 💡 Pro Tips

### Tip 1: Provide Context
```bash
# ❌ BAD (too vague)
ds "How do I fix my code?"

# ✅ GOOD (specific with context)
ds "I'm getting 'Connection timeout' error when fetching BTC prices from BingX API in line 145 of live_trader.py. Here's the code: $(sed -n '140,150p' live_trader.py). How do I add retry logic?"
```

### Tip 2: Show Code Snippets
```bash
# Use grep to extract specific functions
ds "Review this function for bugs: $(grep -A 30 'def calculate_position_size' live_trader.py)"

# Show specific line ranges
ds "Explain what this code does: $(sed -n '100,130p' live_trader.py)"
```

### Tip 3: Ask Follow-up Questions
```bash
# First question
ds "What is the Kelly Criterion for position sizing?"

# After reading the response, dive deeper
ds "Show me how to implement the Kelly Criterion in Python for a crypto trading bot"

# Get even more specific
ds "My win rate is 60% and average win is 2% vs average loss of 1%. Calculate the optimal Kelly percentage."
```

---

## 🎯 Your First 3 Tasks Today

### Task 1: Understand the Current State (5 min)
```bash
cd /var/www/dev/trading
ds "Based on the README: my bot has $162.95 balance with +9.97% return. Last trade was a SHORT that hit stop loss. No signals in 6 hours. BTC is at $110,923. Is my bot working correctly?"
```

### Task 2: Learn One Concept (5 min)
```bash
ds "Explain the ADX indicator. What does it mean when ADX is above 25? What do +DI and -DI crossovers indicate?"
```

### Task 3: Plan One Improvement (10 min)
```bash
ds "I want to add email notifications when:
1. A trade is opened
2. A trade hits take-profit
3. A trade hits stop-loss
4. The bot encounters an error

Show me how to implement this in Python with the smtplib library."
```

---

## 📚 More Resources

- **Full Guide**: `/var/www/dev/trading/DS_COMMAND_GUIDE.md`
- **Project README**: `/var/www/dev/trading/README.md`
- **Installation Guide**: `/opt/DEEPSEEK_INSTALLATION_GUIDE.md`

---

## 🆘 Getting Help

If you're stuck, ask `ds`:

```bash
ds "I don't understand how to use this ds command effectively. Give me 3 example questions I should ask about my trading bot project."
```

---

## ✅ Start Now!

```bash
cd /var/www/dev/trading
ds "What should I focus on first to improve my ADX trading bot?"
```

**Happy Coding! 🚀**
