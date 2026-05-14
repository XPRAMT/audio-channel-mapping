"""
自動同步 translations.ts 到各語言 .ts 檔案並透過 DeepSeek 自動翻譯
用法: python sync_translations.py

流程:
  1. 讀取 translations.ts 作為基準（包含所有應有的 source 條目）
  2. 對每個目標語言檔案逐一處理：
     a. 檔案不存在 → 從 translations.ts 複製建立
     b. 解析現有翻譯，保留已完成的翻譯
     c. 偵測 translations.ts 中新增或未完成的條目
     d. 列出待翻譯項目，互動確認 (y/n)
     e. y → 調用 DeepSeek API 自動翻譯；n → 保留 unfinished
     f. 輸出更新後的目標語言檔案
  目標語言涵蓋世界使用人口前 10 語言（不含英語來源）
"""
import xml.etree.ElementTree as ET
import re
import json
import time
import requests
from pathlib import Path
from collections import OrderedDict

# ── 設定 ──
BASE_DIR = Path(__file__).parent
LANG_DIR = BASE_DIR / "language"
BASE_TS = LANG_DIR / "translations.ts"

# 目標語言 → (檔名, DeepSeek 要求的目標語言名稱)
# 涵蓋世界使用人口前 10 語言（不含英語來源）
TARGETS = {
    "zh-Hans-CN": LANG_DIR / "zh-Hans-CN.ts",
    "zh-Hant-TW": LANG_DIR / "zh-Hant-TW.ts",
    "hi":         LANG_DIR / "hi.ts",
    "es":         LANG_DIR / "es.ts",
    "fr":         LANG_DIR / "fr.ts",
    "ar":         LANG_DIR / "ar.ts",
    "bn":         LANG_DIR / "bn.ts",
    "pt":         LANG_DIR / "pt.ts",
    "ru":         LANG_DIR / "ru.ts",
    "ja":         LANG_DIR / "ja.ts",
}

DEEPSEEK_API_KEY = "sk-d2bead50e3254a40a58e9d678e6b9cad"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# ── XML 解析輔助 ──
# 手動解析以保留 comment / 格式；ET 會丟掉註解
def parse_ts_entries(filepath: Path) -> list[dict]:
    """從 .ts 檔案解析出所有 <message> 條目，回傳 list[dict]"""
    text = filepath.read_text(encoding="utf-8")

    # 匹配每個 <message> 區塊（處理自閉合與一般 translation 標籤）
    pattern = re.compile(
        r'<message>\s*'
        r'(<location\s+filename="[^"]*"\s+line="[^"]*"\s*/>\s*)?'
        r'<source>(.*?)</source>\s*'
        r'<translation(?:\s+type="([^"]*)")?\s*(?:>(.*?)</translation>|/>)\s*'
        r'</message>',
        re.DOTALL
    )

    entries = []
    for m in pattern.finditer(text):
        trans_text = m.group(4) or ""  # group(4) is None for self-closing tags
        entries.append({
            "location": m.group(1) or "",
            "source": m.group(2).strip(),
            "type": m.group(3) or "",       # "unfinished" or ""
            "translation": trans_text.strip(),
        })
    return entries


def parse_ts_as_dict(filepath: Path) -> OrderedDict:
    """解析 .ts 為 OrderedDict[source → translation_text]"""
    entries = parse_ts_entries(filepath)
    result = OrderedDict()
    for e in entries:
        txt = e["translation"]
        is_unfinished = (e["type"] == "unfinished" or not txt)
        result[e["source"]] = None if is_unfinished else txt
    return result


def build_ts_xml(entries: list[dict], base_ts_text: str) -> str:
    """根據 entries 重建 .ts XML，保留原始標頭"""
    # 提取原檔 XML 頭部
    header_match = re.search(r'(.*?)<context>', base_ts_text, re.DOTALL)
    header = ""
    if header_match:
        header = header_match.group(1)

    messages = []
    for e in entries:
        loc = e.get("location", "").strip()
        src = e["source"]
        trans = e.get("translation", "")
        unfinished = e.get("type") == "unfinished"

        msg = '    <message>\n'
        if loc:
            msg += f'      {loc}\n'
        msg += f'      <source>{src}</source>\n'

        if unfinished or not trans:
            msg += f'      <translation type="unfinished" />\n'
        else:
            # 逸出 XML 特殊字元
            safe_trans = trans.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            msg += f'      <translation>{safe_trans}</translation>\n'

        msg += '    </message>'
        messages.append(msg)

    body = '\n'.join(messages)
    return f'{header}<context>\n    <name />\n{body}\n  </context>\n</TS>\n'


# ── DeepSeek 翻譯 ──
def translate_via_deepseek(sources: list[str], target_lang: str) -> list[str]:
    """批次呼叫 DeepSeek API 翻譯多個字串"""
    if not sources:
        return []

    # 建立 prompt
    lines = "\n".join(f'{i+1}. "{s}"' for i, s in enumerate(sources))
    prompt = (
        f"Translate the following English UI strings into {target_lang}. "
        f"Keep the translation concise and suitable for a software UI. "
        f"Output ONLY the translated text, one per line, in the same order. "
        f"Do NOT include numbers, quotes, or any extra text:\n\n{lines}"
    )

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": f"You are a professional software translator. Always translate to {target_lang} only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
    }

    for attempt in range(3):
        try:
            resp = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                result = resp.json()["choices"][0]["message"]["content"].strip()
                # 按行分割，過濾空行
                translations = [line.strip() for line in result.split("\n") if line.strip()]
                # 確保數量匹配
                while len(translations) < len(sources):
                    translations.append("")
                return translations[:len(sources)]
            else:
                print(f"  ⚠ DeepSeek API 錯誤 (attempt {attempt+1}): HTTP {resp.status_code}")
                if attempt < 2:
                    time.sleep(2)
        except Exception as e:
            print(f"  ⚠ DeepSeek API 例外 (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(2)

    return [""] * len(sources)


# ── 主流程 ──
def main():
    print("=" * 60)
    print("🔄 翻譯同步工具 - 基準檔案: translations.ts")
    print("=" * 60)

    # 1. 讀取基準檔案
    base_entries = parse_ts_entries(BASE_TS)
    base_sources = [e["source"] for e in base_entries]
    base_text = BASE_TS.read_text(encoding="utf-8")
    print(f"\n📄 translations.ts: {len(base_sources)} 個條目")

    for lang, filepath in TARGETS.items():
        print(f"\n{'─' * 40}")
        print(f"🎯 目標: {filepath.name} ({lang})")

        if not filepath.exists():
            print(f"  📄 檔案不存在，從 translations.ts 建立模板...")
            filepath.write_text(base_text, encoding="utf-8")
            existing = {}
        else:
            # 2. 解析現有翻譯
            existing = parse_ts_as_dict(filepath)
        print(f"  現有已翻譯: {sum(1 for v in existing.values() if v is not None)}/{len(existing)}")

        # 3. 找出需要翻譯的條目
        to_translate = []      # (index_in_base, source)
        keep_translation = {}  # source → existing translation

        for i, entry in enumerate(base_entries):
            src = entry["source"]
            old_trans = existing.get(src)
            if old_trans is not None:
                keep_translation[src] = old_trans
            else:
                to_translate.append((i, src))

        print(f"  需新增/翻譯: {len(to_translate)} 個條目")

        # 4. 顯示待翻譯條目，確認後呼叫 DeepSeek
        if to_translate:
            lang_name = {
                "zh-Hant-TW": "Traditional Chinese (zh-TW)",
                "zh-Hans-CN": "Simplified Chinese (zh-CN)",
                "hi":         "Hindi",
                "es":         "Spanish",
                "fr":         "French",
                "ar":         "Arabic",
                "bn":         "Bengali",
                "pt":         "Portuguese",
                "ru":         "Russian",
                "ja":         "Japanese",
            }.get(lang, lang)

            sources_to_translate = [src for _, src in to_translate]
            print(f"  📋 待翻譯 ({len(sources_to_translate)} 個):")
            for src in sources_to_translate:
                print(f"     - {src}")
            print(f"  🌐 目標語言: {lang_name}")

            answer = input(f"  ❓ 是否調用 DeepSeek 翻譯? (y/n): ").strip().lower()
            if answer != "y":
                print(f"  ⏭️ 已取消，跳過翻譯")
                # 未翻譯的條目保留為 unfinished
                for _, src in to_translate:
                    keep_translation[src] = ""
                # 繼續寫入（會輸出 type="unfinished"）
            else:
                print(f"  🤖 調用 DeepSeek 翻譯中...")

                translations = translate_via_deepseek(sources_to_translate, lang_name)

                for (idx, src), trans in zip(to_translate, translations):
                    keep_translation[src] = trans
                    status = "✅" if trans else "❌"
                    print(f"    {status} [{src}] → [{trans}]")

                time.sleep(1)

        # 5. 重建目標 ts 檔案（順序完全跟隨 translations.ts）
        new_entries = []
        for entry in base_entries:
            src = entry["source"]
            trans = keep_translation.get(src, "")
            new_entry = {
                "location": entry["location"],
                "source": src,
                "translation": trans,
                "type": "" if trans and trans != src else "unfinished",
            }
            new_entries.append(new_entry)

        new_xml = build_ts_xml(new_entries, base_text)
        filepath.write_text(new_xml, encoding="utf-8")
        print(f"  💾 已寫入: {filepath.name}")

    print(f"\n{'=' * 60}")
    print("🎉 同步完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
