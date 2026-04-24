import os

hits = []
roots = ['C:\\Program Files', 'C:\\Program Files (x86)', 'C:\\']
for root in roots:
    if not os.path.isdir(root):
        continue
    for d in os.listdir(root):
        p = os.path.join(root, d)
        if not os.path.isdir(p):
            continue
        low = d.lower()
        if any(k in low for k in ['metatrader', 'octa', 'mt5', 'exness']):
            te = os.path.join(p, 'terminal64.exe')
            me = os.path.join(p, 'metaeditor64.exe')
            hits.append((p, os.path.exists(te), os.path.exists(me)))

print('=== MT5 install candidates ===')
for h in hits:
    print(h)

appd = os.environ.get('APPDATA', '')
mq = os.path.join(appd, 'MetaQuotes', 'Terminal')
print('\n=== MetaQuotes Terminal dirs ===')
if os.path.isdir(mq):
    for d in os.listdir(mq):
        full = os.path.join(mq, d)
        if os.path.isdir(full):
            origin = os.path.join(full, 'origin.txt')
            origin_txt = ''
            if os.path.exists(origin):
                try:
                    origin_txt = open(origin, 'r', errors='ignore').read().strip()
                except Exception as e:
                    origin_txt = f'<read err: {e}>'
            print(f'{d}  ->  {origin_txt}')
