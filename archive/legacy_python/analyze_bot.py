import json

print("=" * 70)
print("TRADING BOT ANALYSIS REPORT")
print("=" * 70)

# 1. Analyze Error Logs
print("\n1. ERROR LOGS (agent_err.txt)")
print("-" * 70)
try:
    with open('agent_err.txt', 'r') as f:
        errors = f.read()
    if errors.strip():
        print(errors[:500])
    else:
        print("No errors found - clean execution")
except Exception as e:
    print(f"Could not read: {e}")

# 2. Analyze Output Logs
print("\n2. OUTPUT LOGS (agent_out.txt)")
print("-" * 70)
try:
    with open('agent_out.txt', 'r') as f:
        output = f.read()
    if output.strip():
        lines = output.split('\n')
        print(f"Total lines: {len(lines)}")
        print("Last 20 lines:")
        print('\n'.join(lines[-20:]))
    else:
        print("No output found")
except Exception as e:
    print(f"Could not read: {e}")

# 3. Analyze Start Log
print("\n3. START LOG (_start_log.txt)")
print("-" * 70)
try:
    with open('_start_log.txt', 'r') as f:
        start_log = f.read()
    if start_log.strip():
        print(start_log[:500])
    else:
        print("No start log found")
except Exception as e:
    print(f"Could not read: {e}")

# 4. Analyze Prediction Memory
print("\n4. PREDICTION MEMORY ANALYSIS")
print("-" * 70)
try:
    with open('prediction_memory.json', 'r') as f:
        pred_mem = json.load(f)
    
    if isinstance(pred_mem, dict):
        print(f"Format: Dictionary with {len(pred_mem)} entries")
        # Try to understand structure
        sample_key = list(pred_mem.keys())[0]
        sample_value = pred_mem[sample_key]
        print(f"Sample key: {sample_key}")
        print(f"Sample value type: {type(sample_value)}")
        if isinstance(sample_value, dict):
            print(f"Sample keys: {list(sample_value.keys())}")
            print(f"Sample value: {json.dumps(sample_value, indent=2)[:300]}")
    elif isinstance(pred_mem, list):
        print(f"Format: List with {len(pred_mem)} items")
        if pred_mem:
            print(f"First item: {json.dumps(pred_mem[0], indent=2)[:300]}")
            # Count correct/incorrect
            correct = sum(1 for p in pred_mem if isinstance(p, dict) and p.get('correct'))
            incorrect = len(pred_mem) - correct
            accuracy = (correct / len(pred_mem) * 100) if pred_mem else 0
            print(f"Correct predictions: {correct}")
            print(f"Incorrect predictions: {incorrect}")
            print(f"Win rate: {accuracy:.2f}%")
except Exception as e:
    print(f"Error: {e}")

# 5. Analyze Agent Learnings
print("\n5. AGENT LEARNINGS")
print("-" * 70)
try:
    with open('agent_learnings.json', 'r') as f:
        learnings = json.load(f)
    
    print(f"Type: {type(learnings)}")
    if isinstance(learnings, dict):
        print(f"Keys: {list(learnings.keys())[:10]}")
        for k, v in list(learnings.items())[:3]:
            print(f"  {k}: {v}")
    elif isinstance(learnings, list):
        print(f"Length: {len(learnings)}")
        print(f"First items: {json.dumps(learnings[:2], indent=2)[:300]}")
except Exception as e:
    print(f"Error: {e}")

# 6. Analyze Training Data
print("\n6. TRAINING DATA")
print("-" * 70)
try:
    with open('agent_training_data.json', 'r') as f:
        train_data = json.load(f)
    
    print(f"Type: {type(train_data)}")
    if isinstance(train_data, (dict, list)):
        if isinstance(train_data, dict):
            print(f"Keys: {list(train_data.keys())[:10]}")
        else:
            print(f"Length: {len(train_data)}")
            if train_data:
                print(f"First item keys: {list(train_data[0].keys()) if isinstance(train_data[0], dict) else 'N/A'}")
except Exception as e:
    print(f"Error: {e}")

# 7. Analyze Institutional Positions
print("\n7. INSTITUTIONAL POSITIONS")
print("-" * 70)
try:
    with open('institutional_positions.json', 'r') as f:
        positions = json.load(f)
    
    print(f"Type: {type(positions)}")
    if isinstance(positions, dict):
        print(f"Keys: {list(positions.keys())[:10]}")
        for k, v in list(positions.items())[:2]:
            print(f"  {k}: {v}")
    elif isinstance(positions, list):
        print(f"Length: {len(positions)}")
        if positions:
            print(f"First item: {json.dumps(positions[0], indent=2)[:300]}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 70)
