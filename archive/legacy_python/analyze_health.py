import json
import sys
import os

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

print("=" * 70)
print("AGENT TRAINING SYSTEM HEALTH CHECK")
print("=" * 70)

# 1. agent_training.py - Check for all 3 training levels
print("\n1. AGENT_TRAINING.PY - Training Levels Implementation")
print("-" * 70)
try:
    with open('agent_training.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Check for Level 1 (Statistical)
    has_level1 = 'LEVEL 1' in content and '_learn' in content
    print(f"  {'✓' if has_level1 else '✗'} Level 1 (Statistical Learning): {'IMPLEMENTED' if has_level1 else 'MISSING'}")

    # Check for Level 2 (ML)
    has_level2 = 'LEVEL 2' in content and '_train_ml_model' in content
    print(f"  {'✓' if has_level2 else '✗'} Level 2 (ML Pattern Recognition): {'IMPLEMENTED' if has_level2 else 'MISSING'}")

    # Check for Level 3 (Auto-Management)
    has_level3 = 'LEVEL 3' in content and 'blacklist' in content
    print(f"  {'✓' if has_level3 else '✗'} Level 3 (Auto-Management): {'IMPLEMENTED' if has_level3 else 'MISSING'}")

    # Check for key functions
    funcs = {
        'load()': 'load' in content,
        'save()': 'save' in content,
        'record_entry()': 'record_entry' in content,
        'record_outcome()': 'record_outcome' in content,
        'get_confidence_adjustment()': 'get_confidence_adjustment' in content,
        'run_continuous_learning()': 'run_continuous_learning' in content,
    }

    print(f"\n  Core Functions:")
    for func, present in funcs.items():
        print(f"    {'✓' if present else '✗'} {func}: {'YES' if present else 'NO'}")

    # Check for syntax errors
    try:
        compile(content, 'agent_training.py', 'exec')
        print(f"\n  {'✓'} Syntax: VALID (no Python syntax errors)")
    except SyntaxError as e:
        print(f"\n  {'✗'} Syntax: ERROR - {e}")

except Exception as e:
    print(f"  {'✗'} Error reading file: {e}")

# 2. multi_agent_trainer.py - Check agents
print("\n2. MULTI_AGENT_TRAINER.PY - Agent Architecture")
print("-" * 70)
try:
    with open('multi_agent_trainer.py', 'r', encoding='utf-8') as f:
        content = f.read()

    agents = {
        'DataCollectorAgent': 'DataCollectorAgent' in content,
        'TechnicalAnalysisAgent': 'TechnicalAnalysisAgent' in content,
        'PatternDiscoveryAgent': 'PatternDiscoveryAgent' in content,
        'MLTrainerAgent': 'MLTrainerAgent' in content,
        'StrategyOptimizerAgent': 'StrategyOptimizerAgent' in content,
        'BacktestValidatorAgent': 'BacktestValidatorAgent' in content,
        'CoordinatorAgent': 'CoordinatorAgent' in content,
    }

    implemented = sum(1 for v in agents.values() if v)
    print(f"  Agents Implemented: {implemented}/{len(agents)}")

    for agent, present in agents.items():
        print(f"    {'✓' if present else '✗'} {agent}")

    # Check for TrainingBus
    has_bus = 'TrainingBus' in content
    print(f"\n  {'✓' if has_bus else '✗'} TrainingBus (inter-agent communication): {'YES' if has_bus else 'NO'}")

    # Check for key methods
    has_async = 'async' in content
    print(f"  {'✓' if has_async else '✗'} Async/Concurrent execution: {'YES' if has_async else 'NO'}")

    # Syntax check
    try:
        compile(content, 'multi_agent_trainer.py', 'exec')
        print(f"  {'✓'} Syntax: VALID")
    except SyntaxError as e:
        print(f"  {'✗'} Syntax: ERROR - {e}")

except Exception as e:
    print(f"  {'✗'} Error reading file: {e}")

# 3. agent_training_data.json - Check data integrity
print("\n3. AGENT_TRAINING_DATA.JSON - Trade Records")
print("-" * 70)
try:
    with open('agent_training_data.json', 'r', encoding='utf-8') as f:
        training_data = json.load(f)

    print(f"  {'✓'} JSON Format: VALID")

    # Check structure
    required_keys = ['trades', 'patterns', 'symbol_stats']
    missing = [k for k in required_keys if k not in training_data]
    if missing:
        print(f"  {'⚠'} Missing keys: {missing}")

    # Trade records
    trades = training_data.get('trades', [])
    print(f"  Total trade records: {len(trades)}")

    if trades:
        wins = sum(1 for t in trades if t.get('outcome') == 'WIN')
        losses = sum(1 for t in trades if t.get('outcome') == 'LOSS')
        win_rate = round(wins / len(trades) * 100, 1) if trades else 0
        print(f"  Win/Loss breakdown: {wins} wins, {losses} losses")
        print(f"  Overall win rate: {win_rate}%")
        print(f"  Total P&L: ${training_data.get('total_pnl', 0):.2f}")

    # Symbol coverage
    sym_stats = training_data.get('symbol_stats', {})
    print(f"  Symbols tracked: {len(sym_stats)}")
    if sym_stats:
        print(f"    Symbols: {', '.join(list(sym_stats.keys())[:10])}")

    # ML model status
    ml_acc = training_data.get('ml_model_accuracy', 0)
    print(f"  ML model accuracy: {ml_acc}%")

    # Check for corrupted records
    bad_records = 0
    for i, t in enumerate(trades):
        if not isinstance(t, dict) or 'outcome' not in t:
            bad_records += 1

    if bad_records:
        print(f"  {'⚠'} Corrupted records: {bad_records}")
    else:
        print(f"  {'✓'} Data integrity: All records have outcome field")

except json.JSONDecodeError as e:
    print(f"  {'✗'} JSON parsing error: {e}")
except Exception as e:
    print(f"  {'✗'} Error: {e}")

# 4. agent_memory.json - Check memory health
print("\n4. AGENT_MEMORY.JSON - Agent Memory")
print("-" * 70)
try:
    with open('agent_memory.json', 'r', encoding='utf-8') as f:
        memory = json.load(f)

    print(f"  {'✓'} JSON Format: VALID")

    # Count agents and entries
    agents_dict = {}
    for key, val in memory.items():
        if isinstance(val, list):
            agents_dict[key] = len(val)
        elif isinstance(val, dict):
            agents_dict[key] = len(val)
        else:
            agents_dict[key] = 1 if val else 0

    total_agents = len(agents_dict)
    total_entries = sum(agents_dict.values())

    print(f"  Total agents/symbols: {total_agents}")
    print(f"  Total memory entries: {total_entries}")

    # Show agents with memory
    populated = {k: v for k, v in agents_dict.items() if v > 0}
    print(f"  Agents with memory: {len(populated)}")

    # Sample agents
    sample = sorted(populated.items(), key=lambda x: x[1], reverse=True)[:5]
    for agent, count in sample:
        print(f"    {agent}: {count} entries")

except json.JSONDecodeError as e:
    print(f"  {'✗'} JSON parsing error: {e}")
except Exception as e:
    print(f"  {'✗'} Error: {e}")

# 5. agent_learnings.json - Check learnings integrity
print("\n5. AGENT_LEARNINGS.JSON - Agent Learnings")
print("-" * 70)
try:
    with open('agent_learnings.json', 'r', encoding='utf-8') as f:
        learnings = json.load(f)

    print(f"  {'✓'} JSON Format: VALID (Array)")

    if isinstance(learnings, list):
        print(f"  Total learning entries: {len(learnings)}")

        # Categorize by topic
        topics = {}
        for entry in learnings:
            if isinstance(entry, dict):
                topic = entry.get('topic', 'unknown')
                topics[topic] = topics.get(topic, 0) + 1

        print(f"  Learning topics ({len(topics)} unique):")
        for topic, count in sorted(topics.items(), key=lambda x: x[1], reverse=True):
            print(f"    {topic}: {count} lessons")

        # Check for required fields
        has_required = all(
            isinstance(e, dict) and 'topic' in e and 'lesson' in e
            for e in learnings[:min(10, len(learnings))]
        )
        print(f"  {'✓' if has_required else '⚠'} Learning entries have required fields (topic, lesson)")

except json.JSONDecodeError as e:
    print(f"  {'✗'} JSON parsing error: {e}")
except Exception as e:
    print(f"  {'✗'} Error: {e}")

print("\n" + "=" * 70)
print("HEALTH CHECK COMPLETE")
print("=" * 70)
