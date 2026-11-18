#!/usr/bin/env python3
"""Dated copies of the daily data for the private site 「왕이 될 상」 (AGENTS §3-41).

The daily job overwrites web/*.json and data/snapshot.json every run. This keeps one copy per day on the `archive`
branch of the same public repository, so a later reader can see what the market looked like that day:

    <out>/<YYYY-MM-DD>/close.json · snapshot.json · flows.json · alerts.json · themes.json
    <out>/latest.json      {v, updated, latest, newest, days:[{d, f:[names]}]}  newest first

Rules
  * The folder date is the file's own date — close.json `date`, snapshot.json `asOf`[:10], the others `asOf` —
    never the day the job ran. (Investor flows land at the 21:30 run, alerts also at 07:50, and GitHub's schedule
    can run hours late, so the run date would file a day's data under the wrong day.)
  * Files are copied byte for byte (raw material only; nothing is recomputed). A later run with the same date replaces
    that day's copy, e.g. the 21:30 flows replace the 16:40 ones.
  * Only files already published in web/ and data/ are archived. Analyst consensus is NOT archived here — it goes to
    the Worker's private KV (worker/src/consensus.js).

Usage
    python3 scripts/archive_daily.py --out .archive                      # this checkout's files
    python3 scripts/archive_daily.py --out .archive --from-git origin/main   # backfill every version in git history
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
# name, path in the repo, the field that carries the file's date
FILES = [
    ("close", "web/close.json", "date"),
    ("snapshot", "data/snapshot.json", "asOf"),
    ("flows", "web/flows.json", "asOf"),
    ("alerts", "web/alerts.json", "asOf"),
    ("themes", "web/themes.json", "asOf"),
]
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
DAY_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FIRST_DAY = "2026-01-01"


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def file_date(raw: bytes, field: str):
    """The file's own date (YYYY-MM-DD) or None if the bytes are not a dated JSON object."""
    try:
        d = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(d, dict):
        return None
    m = DATE_RE.match(str(d.get(field) or ""))
    if not m:
        return None
    day = m.group(1)
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return None
    if day < FIRST_DAY or day > today_kst():
        return None
    return day


def put(out: Path, day: str, name: str, raw: bytes) -> bool:
    """Write <out>/<day>/<name>.json if it differs. True if written."""
    target = out / day / f"{name}.json"
    if target.exists() and target.read_bytes() == raw:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, target)
    return True


def write_latest(out: Path):
    days = []
    for p in sorted((x for x in out.iterdir() if x.is_dir() and DAY_DIR_RE.match(x.name)), key=lambda x: x.name, reverse=True):
        names = sorted(f.stem for f in p.glob("*.json"))
        if names:
            days.append({"d": p.name, "f": names})
    latest = next((x["d"] for x in days if "close" in x["f"]), None)   # newest full trading day (has the KRX close)
    body = {
        "v": 1,
        "updated": datetime.now(KST).isoformat(timespec="seconds"),
        "latest": latest,
        "newest": days[0]["d"] if days else None,
        "days": days,
    }
    old = None
    lp = out / "latest.json"
    if lp.exists():
        try:
            old = json.loads(lp.read_bytes())
        except ValueError:
            old = None
    if old and {k: v for k, v in old.items() if k != "updated"} == {k: v for k, v in body.items() if k != "updated"}:
        return False                      # same days → leave the file alone (no commit just for the timestamp)
    lp.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return True


README = """# 판세 날짜별 보관 (archive)

판세 매일 작업이 덮어쓰는 파일의 날짜별 사본이에요. 개인 사이트 「왕이 될 상」이 읽어요 (AGENTS.md §3-41).

- `<YYYY-MM-DD>/close.json · snapshot.json · flows.json · alerts.json · themes.json` — 원본 그대로(바이트 단위 복사).
- 폴더 날짜는 실행한 날이 아니라 **파일 안의 날짜**예요: close.json `date`, snapshot.json `asOf` 앞 10자, 나머지 `asOf`.
  그래서 한 날짜 폴더에 모든 파일이 있지 않을 수 있어요(아침 07:50 경보만 있는 날, 휴장일 아침 등).
- `latest.json` = `{v, updated, latest(KRX 종가가 있는 가장 최근 날), newest, days:[{d, f}]}` 최신순.
- 출처: 네이버 증권 · 한국거래소 지정(시장 경보). 판세 화면과 같은 원천이에요. 증권사 컨센서스는 여기 두지 않아요.
- 이 브랜치는 매일 작업(`.github/workflows/daily.yml`)만 써요. 손으로 고치지 않아요.
"""


def ensure_readme(out: Path):
    p = out / "README.md"
    if not p.exists() or p.read_text(encoding="utf-8") != README:
        p.write_text(README, encoding="utf-8")


def from_tree(out: Path, root: Path):
    wrote = []
    for name, rel, field in FILES:
        p = root / rel
        if not p.exists():
            print(f"skip {rel}: missing", file=sys.stderr)
            continue
        raw = p.read_bytes()
        day = file_date(raw, field)
        if not day:
            print(f"skip {rel}: no valid `{field}` date", file=sys.stderr)
            continue
        if put(out, day, name, raw):
            wrote.append(f"{day}/{name}")
    return wrote


def git(*args) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True).stdout


def from_git(out: Path, ref: str):
    """Every committed version of each file, oldest first, so the last version of a day wins."""
    wrote = []
    for name, rel, field in FILES:
        shas = git("log", "--reverse", "--format=%H", ref, "--", rel).decode().split()
        for sha in shas:
            try:
                raw = git("show", f"{sha}:{rel}")
            except subprocess.CalledProcessError:
                continue                  # the commit deleted the file
            day = file_date(raw, field)
            if day and put(out, day, name, raw):
                wrote.append(f"{day}/{name}@{sha[:7]}")
    return wrote


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="the archive branch's checkout")
    ap.add_argument("--root", default=str(ROOT), help="the main checkout to copy from (default: this repo)")
    ap.add_argument("--from-git", metavar="REF", help="backfill from every commit of REF instead of the working tree")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    wrote = from_git(out, a.from_git) if a.from_git else from_tree(out, Path(a.root))
    ensure_readme(out)
    changed = write_latest(out)
    print(f"archive: {len(wrote)} file(s) written" + (", latest.json updated" if changed else ""))
    for w in wrote:
        print("  " + w)


if __name__ == "__main__":
    main()
