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
    "ko":         LANG_DIR / "ko.ts",
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


# ── DeepSeek 批次翻譯 ──
def translate_via_deepseek_batch(sources: list[str], lang_map: dict) -> dict:
    """
    單次 API 呼叫翻譯多個語言，節省 token。
    lang_map: {code: lang_name}  例如 {"zh-TW": "Traditional Chinese", ...}
    回傳: {code: [translation, ...]}
    """
    if not sources:
        return {code: [] for code in lang_map}

    lang_list = "\n".join(f'{code}: {name}' for code, name in lang_map.items())
    lines = "\n".join(f'{i+1}. "{s}"' for i, s in enumerate(sources))
    prompt = (
        f"Translate the following English UI strings into each target language.\n"
        f"Keep translations concise and suitable for a software UI.\n\n"
        f"==SOURCE STRINGS==\n{lines}\n\n"
        f"==TARGET LANGUAGES==\n{lang_list}\n\n"
        f"Output ONLY a valid JSON object in this format:\n"
        f'{{"lang_code": ["translation1", "translation2", ...]}}\n'
        f"One array per language, same order as source strings."
    )

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a professional software translator. Output only valid JSON, no markdown, no extra text."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    for attempt in range(3):
        try:
            resp = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                raw = resp.json()["choices"][0]["message"]["content"].strip()
                # 清理可能的 markdown 代碼塊標記
                raw = re.sub(r'^```(?:json)?\s*', '', raw)
                raw = re.sub(r'\s*```$', '', raw)
                result = json.loads(raw)

                # 補齊缺失的語言 / 缺失的條目
                out = {}
                for code in lang_map:
                    arr = result.get(code, [])
                    while len(arr) < len(sources):
                        arr.append("")
                    out[code] = arr[:len(sources)]
                return out
            else:
                print(f"  ⚠ DeepSeek API 錯誤 (attempt {attempt+1}): HTTP {resp.status_code}")
                if attempt < 2:
                    time.sleep(3)
        except Exception as e:
            print(f"  ⚠ DeepSeek API 例外 (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(3)

    return {code: [""] * len(sources) for code in lang_map}


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

    # ── 第一階段：收集所有語言需要翻譯的條目 ──
    lang_name_map = {
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
        "ko":         "Korean",
    }

    all_needs = {}    # {lang_code: [source_str, ...]}
    all_keep = {}     # {lang_code: {source: existing_translation}}
    total_new = 0

    for lang, filepath in TARGETS.items():
        print(f"\n{'─' * 40}")
        print(f"🎯 目標: {filepath.name} ({lang})")

        if not filepath.exists():
            print(f"  📄 檔案不存在，從 translations.ts 建立模板...")
            filepath.write_text(base_text, encoding="utf-8")
            existing = {}
        else:
            existing = parse_ts_as_dict(filepath)
        print(f"  現有已翻譯: {sum(1 for v in existing.values() if v is not None)}/{len(existing)}")

        to_translate = []
        keep_translation = {}
        for entry in base_entries:
            src = entry["source"]
            old_trans = existing.get(src)
            if old_trans is not None:
                keep_translation[src] = old_trans
            else:
                to_translate.append(src)

        print(f"  需新增/翻譯: {len(to_translate)} 個條目")
        all_needs[lang] = to_translate
        all_keep[lang] = keep_translation
        total_new += len(to_translate)

    # ── 第二階段：一次性確認 + API 呼叫 ──
    if total_new == 0:
        print(f"\n{'=' * 60}")
        print("✅ 所有語言皆已是最新，無需翻譯！")
        print("=" * 60)
        return

    print(f"\n{'=' * 60}")
    print(f"📋 總計 {total_new} 個待翻譯條目（分布在 {sum(1 for v in all_needs.values() if v)} 種語言中）")
    print("─" * 40)
    for lang, needs in all_needs.items():
        if needs:
            lang_display = lang_name_map.get(lang, lang)
            print(f"  {lang_display} ({lang}): {len(needs)} 個")
            for s in needs:
                print(f"     - {s}")
    print("=" * 60)

    answer = input(f"❓ 是否一次調用 DeepSeek 翻譯以上全部? (y/n): ").strip().lower()
    if answer != "y":
        print("⏭️ 已取消")
        # 未翻譯的寫入仍會保留為 unfinished
        for lang, filepath in TARGETS.items():
            keep_translation = all_keep[lang]
            for src in all_needs[lang]:
                keep_translation[src] = ""
            new_entries = [_make_entry(e, keep_translation) for e in base_entries]
            filepath.write_text(build_ts_xml(new_entries, base_text), encoding="utf-8")
            print(f"  💾 {filepath.name} (保留未翻譯)")
        return

    # 收集需要翻譯的語言
    active_langs = {lang: lang_name_map.get(lang, lang)
                    for lang, needs in all_needs.items() if needs}

    print(f"\n🤖 單次 API 呼叫 → 翻譯 {total_new} 個條目到 {len(active_langs)} 種語言...")
    all_translations = translate_via_deepseek_batch(base_sources, active_langs)

    # ── 分發結果並寫入 ──
    for lang, filepath in TARGETS.items():
        keep_translation = all_keep[lang]
        if lang in all_translations:
            for src, trans in zip(base_sources, all_translations[lang]):
                if src in all_needs[lang]:
                    keep_translation[src] = trans
                    status = "✅" if trans else "❌"
                    print(f"  {status} [{lang}] {src} → {trans}")

        new_entries = [_make_entry(e, keep_translation) for e in base_entries]
        filepath.write_text(build_ts_xml(new_entries, base_text), encoding="utf-8")
        print(f"  💾 已寫入: {filepath.name}")

    print(f"\n{'=' * 60}")
    print("🎉 同步完成！")
    print("=" * 60)


def _make_entry(entry, keep: dict) -> dict:
    src = entry["source"]
    trans = keep.get(src, "")
    return {
        "location": entry["location"],
        "source": src,
        "translation": trans,
        "type": "" if trans else "unfinished",
    }


if __name__ == "__main__":
    main()
