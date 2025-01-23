import os
import praw
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validate environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
USER_AGENT = os.getenv("USER_AGENT")

if not all([CLIENT_ID, CLIENT_SECRET, USER_AGENT]):
    raise ValueError("Missing Reddit API credentials in environment variables.")

# Initialize Reddit API client
try:
    reddit = praw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT
    )
except Exception as e:
    logger.error("Failed to initialize Reddit client: %s", e)
    raise

# Function to extract the code from the post text
def extract_code(post_text):
    """Extract the code from post text using regex."""
    match = re.search(r"\*\*Code:\*\*\s*(\S+)", post_text, re.IGNORECASE)
    if match:
        return match.group(1)  # Return the captured code
    return None

def fetch_latest_codes(subreddit_name, keyword):
    """
    Fetch the latest posts containing gift codes from a subreddit.

    Args:
        subreddit_name (str): The name of the subreddit to search.
        keyword (str): The keyword to search for in the posts.

    Returns:
        list: A list of extracted codes.
    """
    try:
        subreddit = reddit.subreddit(subreddit_name)
        codes = []

        for submission in subreddit.search(query=keyword.lower(), time_filter='month'):
            if submission.is_self:  # Check if it's a text post
                code = extract_code(submission.selftext)
                if code:
                    codes.append(code)

        return codes
    except Exception as e:
        logger.error("Error fetching codes: %s", e)
        return []

def main():
    """Main function to test fetching gift codes."""
    subreddit_name = "whiteoutsurvival"  # Replace with your subreddit
    keyword = "gift code"  # Replace with your search keyword

    logger.info("Fetching codes from subreddit: %s with keyword: %s", subreddit_name, keyword)
    codes = fetch_latest_codes(subreddit_name, keyword)

    if codes:
        logger.info("Extracted Codes: %s", codes)
    else:
        logger.info("No codes found.")

if __name__ == "__main__":
    main()
