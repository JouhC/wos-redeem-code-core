import os
import asyncpraw
import re
import logging
import asyncio
import xml.etree.ElementTree as ET

import requests

from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validate environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
USER_AGENT = os.getenv("USER_AGENT")

if not all([CLIENT_ID, CLIENT_SECRET, USER_AGENT]):
    raise ValueError("Missing Reddit API credentials in environment variables.")

def extract_code(post_text):
    """Extract the code from post text using regex."""
    match = re.search(r'(?i)(?:\*\*code:\*\*|gift\s+code:)\s*`?([^\s`]+)`?', post_text, re.IGNORECASE)
    return match.group(1) if match else None

def _fetch_rss_codes(url):
    """Fetch gift codes from one RSS URL."""
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    codes = []

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{4,32}", title):
            codes.append(title)
            continue

        item_text = " ".join(text for text in item.itertext() if text)
        code = extract_code(item_text)
        if code:
            codes.append(code)

    return codes


async def fetch_codes_from_urls_async(urls):
    """Fetch configured RSS URLs concurrently, without one failure stopping others."""
    async def fetch_one(url):
        try:
            codes = await asyncio.to_thread(_fetch_rss_codes, url)
            logger.info("Fetched %d codes from %s", len(codes), url)
            return codes
        except Exception as exc:
            logger.error("Error fetching gift codes from %s: %s", url, exc)
            return []

    results = await asyncio.gather(*(fetch_one(url) for url in urls))
    return [code for codes in results for code in codes]


async def _fetch_reddit_codes_async(subreddit_name, keyword):
    """Fetch gift codes from Reddit."""
    reddit = asyncpraw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT
    )
    codes = []
    post_count = 0
    try:
        subreddit = await reddit.subreddit(subreddit_name)
        async for submission in subreddit.search(query=keyword.lower(), time_filter='month'):
            post_count += 1
            if submission.is_self:
                code = extract_code(submission.selftext)
                if code:
                    codes.append(code)
        return codes
    except Exception as e:
        logger.error("Error fetching codes from Reddit: %s", e)
        return []
    finally:
        await reddit.close()
        logger.info("Total of %d codes / %d Reddit posts fetched.", len(codes), post_count)
        logger.info("Reddit session closed.")


async def fetch_latest_codes_async(subreddit_name, keyword, urls=None):
    """
    Fetch the latest posts containing gift codes from a subreddit.

    Args:
        subreddit_name (str): The name of the subreddit to search.
        keyword (str): The keyword to search for in the posts.
        urls (list[str] | None): RSS feed URLs. Defaults to GIFT_CODE_URLS.

    Returns:
        list: A deduplicated list of extracted codes from Reddit and the feeds.
    """
    feed_urls = settings.GIFT_CODE_URLS if urls is None else urls
    reddit_codes, url_codes = await asyncio.gather(
        _fetch_reddit_codes_async(subreddit_name, keyword),
        fetch_codes_from_urls_async(feed_urls),
    )
    return list(dict.fromkeys(reddit_codes + url_codes))

async def main():
    """Main function to test fetching gift codes."""
    subreddit_name = "whiteoutsurvival"
    keyword = "gift code"

    logger.info("Fetching codes from subreddit: %s with keyword: %s", subreddit_name, keyword)
    codes = await fetch_latest_codes_async(subreddit_name, keyword)

    if codes:
        logger.info("Extracted Codes: %s", codes)
    else:
        logger.info("No codes found.")

if __name__ == "__main__":
    asyncio.run(main())
