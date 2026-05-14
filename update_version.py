"""
自動更新版本號為當天日期 (YY.MM.DD 格式)
影響檔案:
  - GUI.pyw        : curVersion
  - version.txt    : filevers, ProductVersion
  - pyproject.toml : version
"""
import re
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).parent

today = date.today()
YY = today.strftime("%y")   # 兩位數年份, e.g. "26"
MM = today.strftime("%m")   # 兩位數月份, e.g. "05"
DD = today.strftime("%d")   # 兩位數日期, e.g. "14"

# 無前導零的整數版本 (供 filevers 使用)
M_int = today.month   # e.g. 5
D_int = today.day     # e.g. 14

VERSION_STR = f"{YY}.{MM}.{DD}"          # e.g. "26.05.14"
VERSION_TUPLE = f"({YY}, {M_int}, {D_int}, 0)"  # e.g. "(26, 5, 14, 0)"
VERSION_FILE = f"'{YY}.{MM}.{DD}.0'"     # e.g. "'26.05.14.0'"

print(f"📅 今天日期: {today}")
print(f"🔢 新版本號: {VERSION_STR}")

# ── 1. 更新 GUI.pyw ──
gui_path = BASE_DIR / "GUI.pyw"
gui_content = gui_path.read_text(encoding="utf-8")
new_gui = re.sub(
    r'curVersion\s*=\s*"[^"]*"',
    f'curVersion = "{VERSION_STR}"',
    gui_content
)
gui_path.write_text(new_gui, encoding="utf-8")
print(f"✅ GUI.pyw: curVersion = \"{VERSION_STR}\"")

# ── 2. 更新 version.txt ──
ver_path = BASE_DIR / "version.txt"
ver_content = ver_path.read_text(encoding="utf-8")
# 更新 filevers 元組
ver_content = re.sub(
    r'filevers\s*=\s*\([^)]+\)',
    f'filevers={VERSION_TUPLE}',
    ver_content
)
# 更新 ProductVersion 字串
ver_content = re.sub(
    r"'ProductVersion'\s*,\s*'[^']*'",
    f"'ProductVersion', {VERSION_FILE}",
    ver_content
)
ver_path.write_text(ver_content, encoding="utf-8")
print(f"✅ version.txt: filevers={VERSION_TUPLE}, ProductVersion={VERSION_FILE}")

# ── 3. 更新 pyproject.toml ──
toml_path = BASE_DIR / "pyproject.toml"
toml_content = toml_path.read_text(encoding="utf-8")
toml_content = re.sub(
    r'version\s*=\s*"[^"]*"',
    f'version = "{VERSION_STR}"',
    toml_content,
    count=1  # 只替換 [project] 下的第一個 version
)
toml_path.write_text(toml_content, encoding="utf-8")
print(f"✅ pyproject.toml: version = \"{VERSION_STR}\"")

print("\n🎉 版本號更新完成！")
