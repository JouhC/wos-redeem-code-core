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
            return self.players_data[player_id]  # Skip re-login if already logged in

        request_data = {
            "fid": player_id,
            "time": int(time.time() * 1000)  # Convert to milliseconds
        }
        request_data["sign"] = hashlib.md5(
            f"fid={request_data['fid']}&time={request_data['time']}{salt}".encode("utf-8")
        ).hexdigest()

        retries = 0
        backoff = 1  # Start with 1 second backoff

        while retries <= max_retries:
            try:
                async with self.session.post(f"{URL}/player", json=request_data, headers=HTTP_HEADER, timeout=30) as response:
                    if response.status == 429:
                        logger.warning(f"Player {player_id}: Rate limited. Retrying in {backoff} seconds...")
                        await asyncio.sleep(backoff)
                        backoff *= 2  # Exponential backoff
                        retries += 1
                        continue  # Retry request

                    response.raise_for_status()
                    login_response = await response.json()

                    if login_response.get("msg") != "success":
                        logger.info(f"Login failed for player {player_id}: {login_response}")
                        return None

                    self.players_data[player_id] = {
                        "token": login_response.get("data", {}),
                        "request_data": request_data
                    }
                    return self.players_data[player_id]

            except aiohttp.ClientError as e:
                logger.info(f"Network error for player {player_id}: {e}")
            except Exception as e:
                logger.info(f"Unexpected error for player {player_id}: {e}")

        return None
    
    async def get_captcha(self, player_id, salt, delay=2, max_retries=5):
        """Get CAPTCHA then solve it for a logged-in player with retry on 429 Too Many Requests."""
        if player_id not in self.players_data:
            logger.info(f"Error: Player {player_id} is not logged in.")
            return None
        
        if 'to_solve' in self.players_data[player_id]:
            await asyncio.sleep(30)
        else:
            await asyncio.sleep(delay)

        captcha_request_data = self.players_data[player_id]["request_data"].copy()

        retries = 0
        backoff = 1  # Start with 1 second backoff
        captcha_response = None

        while retries <= max_retries:
            try:
                async with self.session.post(f"{URL}/captcha", json=captcha_request_data, headers=HTTP_HEADER, timeout=30) as response:
                    if response.status == 429:
                        logger.warning(f"Player {player_id}: Rate limited. Retrying in {backoff} seconds...")
                        await asyncio.sleep(backoff)
                        backoff *= 2  # Exponential backoff
                        retries += 1
                        continue  # Retry request

                    response.raise_for_status()
                    captcha_response = await response.json()

                    if captcha_response.get("err_code") == 40009:
                        self.players_data.pop(player_id, None)
                        login_player = await self.login_player(player_id, salt)

                    if captcha_response.get("msg") != "SUCCESS":
                        logger.info(f"Captcha retrieval failed for player {player_id}: {captcha_response}")
                        return None
                    
                    self.players_data[player_id]['to_solve'] = captcha_response
    
            except aiohttp.ClientError as e:
                logger.info(f"Captcha - Network error for player {player_id}: {e}")
                continue
            except Exception as e:
                logger.info(f"Captcha - Unexpected error for player {player_id}: {e}")
                continue
        return captcha_response

    async def redeem_code(self, player_id, code, captcha_solution, salt, delay=1, max_retries=5):
        """Redeems a gift code for a logged-in player with retry on 429 Too Many Requests."""
        if player_id not in self.players_data:
            logger.info(f"Error: Player {player_id} is not logged in.")
            return None
        
        await asyncio.sleep(delay)

        redeem_request_data = self.players_data[player_id]["request_data"].copy()
        redeem_request_data["cdk"] = code

        retries = 0
        
        while retries <= max_retries:
            try:
                redeem_request_data["captcha_code"] = captcha_solution
                redeem_request_data["sign"] = hashlib.md5(
                    f"captcha_code={redeem_request_data['captcha_code']}&cdk={redeem_request_data['cdk']}&fid={redeem_request_data['fid']}&time={redeem_request_data['time']}{salt}".encode("utf-8")
                ).hexdigest()

                async with self.session.post(f"{URL}/gift_code", json=redeem_request_data, headers=HTTP_HEADER, timeout=30) as response:
                    if response.status == 429:
                        logger.warning(f"Player {player_id}: Rate limited. Retrying in {backoff} seconds...")
                        await asyncio.sleep(backoff)
                        backoff *= 2  # Exponential backoff
                        retries += 1
                        continue  # Retry request

                    response.raise_for_status()
                    result = await response.json()
                    break

            except aiohttp.ClientError as e:
                logger.warning(f"Network error during redemption for player {player_id}: {e}")
                result = None
            except Exception as e:
                logger.warning(f"Unexpected error during redemption for player {player_id}: {e}")
                result = None

        return result
 

    async def close_session(self):
        """Closes the session when done."""
        await self.session.close()

async def main():
    pass

if __name__ == "__main__":
    # Run the async function
    asyncio.run(main())
