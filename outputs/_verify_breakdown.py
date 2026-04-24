"""Per-file pytest breakdown."""
import os, sys, subprocess
os.chdir(r"C:\Users\Ratanshila\Documents\autmated trading")
sys.path.insert(0, os.getcwd())

r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v", "--no-header", "--tb=no"],
                   capture_output=True, text=True, timeout=240)
print("STDOUT lines (first 40):")
for line in r.stdout.splitlines()[:40]:
    print(f"  | {line}")
print("...")
print("STDOUT lines (last 5):")
for line in r.stdout.splitlines()[-5:]:
    print(f"  | {line}")
