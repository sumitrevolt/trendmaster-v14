import json, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

base = r'C:\Users\Ratanshila\Documents\autmated trading\ai_trading_agents'

# Check memory
mf = os.path.join(base, 'agent_memory.json')
if os.path.exists(mf):
    d = json.load(open(mf, 'r', encoding='utf-8'))
    print(f"=== MEMORY: {len(d)} agents ===")
    for k, v in d.items():
        if isinstance(v, list) and len(v) > 0:
            last_item = v[-1]
            if isinstance(last_item, dict):
                last = last_item.get('content','')[:100]
            else:
                last = str(last_item)[:100]
            print(f"  {k}: {len(v)} msgs | Last: {last}")
        elif isinstance(v, dict):
            print(f"  {k}: dict with {len(v)} keys")
        else:
            print(f"  {k}: type={type(v).__name__}")
else:
    print("NO memory file")

print()

# Check training data
tf = os.path.join(base, 'agent_training_data.json')
if os.path.exists(tf):
    t = json.load(open(tf, 'r', encoding='utf-8'))
    print(f"=== TRAINING DATA ===")
    for sector, sessions in t.items():
        print(f"  {sector}: {len(sessions)} sessions")
        if sessions:
            last = sessions[-1]
            print(f"    Last: {last.get('timestamp','?')}")
            print(f"    Insights: {last.get('insights','')[:150]}")
else:
    print("NO training data file yet")

print()

# Check learnings
lf = os.path.join(base, 'agent_learnings.json')
if os.path.exists(lf):
    l = json.load(open(lf, 'r', encoding='utf-8'))
    print(f"=== LEARNINGS: {len(l)} total ===")
    for item in l[-3:]:
        print(f"  [{item.get('source','')}] {item.get('topic','')}: {item.get('lesson','')[:100]}")
else:
    print("NO learnings file")
