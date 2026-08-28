import psutil
for p in psutil.process_iter(['pid','name','cmdline']):
    try:
        cmd = ' '.join(p.info.get('cmdline') or [])
        if 'tv_webhook_receiver' in cmd or 'python_signal_executor' in cmd:
            print(f'killing PID {p.info[\"pid\"]}: {cmd[:100]}')
            try: p.terminate()
            except: pass
    except: pass
import time; time.sleep(3)
# Force-kill any survivors
for p in psutil.process_iter(['pid','cmdline']):
    try:
        cmd = ' '.join(p.info.get('cmdline') or [])
        if 'tv_webhook_receiver' in cmd or 'python_signal_executor' in cmd:
            try: p.kill()
            except: pass
    except: pass
