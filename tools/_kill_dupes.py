"""Kill duplicate background processes — keep ONE of each."""
import psutil

KEEPERS = ["dashboard_server", "python_signal_executor", "trailing_stop_manager"]
seen = {}
for p in psutil.process_iter(["pid", "cmdline", "create_time"]):
    try:
        cl = " ".join(p.info.get("cmdline") or []).lower()
        for k in KEEPERS:
            if k in cl:
                if k not in seen:
                    seen[k] = []
                seen[k].append((p.info["pid"], p.info["create_time"]))
                break
    except Exception:
        pass

for k, plist in seen.items():
    plist.sort(key=lambda x: x[1])  # oldest first
    keep_pid, keep_ts = plist[0]
    print(f"{k}: keep PID {keep_pid}")
    for pid, ts in plist[1:]:
        try:
            psutil.Process(pid).kill()
            print(f"  killed dupe PID {pid}")
        except Exception as e:
            print(f"  could not kill {pid}: {e}")
