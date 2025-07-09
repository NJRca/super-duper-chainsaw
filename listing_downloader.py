import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import List, Dict
import time
from io import BytesIO

from PIL import Image

import requests
from bs4 import BeautifulSoup

CONFIG_FILE = Path("config.json")
PROCESSED_FILE = Path("processed_urls.json")
LOG_FILE = Path("scrape.log")
DEFAULT_BASE_DIR = Path("listings")
TAGS_FILE = Path("tags.json")
DEFAULT_DELAY = 1.0

def load_config() -> Dict:
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open() as f:
            return json.load(f)
    return {"base_dir": str(DEFAULT_BASE_DIR)}

def save_config(cfg: Dict) -> None:
    with CONFIG_FILE.open("w") as f:
        json.dump(cfg, f, indent=2)

def load_processed() -> List[str]:
    if PROCESSED_FILE.exists():
        with PROCESSED_FILE.open() as f:
            return json.load(f)
    return []

def save_processed(urls: List[str]) -> None:
    with PROCESSED_FILE.open("w") as f:
        json.dump(urls, f, indent=2)

def load_tags() -> Dict[str, List[str]]:
    if TAGS_FILE.exists():
        with TAGS_FILE.open() as f:
            return json.load(f)
    return {"architectural_style_tags": [],
            "room_feature_tags": [],
            "unique_feature_tags": []}

def sanitize(text: str) -> str:
    text = re.sub(r"[\\/:*?<>|]", "_", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:100]

def extract_listing_data(html: str) -> Dict:
    soup = BeautifulSoup(html, "lxml")
    data = {
        "address": "unknown_address",
        "price": "",
        "description": "",
    }

    if soup.title:
        data["address"] = soup.title.text.strip()

    address_tag = soup.find("meta", property="og:title")
    if address_tag and address_tag.get("content"):
        data["address"] = address_tag["content"].strip()

    price_tag = soup.find(string=re.compile(r"\$[\d,]+"))
    if price_tag:
        data["price"] = price_tag.strip()

    desc_tag = soup.find("meta", property="og:description")
    if desc_tag and desc_tag.get("content"):
        data["description"] = desc_tag["content"].strip()

    return data

def detect_tags(text: str, tags: List[str]) -> List[str]:
    """Return list of tag names (without leading '#') detected in text."""
    text_norm = re.sub(r"\W+", "", text.lower())
    found = []
    for tag in tags:
        keyword = re.sub(r"\W+", "", tag.lstrip("#").lower())
        if keyword and keyword in text_norm:
            found.append(keyword)
    return found

def find_image_urls(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    urls = set()
    for img in soup.find_all("img"):
        src = img.get("data-src") or img.get("src")
        if not src:
            continue
        src_lower = src.lower()
        if any(token in src_lower for token in ["thumb", "small", "video", "tour", "360"]):
            continue
        if os.path.splitext(src_lower)[1] in [".mp4", ".mov", ".webm", ".gif"]:
            continue
        if not src.startswith("http"):
            src = requests.compat.urljoin(base_url, src)
        urls.add(src)
    return list(urls)

def download_images(urls: List[str], folder: Path, session: requests.Session, delay: float) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for idx, url in enumerate(urls, 1):
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "").lower()
            ext = os.path.splitext(url)[1].split("?", 1)[0].lower()
            if "image/webp" in content_type or ext == ".webp":
                img = Image.open(BytesIO(resp.content))
                filename = folder / f"img_{idx}.jpg"
                img.convert("RGB").save(filename, "JPEG", quality=95)
            else:
                if ext not in [".jpg", ".jpeg", ".png"]:
                    ext = ".jpg"
                filename = folder / f"img_{idx}{ext}"
                with open(filename, "wb") as f:
                    f.write(resp.content)
            time.sleep(delay)
        except Exception as e:
            logging.exception("Failed to download %s: %s", url, e)

def process_url(url: str, base_dir: Path, processed: List[str], tags: Dict[str, List[str]],
                session: requests.Session, delay: float) -> None:
    if url in processed:
        logging.info("Skipping already processed URL: %s", url)
        return

    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        time.sleep(delay)
    except Exception as e:
        logging.error("Failed to fetch %s: %s", url, e)
        return

    data = extract_listing_data(resp.text)
    logging.info("Fetched data for %s: %s", url, data)

    style_tags = detect_tags(data.get("description", ""), tags.get("architectural_style_tags", []))
    feature_tags = detect_tags(
        data.get("description", ""),
        tags.get("room_feature_tags", []) + tags.get("unique_feature_tags", [])
    )

    folder_name = sanitize(data.get("address", "listing"))
    target_dir = base_dir / folder_name
    for tag in feature_tags + style_tags:
        target_dir = target_dir / tag

    image_urls = find_image_urls(resp.text, url)
    download_images(image_urls, target_dir, session, delay)

    processed.append(url)
    save_processed(processed)

def main(argv: List[str]) -> int:
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Download listing images and organize them")
    parser.add_argument("urls", nargs="+", help="Listing URLs")
    parser.add_argument("--base-dir", help="Base directory to save listings")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Delay between requests in seconds")
    args = parser.parse_args(argv)

    cfg = load_config()
    base_dir = Path(args.base_dir or cfg.get("base_dir", DEFAULT_BASE_DIR))
    cfg["base_dir"] = str(base_dir)
    save_config(cfg)

    tags = load_tags()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ListingBot/1.0)"})

    processed = load_processed()
    for url in args.urls:
        process_url(url, base_dir, processed, tags, session, args.delay)

    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
