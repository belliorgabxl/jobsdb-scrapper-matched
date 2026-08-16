"""
JobsDB Scraper (สำหรับเรียนรู้/ทดลองส่วนตัว ปริมาณน้อย)
=========================================================

⚠️ อ่านก่อนใช้งาน — ผลตรวจสอบจริงกับ th.jobsdb.com (ไม่ใช่การเดา):

1) robots.txt (https://th.jobsdb.com/robots.txt) สำหรับ User-agent: *
   - Disallow: */job/        -> ห้ามดึงหน้ารายละเอียดงาน (URL ที่มี /job/)
   - Disallow: *?            -> ห้ามดึง URL ที่มี query string ใดๆ เลย
   - Disallow: /graphql, /api/jobsearch/, */profile/me/, */profiles/search*
   ผลกระทบสำคัญ: pagination ของ JobsDB ใช้ ?page=2, ?page=3 ... ซึ่งมี "?"
   จึงถูก Disallow ด้วย กติกานี้ทำให้ "ดึงได้แค่หน้าแรกของแต่ละคำค้นหาเท่านั้น"
   สคริปต์นี้จึงไม่มีฟีเจอร์ pagination แบบไล่หน้า — ถ้าต้องการข้อมูลมากขึ้น
   ให้ค้นหลายคำ/หลายพื้นที่แทน (ดู SEARCH_TARGETS) ไม่ใช่ไล่ page

2) บั๊กสำคัญที่พบในโค้ดต้นฉบับ: robotparser.read() ใช้ urllib ภายในซึ่งส่ง
   User-Agent เริ่มต้น "Python-urllib/x.x" — เว็บนี้ตอบ 403 Forbidden ให้ UA
   แบบนี้ทันที เมื่อ read() เจอ 403 มันจะ set disallow_all=True เงียบๆ
   (ไม่ throw exception ที่เห็นชัด) ผลคือ check_robots_txt_allows() จะคืนค่า
   False เสมอ ไม่ว่า URL อะไรก็ตาม -> สคริปต์เดิมจะไม่เคยดึงข้อมูลได้จริงเลย
   แก้โดยดึง robots.txt เองด้วย requests + HEADERS เดียวกับที่ใช้ดึงหน้าเว็บ
   แล้วค่อยป้อนให้ RobotFileParser.parse() แทนการเรียก .read()

3) โครงสร้าง HTML จริง (SSR, ไม่มี XHR/JSON endpoint แยก) — inspect จริงแล้ว:
   - การ์ดแต่ละงาน: <article data-automation="normalJob" data-job-id="...">
   - ชื่อตำแหน่ง:     [data-automation="jobTitle"]           (เป็น <a href="/job/..">)
   - บริษัท:          [data-automation="jobCompany"]
   - สถานที่:         [data-automation="jobLocation"]
   - เงินเดือน:       [data-automation="jobSalary"]           (ไม่ใช่ทุกงานจะมี)
   - รายละเอียดย่อ:   [data-automation="jobShortDescription"]
   - วันที่ลงประกาศ:  [data-automation="jobListingDate"]
   href ของ jobTitle ชี้ไป /job/{id}?... ซึ่ง Disallow ตามข้อ 1 — โค้ดนี้จะ
   "เก็บ URL ไว้เป็นข้อมูล" เท่านั้น แต่จะ "ไม่ยิง request ไปหน้านั้นเด็ดขาด"

4) ข้อจำกัดการใช้งานเดิมยังคงอยู่: ใช้ส่วนตัว/เรียนรู้เท่านั้น ห้ามใช้เพื่อการ
   พาณิชย์ ห้าม scrape ปริมาณมาก ต้องตรวจ robots.txt ก่อนทุก request (โค้ดนี้
   ทำให้อัตโนมัติและ fail-closed ถ้าอ่าน robots.txt ไม่ได้)

ติดตั้ง dependency ก่อนใช้งาน:
    pip install -r requirements.txt
"""

from __future__ import annotations

import argparse
import csv
import random
import time
from urllib import robotparser
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://th.jobsdb.com"
HEADERS = {
    "User-Agent": "MyLearningScraper/1.0 (personal educational project)"
}
MIN_DELAY_SEC = 3 
MAX_DELAY_SEC = 6  
MAX_RETRIES = 3     
REQUEST_TIMEOUT_SEC = 10

SEARCH_TARGETS: list[tuple[str, str | None]] = [
    ("software developer", "Bangkok"),
    ("python developer", "Bangkok"),
]

_robots_parser_cache: robotparser.RobotFileParser | None = None



def _get_robots_parser() -> robotparser.RobotFileParser:
    """ดึงและ parse robots.txt เอง (แคชไว้ใช้ตลอด session ไม่ดึงซ้ำทุก request)

    ใช้ requests + HEADERS ของเราแทน RobotFileParser.read() เพราะ read()
    ใช้ urllib ซึ่งส่ง User-Agent เริ่มต้นที่โดนเว็บนี้ตอบ 403 (ดูหมายเหตุข้อ 2)
    """
    global _robots_parser_cache
    if _robots_parser_cache is not None:
        return _robots_parser_cache

    rp = robotparser.RobotFileParser()
    robots_url = urljoin(BASE_URL, "/robots.txt")
    try:
        response = requests.get(robots_url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SEC)
        response.raise_for_status()
        rp.parse(response.text.splitlines())
    except requests.RequestException as e:
        print(f"[คำเตือน] อ่าน robots.txt ไม่ได้ ({e}) — ปฏิเสธทุก request เพื่อความปลอดภัย")
        rp.disallow_all = True

    _robots_parser_cache = rp
    return rp


def check_robots_txt_allows(url: str, user_agent: str = "*") -> bool:
    """เช็คว่า robots.txt อนุญาตให้ crawl URL นี้หรือไม่ ก่อนดึงข้อมูลทุกครั้ง"""
    return _get_robots_parser().can_fetch(user_agent, url)


def polite_sleep():
    """หน่วงเวลาแบบสุ่มเพื่อไม่ให้ยิง request ถี่เกินไป"""
    time.sleep(random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC))



def fetch_page(url: str) -> str | None:
    """ดึง HTML ของหน้าเว็บ พร้อมเช็ค robots.txt ก่อนทุกครั้ง + retry เมื่อ error ชั่วคราว"""
    if not check_robots_txt_allows(url):
        print(f"[ข้าม] robots.txt ไม่อนุญาตให้ดึงข้อมูลจาก: {url}")
        return None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SEC)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 10))
                print(f"[ระวัง] โดน rate limit (429) รอ {retry_after} วิ แล้วลองใหม่...")
                time.sleep(retry_after)
                continue

            response.raise_for_status()
            return response.text

        except requests.RequestException as e:
            print(f"[ผิดพลาด] (ครั้งที่ {attempt}/{MAX_RETRIES}) ดึงหน้าเว็บไม่สำเร็จ {url}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)  # exponential backoff: 2, 4, 8 วิ

    return None


def parse_job_listings(html: str) -> list[dict]:
    """parse ข้อมูลตำแหน่งงานจาก HTML โดยใช้ selector ที่ inspect จาก HTML จริง"""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    job_cards = soup.select("article[data-automation='normalJob']")

    if not job_cards:

        job_list_container = soup.select_one("[data-automation='search-result-job-list']")
        if job_list_container:
            job_cards = job_list_container.select("article")

    for card in job_cards:
        title_el = card.select_one("[data-automation='jobTitle']")
        company_el = card.select_one("[data-automation='jobCompany']")
        location_el = card.select_one("[data-automation='jobLocation']")
        salary_el = card.select_one("[data-automation='jobSalary']")
        desc_el = card.select_one("[data-automation='jobShortDescription']")
        date_el = card.select_one("[data-automation='jobListingDate']")
        work_arrangement_el = card.select_one("[data-testid='work-arrangement']")

        jobs.append({
            "job_id": card.get("data-job-id"),
            "title": title_el.get_text(strip=True) if title_el else None,
            "company": company_el.get_text(strip=True) if company_el else None,
            "location": location_el.get_text(strip=True) if location_el else None,
            "work_arrangement": work_arrangement_el.get_text(strip=True).strip("()") if work_arrangement_el else None,
            "salary": salary_el.get_text(strip=True) if salary_el else None,
            "short_description": desc_el.get_text(strip=True) if desc_el else None,
            "listed": date_el.get_text(strip=True) if date_el else None,
            "url": urljoin(BASE_URL, title_el["href"]) if title_el and title_el.get("href") else None,
        })

    return jobs


def save_to_csv(jobs: list[dict], filename: str = "jobs_output.csv"):
    if not jobs:
        print("ไม่มีข้อมูลให้บันทึก")
        return

    fieldnames = jobs[0].keys()
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(jobs)

    print(f"บันทึกข้อมูล {len(jobs)} รายการลงไฟล์ {filename} เรียบร้อยแล้ว")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def build_search_url(keyword: str, location: str | None = None) -> str:
    """สร้าง URL หน้าแรกของผลค้นหา (ไม่มี query string เพื่อให้ผ่าน robots.txt)"""
    slug_keyword = keyword.strip().lower().replace(" ", "-")
    path = f"/{slug_keyword}-jobs"
    if location:
        slug_location = location.strip().replace(" ", "-")
        path += f"/in-{slug_location}"
    return urljoin(BASE_URL, path)


def main(search_targets: list[tuple[str, str | None]], output_filename: str = "jobs_output.csv"):
    all_jobs = []

    for i, (keyword, location) in enumerate(search_targets, start=1):
        search_url = build_search_url(keyword, location)
        print(f"[{i}/{len(search_targets)}] กำลังดึง: '{keyword}' @ {location or 'ทุกพื้นที่'} -> {search_url}")

        html = fetch_page(search_url)
        if html is None:
            continue

        jobs = parse_job_listings(html)
        print(f"  พบ {len(jobs)} ตำแหน่งงาน (เฉพาะหน้าแรก — ดูหมายเหตุเรื่อง robots.txt/pagination ด้านบนไฟล์)")
        all_jobs.extend(jobs)

        if i < len(search_targets):
            polite_sleep()

    save_to_csv(all_jobs, output_filename)
    return all_jobs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="JobsDB Thailand scraper (หน้าแรกของผลค้นหาเท่านั้น ตาม robots.txt)"
    )
    parser.add_argument("--keyword", default=None, help="คำค้นหาตำแหน่งงาน เช่น 'python developer'")
    parser.add_argument("--location", default=None, help="พื้นที่ทำงาน เช่น Bangkok, Chiang-Mai")
    parser.add_argument("--output", default="jobs_output.csv", help="ชื่อไฟล์ CSV ปลายทาง")
    args = parser.parse_args()

    if args.keyword:
        targets = [(args.keyword, args.location)]
    else:
        targets = SEARCH_TARGETS

    main(targets, args.output)
