from pathlib import Path
import sys, time
out = Path(r"C:\Users\Ratanshila\Documents\autmated trading\outputs\python_test_proof.txt")
out.write_text(f"Python ran at {time.strftime('%Y-%m-%d %H:%M:%S')}\nargs={sys.argv}\nPython={sys.executable}\n", encoding="utf-8")
print("WROTE", out)
