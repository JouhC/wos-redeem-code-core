import aiohttp
import asyncio
import hashlib
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redemption API endpoint
URL = "https://wos-giftcode-api.centurygame.com/api"
HTTP_HEADER = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

class PlayerAPI:
    def __init__(self):
        self.session = aiohttp.ClientSession()
        self.players_data = {}  # Stores player_id -> (session data, request data)

    async def login_player(self, player_id, salt, max_retries=5):
        """Logs in a player and stores request data for reuse."""
        if player_id in self.players_data:
            return self.players_data[player_id]  # Already logged in

        request_data = {
            "fid": player_id,
            "time": int(time.time() * 1000)
        }
        request_data["sign"] = hashlib.md5(
            f"fid={request_data['fid']}&time={request_data['time']}{salt}".encode("utf-8")
        ).hexdigest()

        backoff = 1

        for attempt in range(1, max_retries + 1):
            try:
                async with self.session.post(f"{URL}/player", json=request_data, headers=HTTP_HEADER, timeout=30) as response:
                    if response.status == 429:
                        logger.warning(f"Player {player_id}: Rate limited (attempt {attempt}). Retrying in {backoff} seconds...")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue

                    response.raise_for_status()
                    login_response = await response.json()

                    if login_response.get("msg") != "success":
                        logger.info(f"Login failed for player {player_id}: {login_response}")
                        return None

                    # Cache and return on success
                    self.players_data[player_id] = {
                        "token": login_response.get("data", {}),
                        "request_data": request_data
                    }
                    return self.players_data[player_id]

            except aiohttp.ClientError as e:
                logger.info(f"Network error for player {player_id} on attempt {attempt}: {e}")
            except Exception as e:
                logger.info(f"Unexpected error for player {player_id} on attempt {attempt}: {e}")

            await asyncio.sleep(backoff)
            backoff *= 2  # Double backoff even on other exceptions

        logger.error(f"Login failed after {max_retries} attempts for player {player_id}")
        return None

    
    async def get_captcha(self, player_id, salt, delay=2, max_retries=5):
        """Get CAPTCHA for a logged-in player with retry logic on rate limits and specific error codes."""
        if player_id not in self.players_data:
            logger.info(f"Error: Player {player_id} is not logged in.")
            return None

        # Wait longer if CAPTCHA is already being solved
        await asyncio.sleep(30 if 'to_solve' in self.players_data[player_id] else delay)

        request_data = self.players_data[player_id]["request_data"].copy()
        backoff = 1

        for attempt in range(1, max_retries + 1):
            try:
                async with self.session.post(f"{URL}/captcha", json=request_data, headers=HTTP_HEADER, timeout=30) as response:
                    if response.status == 429:
                        logger.warning(f"Player {player_id}: Rate limited (attempt {attempt}). Retrying in {backoff} seconds...")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue

                    response.raise_for_status()
                    captcha_response = await response.json()

                    err_code = captcha_response.get("err_code")
                    msg = captcha_response.get("msg")

                    if err_code == 40009:
                        logger.info(f"Token expired for {player_id}. Re-logging in.")
                        self.players_data.pop(player_id, None)
                        await self.login_player(player_id, salt)
                        continue

                    if err_code == 40100:
                        logger.info(f"Captcha Get too Frequent for {player_id}. Waiting 60s.")
                        await asyncio.sleep(30)
                        continue

                    if msg != "SUCCESS":
                        logger.info(f"Captcha retrieval failed for player {player_id}: {captcha_response}")
                        return None

                    self.players_data[player_id]["to_solve"] = captcha_response
                    return captcha_response  # Success

            except aiohttp.ClientError as e:
                logger.info(f"Captcha - Network error for player {player_id} on attempt {attempt}: {e}")
            except Exception as e:
                logger.info(f"Captcha - Unexpected error for player {player_id} on attempt {attempt}: {e}")

            await asyncio.sleep(backoff)
            backoff *= 2

        logger.error(f"Failed to retrieve CAPTCHA for player {player_id} after {max_retries} attempts.")
        return None


    async def redeem_code(self, player_id, code, captcha_solution, salt, delay=1, max_retries=5):
        """Redeems a gift code for a logged-in player with retry logic on rate limits."""
        if player_id not in self.players_data:
            logger.info(f"Error: Player {player_id} is not logged in.")
            return None

        await asyncio.sleep(delay)
        base_request_data = self.players_data[player_id]["request_data"].copy()
        base_request_data["cdk"] = code

        backoff = 1

        for attempt in range(1, max_retries + 1):
            try:
                request_data = base_request_data.copy()
                request_data["captcha_code"] = captcha_solution
                request_data["sign"] = hashlib.md5(
                    f"captcha_code={request_data['captcha_code']}&cdk={request_data['cdk']}&fid={request_data['fid']}&time={request_data['time']}{salt}".encode("utf-8")
                ).hexdigest()

                async with self.session.post(f"{URL}/gift_code", json=request_data, headers=HTTP_HEADER, timeout=30) as response:
                    if response.status == 429:
                        logger.warning(f"Player {player_id}: Rate limited (attempt {attempt}). Retrying in {backoff} seconds...")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue

                    response.raise_for_status()
                    return await response.json()  # Success

            except aiohttp.ClientError as e:
                logger.warning(f"Network error during redemption for player {player_id} (attempt {attempt}): {e}")
            except Exception as e:
                logger.warning(f"Unexpected error during redemption for player {player_id} (attempt {attempt}): {e}")

            await asyncio.sleep(backoff)
            backoff *= 2

        logger.error(f"Failed to redeem code for player {player_id} after {max_retries} attempts.")
        return None


    async def close_session(self):
        """Closes the session when done."""
        await self.session.close()

async def main():
    pass

if __name__ == "__main__":
    # Run the async function
    asyncio.run(main())
