#!/bin/bash
# add_topic.sh - emojiji お題追加スクリプト
# Usage: ./add_topic.sh 2026-04-01 "エイプリルフール" "嘘が許される日。" "🤥,😂,📱,🎭,❓,🤡,📰,💬,✨,😈,🔔,🎪"

set -euo pipefail

if [ $# -ne 4 ]; then
  echo "Usage: $0 <date> <word> <desc> <hints>"
  echo "  date:  YYYY-MM-DD"
  echo "  word:  お題ワード"
  echo "  desc:  説明文"
  echo "  hints: カンマ区切り絵文字12個"
  echo ""
  echo "Example:"
  echo "  $0 2026-04-01 \"エイプリルフール\" \"嘘が許される日。\" \"🤥,😂,📱,🎭,❓,🤡,📰,💬,✨,😈,🔔,🎪\""
  exit 1
fi

DATE="$1"
WORD="$2"
DESC="$3"
HINTS="$4"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JSON_FILE="$SCRIPT_DIR/topics.json"

if [ ! -f "$JSON_FILE" ]; then
  echo "{}" > "$JSON_FILE"
fi

python3 -c "
import json, sys

date = sys.argv[1]
word = sys.argv[2]
desc = sys.argv[3]
hints = [h.strip() for h in sys.argv[4].split(',')]

with open('$JSON_FILE', 'r', encoding='utf-8') as f:
    data = json.load(f)

data[date] = {
    'word': word,
    'desc': desc,
    'hints': hints
}

sorted_data = dict(sorted(data.items()))

with open('$JSON_FILE', 'w', encoding='utf-8') as f:
    json.dump(sorted_data, f, ensure_ascii=False, indent=2)

print(f'Added: {date} - {word}')
" "$DATE" "$WORD" "$DESC" "$HINTS"
