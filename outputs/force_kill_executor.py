"""Aggressive kill of all python_signal_executor PIDs using psutil.
PowerShell taskkill via WMI sometimes misses on Win11. psutil is reliable.
"""
import psutil
import time
import sys

killed_pids = []
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        if 'python_signal_executor' in cmd.lower():
            print(f"Killing PID {p.info['pid']} ({p.info['name']}): {cmd[:120]}")
            try:
                p.terminate()
                killed_pids.append(p.info['pid'])
            except Exception as e:
                print(f"  terminate failed: {e}")
                try:
                    p.kill()
                    killed_pids.append(p.info['pid'])
                except Exception as e2:
                    print(f"  kill failed: {e2}")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

print(f"\nTerminated {len(killed_pids)} executor PIDs: {killed_pids}")
time.sleep(3)

# Verify all dead
still_alive = []
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        cmd = " ".join(p.info.get('cmdline') or [])
        if 'python_signal_executor' in cmd.lower():
            still_alive.append(p.info['pid'])
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

if still_alive:
    print(f"\nWARNING: Still alive: {still_alive} — force-killing")
    for pid in still_alive:
        try:
            psutil.Process(pid).kill()
        except Exception as e:
            print(f"  PID {pid} kill failed: {e}")
else:
    print("\n[OK] No executor processes remain.")
