#!/usr/bin/env python3
"""
emojiji daily topic generator.
Fetches Japanese trending news, uses Claude API to generate a satirical topic,
and updates topics.json.

Usage:
  ANTHROPIC_API_KEY=sk-... python scripts/generate_topic.py
  ANTHROPIC_API_KEY=sk-... python scripts/generate_topic.py --date 2026-03-10
  ANTHROPIC_API_KEY=sk-... python scripts/generate_topic.py --dry-run
"""

import argparse
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import anthropic
except ImportError:
    anthropic = None

# ── Config ──

CLAUDE_MODEL = "claude-sonnet-4-20250514"

RSS_SOURCES = [
    {
        "name": "Google Trends JP",
        "url": "https://trends.google.co.jp/trending/rss?geo=JP",
    },
    {
        "name": "Yahoo Japan News",
        "url": "https://news.yahoo.co.jp/rss/topics/top-picks.xml",
    },
    {
        "name": "Google News JP",
        "url": "https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja",
    },
]

SYSTEM_PROMPT = """\
あなたは「emojiji」という日本語の日替わり時事風刺ゲームのお題を作るAIです。

ゲームの仕組み:
- プレイヤーは毎日1つの時事ワードを見て、それを絵文字だけで風刺アートとして表現します
- お題には「word」（2〜8文字の日本語）、「desc」（1〜2文の風刺的説明）、「hints」（関連絵文字12個）が必要です

良いお題の条件:
- 今日の日本のニュースやトレンドに基づいていること
- 絵文字で表現しやすいテーマであること（抽象的すぎるものは避ける）
- 風刺・皮肉が効いていて、クスっと笑えるもの
- 固有名詞（人名）は避け、現象・社会問題・話題を表す言葉にすること
- 政治的に極端すぎないこと

wordのルール:
- 2〜8文字（漢字、カタカナ、ひらがな可）
- 日本語として自然で、一般の人が理解できる言葉
- 例: 「AI失業」「円安」「闇バイト」「少子化」

descのルール:
- 1〜2文。句点「。」で終わる
- 風刺的・皮肉っぽいトーン
- 短く切れ味のある表現
- 例: 「下がり続ける円の価値。輸出には追い風、暮らしには逆風。」

hintsのルール:
- 必ず12個の絵文字（Emoji）
- お題に関連する絵文字を選ぶ
- 直接的なもの（🤖→AI）と間接的なもの（😰→不安）をバランスよく混ぜる
- 重複なし
"""

USER_PROMPT_TEMPLATE = """\
以下は今日の日本のニュース・トレンドです:

{headlines}

{recent_topics}

上記から1つ最もふさわしいテーマを選び（または複数を組み合わせて）、emojijiのお題を生成してください。

以下のJSON形式のみで回答してください（JSON以外のテキストは不要）:
{{
  "word": "ワード（2〜8文字）",
  "desc": "風刺的な説明文。1〜2文。",
  "hints": ["emoji1", "emoji2", "emoji3", "emoji4", "emoji5", "emoji6", "emoji7", "emoji8", "emoji9", "emoji10", "emoji11", "emoji12"]
}}
"""


# ── RSS Fetching ──

def fetch_rss(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "emojiji-bot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] Failed to fetch {url}: {e}", file=sys.stderr)
        return ""


def extract_titles(xml_text):
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
        items = root.findall(".//item/title")
        return [item.text.strip() for item in items if item.text]
    except ET.ParseError as e:
        print(f"  [WARN] XML parse error: {e}", file=sys.stderr)
        return []


def fetch_trending_topics():
    all_titles = []
    for source in RSS_SOURCES:
        print(f"Fetching from {source['name']}...")
        xml_text = fetch_rss(source["url"])
        titles = extract_titles(xml_text)
        print(f"  Got {len(titles)} titles")
        all_titles.extend(titles)
    return all_titles


# ── Claude API ──

def generate_topic_with_claude(headlines, api_key, existing_data=None):
    if anthropic is None:
        print("[ERROR] anthropic package not installed. Run: pip install anthropic", file=sys.stderr)
        return None

    # Deduplicate
    seen = set()
    unique = []
    for h in headlines:
        h_clean = h.strip()
        if h_clean and h_clean not in seen:
            seen.add(h_clean)
            unique.append(h_clean)
    unique = unique[:30]

    headlines_text = "\n".join(f"- {h}" for h in unique)

    # Recent topics to avoid duplicates
    recent_topics = ""
    if existing_data:
        sorted_dates = sorted(existing_data.keys(), reverse=True)[:7]
        if sorted_dates:
            words = [existing_data[d]["word"] for d in sorted_dates]
            recent_topics = f"直近のお題（重複を避けてください）: {', '.join(words)}"

    user_msg = USER_PROMPT_TEMPLATE.format(
        headlines=headlines_text,
        recent_topics=recent_topics,
    )

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        text = response.content[0].text.strip()

        # Handle markdown code blocks
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        result = json.loads(text)

        # Validate
        assert isinstance(result.get("word"), str), "word must be string"
        assert 2 <= len(result["word"]) <= 8, f"word length {len(result['word'])} out of range"
        assert isinstance(result.get("desc"), str), "desc must be string"
        assert isinstance(result.get("hints"), list), "hints must be list"
        assert len(result["hints"]) == 12, f"hints count {len(result['hints'])} != 12"

        return result

    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse JSON: {e}", file=sys.stderr)
        print(f"  Response: {text[:500]}", file=sys.stderr)
        return None
    except (anthropic.APIError if anthropic else Exception) as e:
        print(f"[ERROR] Claude API error: {e}", file=sys.stderr)
        return None
    except AssertionError as e:
        print(f"[ERROR] Validation failed: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}", file=sys.stderr)
        return None


# ── JSON Update ──

def get_target_date(args_date):
    if args_date:
        datetime.strptime(args_date, "%Y-%m-%d")
        return args_date
    jst = timezone(timedelta(hours=9))
    tomorrow = datetime.now(jst) + timedelta(days=1)
    return tomorrow.strftime("%Y-%m-%d")


def update_topics_json(target_date, topic, json_path):
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    if target_date in data:
        print(f"[SKIP] {target_date} already has topic: {data[target_date]['word']}")
        return False

    data[target_date] = {
        "word": topic["word"],
        "desc": topic["desc"],
        "hints": topic["hints"],
    }

    sorted_data = dict(sorted(data.items()))

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=2)
    f.close()

    print(f"[OK] Added topic for {target_date}: {topic['word']}")
    return True


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="Generate daily emojiji topic")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: tomorrow JST)")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    json_path = repo_root / "topics.json"

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[ERROR] ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    target_date = get_target_date(args.date)
    print(f"Target date: {target_date}")

    # Load existing data
    existing_data = {}
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
        if target_date in existing_data:
            print(f"[SKIP] Topic already exists for {target_date}: {existing_data[target_date]['word']}")
            sys.exit(0)

    # Fetch news
    print("\n=== Fetching trending topics ===")
    headlines = fetch_trending_topics()
    if not headlines:
        print("[FATAL] No headlines available", file=sys.stderr)
        sys.exit(1)

    # Generate with Claude
    print(f"\n=== Generating topic ({CLAUDE_MODEL}) ===")
    topic = generate_topic_with_claude(headlines, api_key, existing_data)
    if topic is None:
        print("[FATAL] Failed to generate topic", file=sys.stderr)
        sys.exit(1)

    print(f"  word: {topic['word']}")
    print(f"  desc: {topic['desc']}")
    print(f"  hints: {' '.join(topic['hints'])}")

    if args.dry_run:
        print("\n=== DRY RUN ===")
        print(json.dumps({target_date: topic}, ensure_ascii=False, indent=2))
        sys.exit(0)

    print(f"\n=== Updating {json_path} ===")
    update_topics_json(target_date, topic, json_path)


if __name__ == "__main__":
    main()
