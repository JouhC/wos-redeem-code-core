import os
import asyncpraw
import re
import logging
import asyncio

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
    match = re.search(r"\*\*Code:\*\*\s*(\S+)", post_text, re.IGNORECASE)
    return match.group(1) if match else None

async def fetch_latest_codes_async(subreddit_name, keyword):
    """
    Fetch the latest posts containing gift codes from a subreddit.

    Args:
        subreddit_name (str): The name of the subreddit to search.
        keyword (str): The keyword to search for in the posts.

    Returns:
        list: A list of extracted codes.
    """
    reddit = asyncpraw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT
    )

    try:
        subreddit = await reddit.subreddit(subreddit_name)
        codes = []
        async for submission in subreddit.search(query=keyword.lower(), time_filter='month'):
            if submission.is_self:
                code = extract_code(submission.selftext)
                if code:
                    codes.append(code)
        return codes
    except Exception as e:
        logger.error("Error fetching codes: %s", e)
        return []
    finally:
        await reddit.close()  # Explicitly close Reddit client
        logger.info("Reddit session closed.")

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