import json
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('agent_training_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

trades = data.get('trades', [])
sym_stats = data.get('symbol_stats', {})
patterns = data.get('patterns', {})

print('SYMBOL-BY-SYMBOL BREAKDOWN:')
print('-' * 70)
print('Symbol     | Status  | Win%   | Wins/Losses | P&L        ')
print('-' * 70)
for sym, stats in sorted(sym_stats.items(), key=lambda x: x[1].get('win_rate', 0), reverse=True):
    wr = stats.get('win_rate', 0)
    wins = stats.get('wins', 0)
    losses = stats.get('losses', 0)
    pnl = stats.get('total_pnl', 0)
    status = 'STRONG' if wr > 55 else 'WEAK' if wr < 45 else 'NORMAL'
    print(f'{sym:10} | {status:7} | {wr:5.1f}% | {wins:3}W/{losses:3}L | {pnl:9.2f}')

print()
print('TRAINING METADATA:')
print('-' * 70)
last_trained = data.get('last_trained', 'N/A')
print(f'Last trained: {last_trained}')

blacklisted = data.get('blacklisted_symbols', [])
print(f'Blacklisted symbols: {blacklisted if blacklisted else "None"}')

ml_acc = data.get('ml_model_accuracy', 0)
print(f'ML Model Accuracy: {ml_acc}%')

ml_features = data.get('ml_top_features', [])
if ml_features:
    print(f'\nTop ML Features:')
    for i, f in enumerate(ml_features[:5], 1):
        print(f'  {i}. {f.get("name", "?")}: {f.get("importance", 0)}%')

print()
print('PATTERNS DISCOVERED:')
print('-' * 70)
pattern_keys = list(patterns.keys())
print(f'Pattern categories: {len(pattern_keys)}')
for key in pattern_keys[:8]:
    print(f'  - {key}')

print()
print('CONTINUOUS LEARNING STATUS:')
print('-' * 70)
print(f'Adaptive thresholds configured: {len(data.get("adaptive_thresholds", {}))} symbols')
print(f'Blacklisted hours defined: {len(data.get("blacklisted_hours", {}))} symbols')
print(f'Regime statistics available: {len(data.get("regime_stats", {}))} symbols')

# Check for any issues
print()
print('DATA QUALITY CHECKS:')
print('-' * 70)

# Check for null/missing outcomes
null_outcomes = sum(1 for t in trades if 'outcome' not in t or t['outcome'] is None)
if null_outcomes > 0:
    print(f'WARNING: {null_outcomes} trades missing outcome')
else:
    print('OK: All trades have outcome recorded')

# Check for missing scores
missing_scores = sum(1 for t in trades if 'score' not in t)
if missing_scores > 0:
    print(f'WARNING: {missing_scores} trades missing score')
else:
    print('OK: All trades have score')

# Check for missing confidence
missing_conf = sum(1 for t in trades if 'confidence' not in t)
if missing_conf > 0:
    print(f'WARNING: {missing_conf} trades missing confidence')
else:
    print('OK: All trades have confidence')

# Check P&L consistency
total_pnl_calc = sum(t.get('pnl', 0) for t in trades)
total_pnl_stored = data.get('total_pnl', 0)
if abs(total_pnl_calc - total_pnl_stored) > 0.1:
    print(f'WARNING: P&L mismatch - calculated {total_pnl_calc:.2f}, stored {total_pnl_stored:.2f}')
else:
    print(f'OK: P&L consistent (${total_pnl_stored:.2f})')
