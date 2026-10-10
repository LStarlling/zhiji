#!/usr/bin/env python3
"""输出分身当前状态（JSON），供入口菜单使用。仅依赖标准库。"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from extract import HOME

IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
STALE_DAYS = 90  # 高把握规则超过这么多天没有新证据，认为"可能已陈旧"


def header(profile, key):
    m = re.search(r"^- {}[：:]\s*(.*)$".format(re.escape(key)), profile, re.M)
    return (m.group(1).strip() if m else "") or ""


def stale_rules(profile, store_path):
    """统计正式区域（待验证之前）中，把握度为"高"且超过 STALE_DAYS 天没有新证据的规则数量。
    只需要规则行里的证据 id，去 signals.jsonl 查最新的 ts，算距今天数。
    查不到 ts 的 id（如已删除的信号）跳过；一条规则只要有一条证据在期限内就不算陈旧。
    """
    if not store_path.exists():
        return 0

    # 建立 id -> ts 索引（只扫一次文件）
    ts_map = {}
    for line in open(store_path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            s = json.loads(line)
            if s.get("id") and s.get("ts"):
                ts_map[s["id"]] = s["ts"]
        except ValueError:
            continue

    now = datetime.now(tz=timezone.utc)
    formal = profile.split("## 待验证")[0]
    stale = 0
    for line in formal.splitlines():
        # 只看把握度为"高"的正式规则行
        if not re.match(r"^- \[R\d+\]", line):
            continue
        if "把握：高" not in line and "把握:高" not in line:
            continue
        # 提取所有证据 id
        m = re.search(r"证据[：:]\s*([\w,\s]+)", line)
        if not m:
            stale += 1  # 没有证据字段，保守计为陈旧
            continue
        ids = [x.strip() for x in m.group(1).split(",") if x.strip()]
        if not ids:
            stale += 1
            continue
        # 找这条规则最新的证据时间
        latest_ts = max((ts_map[i] for i in ids if i in ts_map), default=None)
        if latest_ts is None:
            # 所有证据 id 都查不到（可能是手写规则），跳过，不计为陈旧
            continue
        try:
            # 兼容带 Z 和带时区偏移的 ISO 8601
            ts_str = latest_ts.replace("Z", "+00:00")
            ts_dt = datetime.fromisoformat(ts_str)
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            days = (now - ts_dt).days
        except ValueError:
            continue
        if days > STALE_DAYS:
            stale += 1

    return stale


def main():
    profile_path = HOME / "profile.md"
    st = {"版本": (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip(),
          "已建档": profile_path.exists()}
    profile = profile_path.read_text(encoding="utf-8", errors="ignore") if st["已建档"] else ""
    formal = profile.split("## 待验证")[0]
    st["规则数"] = len(re.findall(r"^- \[R\d+\]", formal, re.M))
    st["最近校准"] = {"选择题": header(profile, "最近校准（选择题）") or header(profile, "最近校准"),
                    "打回题": header(profile, "最近校准（打回题）")}
    st["memory文件"] = header(profile, "memory 文件")
    st["本人昵称"] = header(profile, "本人昵称")
    pending = HOME / "pending"
    st["待学习信号"] = sum(1 for f in pending.glob("*.jsonl") for l in open(f, encoding="utf-8", errors="ignore")
                       if l.strip()) if pending.is_dir() else 0
    inbox = HOME / "inbox"
    st["收件箱截图"] = sum(1 for p in inbox.iterdir() if p.suffix.lower() in IMAGES) if inbox.is_dir() else 0
    used_file = HOME / "eval" / "used.txt"
    used = set(used_file.read_text(encoding="utf-8").split()) if used_file.exists() else set()
    tests = {"选择题": 0, "打回题": 0}
    store = HOME / "signals.jsonl"
    if store.exists():
        for l in open(store, encoding="utf-8", errors="ignore"):
            if '"split": "test"' not in l:
                continue
            s = json.loads(l)
            if s["id"] not in used:
                tests["选择题" if s.get("options") else "打回题"] += 1
    st["可用考题"] = tests
    st["已有卡片"] = (HOME / "card.json").exists()
    # 陈旧规则：高把握规则中超过 STALE_DAYS 天没有新证据的数量
    st["陈旧规则数"] = stale_rules(profile, store) if st["已建档"] else 0
    print(json.dumps(st, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
