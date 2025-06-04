# save this as patch_narration.py alongside narration_and_style.py
import re, sys

fn = "narration_and_style.py"
text = open(fn, "r", encoding="utf-8").read()

# 1) Remove any accidental nested f-strings in prints:
text = re.sub(
    r'print\(f"\[([A-Z]+)\]\s*f"(.*?)"\)',
    r'print(f"[\1] \2")',
    text,
    flags=re.DOTALL
)

# 2) Fix unterminated quotes (double quotes before closing paren):
text = text.replace('"" )', '")').replace('""\n', '"\n')

# 3) Correct the “Failed to retrieve” line:
text = text.replace(
    'print(f"[ERROR] "Failed to retrieve video script.")',
    'print("[ERROR] Failed to retrieve video script.")'
)

# 4) Simplify any remaining prints that still have stray quotes:
text = re.sub(r'print\((f)?"(.*?)"+"\)', r'print("\2")', text)

# Write back and test compile:
with open(fn, "w", encoding="utf-8") as f:
    f.write(text)

# Try a syntax check:
try:
    compile(text, fn, "exec")
    print("✔ narration_and_style.py patched and syntax-OK!")
except Exception as e:
    print("✘ Still a syntax error:", e)
    sys.exit(1)
