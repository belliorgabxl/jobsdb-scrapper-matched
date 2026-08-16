"""
Job Alert — ดึงงานตาม SEARCH_TARGETS ใน jobsdb_scraper.py, กรองด้วยเงื่อนไขที่
สนใจด้านล่าง แล้วแจ้งเตือนผ่าน Discord webhook เฉพาะ "งานใหม่" ที่ยังไม่เคยแจ้ง
มาก่อน (เทียบจาก job_id ที่เก็บไว้ใน seen_jobs.json)

รันด้วยมือ:
    python job_alert.py

รันอัตโนมัติทุก 6 ชม.: ดู setup_task_scheduler.ps1

ต้องตั้งค่า Discord webhook ก่อนใช้งาน — เลือกวิธีใดวิธีหนึ่ง:
    1) ตั้ง environment variable: DISCORD_WEBHOOK_URL
    2) สร้างไฟล์ config.json (ดู config.example.json) แล้วใส่ discord_webhook_url
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import requests

from jobsdb_scraper import (
    SEARCH_TARGETS,
    build_search_url,
    fetch_page,
    parse_job_listings,
    polite_sleep,
)

BASE_DIR = Path(__file__).resolve().parent
SEEN_JOBS_FILE = BASE_DIR / "seen_jobs.json"
CONFIG_FILE = BASE_DIR / "config.json"


INTERESTED_KEYWORDS = ["software developer", "software engineer"]

INTERESTED_WORK_ARRANGEMENTS = ["hybrid"]

EXCLUDED_KEYWORDS: list[str] = []


def job_matches_interest(job: dict) -> bool:
    haystack = f"{job.get('title') or ''} {job.get('short_description') or ''}".lower()

    if EXCLUDED_KEYWORDS and any(kw.lower() in haystack for kw in EXCLUDED_KEYWORDS):
        return False

    if INTERESTED_KEYWORDS and not any(kw.lower() in haystack for kw in INTERESTED_KEYWORDS):
        return False

    if INTERESTED_WORK_ARRANGEMENTS:
        work_arrangement = (job.get("work_arrangement") or "").lower()
        if work_arrangement not in [w.lower() for w in INTERESTED_WORK_ARRANGEMENTS]:
            return False

    return True


# ---------------------------------------------------------------------------
# state: กันแจ้งเตือนซ้ำ
# ---------------------------------------------------------------------------
def load_seen_job_ids() -> set[str]:
    if not SEEN_JOBS_FILE.exists():
        return set()
    with open(SEEN_JOBS_FILE, encoding="utf-8") as f:
        return set(json.load(f).keys())


def save_seen_job_ids(job_ids: set[str]):
    existing = {}
    if SEEN_JOBS_FILE.exists():
        with open(SEEN_JOBS_FILE, encoding="utf-8") as f:
            existing = json.load(f)

    now = datetime.now().isoformat(timespec="seconds")
    for job_id in job_ids:
        existing.setdefault(job_id, now)

    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------
def get_discord_webhook_url() -> str | None:
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        return os.environ["DISCORD_WEBHOOK_URL"]
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f).get("discord_webhook_url")
    return None


def notify_discord(jobs: list[dict], webhook_url: str):
    """ส่งแจ้งเตือนเป็น embed (Discord จำกัด 10 embeds ต่อ 1 ข้อความ จึงแบ่งเป็นชุด)"""
    for i in range(0, len(jobs), 10):
        chunk = jobs[i : i + 10]
        embeds = [
            {
                "title": (job.get("title") or "ไม่มีชื่อตำแหน่ง")[:256],
                "url": job.get("url"),
                "description": (job.get("short_description") or "")[:300],
                "color": 0x2ECC71,
                "fields": [
                    {"name": "บริษัท", "value": job.get("company") or "-", "inline": True},
                    {"name": "สถานที่", "value": job.get("location") or "-", "inline": True},
                    {"name": "รูปแบบงาน", "value": job.get("work_arrangement") or "-", "inline": True},
                    {"name": "เงินเดือน", "value": job.get("salary") or "ไม่ระบุ", "inline": True},
                ],
            }
            for job in chunk
        ]
        payload = {"embeds": embeds}
        if i == 0:
            payload["content"] = f"🔔 พบงานใหม่ตรงเงื่อนไข {len(jobs)} ตำแหน่ง"

        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def run():
    webhook_url = get_discord_webhook_url()
    if not webhook_url:
        print(
            "[ผิดพลาด] ไม่พบ Discord webhook URL — ตั้งค่า environment variable "
            "DISCORD_WEBHOOK_URL หรือสร้างไฟล์ config.json (ดู config.example.json)"
        )
        return

    seen_ids = load_seen_job_ids()
    all_matches = []

    for i, (keyword, location) in enumerate(SEARCH_TARGETS, start=1):
        search_url = build_search_url(keyword, location)
        print(f"[{i}/{len(SEARCH_TARGETS)}] ตรวจสอบ: '{keyword}' @ {location or 'ทุกพื้นที่'}")

        html = fetch_page(search_url)
        if html is None:
            continue

        jobs = parse_job_listings(html)
        matches = [job for job in jobs if job_matches_interest(job)]
        print(f"  พบ {len(jobs)} งานทั้งหมด, ตรงเงื่อนไข {len(matches)} งาน")
        all_matches.extend(matches)

        if i < len(SEARCH_TARGETS):
            polite_sleep()

    new_matches = [job for job in all_matches if job.get("job_id") and job["job_id"] not in seen_ids]

    if new_matches:
        print(f"พบงานใหม่ {len(new_matches)} ตำแหน่ง กำลังแจ้งเตือนผ่าน Discord...")
        notify_discord(new_matches, webhook_url)
    else:
        print("ไม่มีงานใหม่ที่ตรงเงื่อนไขในรอบนี้")

    save_seen_job_ids({job["job_id"] for job in all_matches if job.get("job_id")})


if __name__ == "__main__":
    run()
