# SCALPING v1.2 - Archived System

**Archive Date:** 2025-10-15
**Final Status:** Stopped for ADX v2.0 development
**Running Period:** October 11-12, 2025

## Final Performance Summary

- **Win Rate:** 49.5% (49 wins / 50 losses)
- **Total Signals:** 1,034 (936 evaluated in last 24h)
- **Timeout Rate:** 92%
- **P&L:** +0.317%

## Best Performing Signals (SHORT only)

1. **EMA_BEARISH_CROSS:** 90.9% win rate (20W/2L)
2. **NEAR_RESISTANCE:** 89.5% win rate (17W/2L)
3. **RSI_OVERBOUGHT:** 84.6% win rate (11W/2L)

## Failed Signals (LONG)

1. **EMA_BULLISH_CROSS:** 0.0% win rate (0W/19L)
2. **NEAR_SUPPORT:** 0.0% win rate (0W/15L)
3. **RSI_OVERSOLD:** 9.1% win rate (1W/10L)

## Key Learnings

✅ SHORT signals in downtrends are highly profitable
❌ LONG signals (counter-trend) completely failed
⚠️ 92% timeout rate indicates targets too aggressive
📊 38 signals/hour is excessive - quality over quantity needed

## Archived Files

- `btc_monitor.py` - Main signal generator
- `signal_tracker.py` - Signal tracking system
- `auto_label_monitor.py` - Auto-labeling daemon
- `signals_final_backup_20251015.db` - Complete signal database
- `config_conservative.json` - Final configuration
- All log files

## Reason for Archive

Transitioning to **ADX v2.0 Strategy** with:
- Trend-following approach (vs counter-trend)
- 5-minute timeframe (vs 5-second)
- ADX-based indicators (vs RSI/EMA)
- 5x leverage on BingX Futures
- Target: 60%+ win rate

## References

- Full analysis: `/var/www/dev/trading/CURRENT_STRATEGY_ANALYSIS.md`
- ADX plan: `/var/www/dev/trading/ADX_V2_APPROVED_EXECUTION_PLAN.md`
