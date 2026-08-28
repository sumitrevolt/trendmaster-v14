from pathlib import Path
import time
Path(r"C:\Users\Ratanshila\Documents\autmated trading\outputs\sentinel_proof.txt").write_text(f"SENTINEL RAN AT {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
print("OK")
