import requests
import hashlib
import time
import logging
from db.database import deactivate_giftcode
import random
import aiohttp
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redemption API endpoint
URL = "https://wos-giftcode-api.centurygame.com/api"
HTTP_HEADER = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}
SEMAPHORE = asyncio.Semaphore(30)  # Limit concurrent requests to 30


async def login_player2(player_id, salt):
    """Logs in a player and returns their details."""
    max_retries = 5
    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries):
            try:
                request_data = {
                    "fid": player_id,
                    "time": int(time.time() * 1000)  # Convert to milliseconds
                }
                request_data["sign"] = hashlib.md5(
                    f"fid={request_data['fid']}&time={request_data['time']}{salt}".encode("utf-8")
                ).hexdigest()

                async with session.post(f"{URL}/player", json=request_data, headers=HTTP_HEADER, timeout=30) as response:
                    response.raise_for_status()
                    login_response = await response.json()

                    if login_response.get("msg") != "success":
                        print(login_response)
                        print(f"Login failed for player: {player_id}")
                        return None

                    return login_response.get("data", {})

            except aiohttp.ClientError as e:
                print(f"Network error for player {player_id}: {e}")
            except Exception as e:
                print(f"Unexpected error for player {player_id}: {e}")
            await asyncio.sleep(2)  # Backoff before retrying

    return None

async def login_player(player_id, salt):
    """Logs in a player and returns their details."""
    async with aiohttp.ClientSession() as session:
        try:
            async with SEMAPHORE:  # Enforce concurrency limit
                request_data = {
                    "fid": player_id,
                    "time": int(time.time() * 1000)  # Convert to milliseconds
                }
                request_data["sign"] = hashlib.md5(
                    f"fid={request_data['fid']}&time={request_data['time']}{salt}".encode("utf-8")
                ).hexdigest()

                async with session.post(f"{URL}/player", json=request_data, headers=HTTP_HEADER, timeout=30) as response:
                    response.raise_for_status()
                    login_response = await response.json()

                    if login_response.get("msg") != "success":
                        print(f"Login failed for player: {player_id}")
                        return None

                    return login_response.get("data", {})

        except aiohttp.ClientError as e:
            print(f"Network error for player {player_id}: {e}")
        except Exception as e:
            print(f"Unexpected error for player {player_id}: {e}")

    return None

async def login_players_in_batches(player_ids, salt):
    """Logs in players in controlled concurrent batches."""
    tasks = []
    for i, player_id in enumerate(player_ids):
        tasks.append(login_player(player_id, salt))

        # Rate limit: Wait every 30 requests
        if (i + 1) % 30 == 0:
            print("Pausing to respect rate limit...")
            await asyncio.sleep(60)  # Enforce the 30 requests per minute limit

    results = await asyncio.gather(*tasks)
    return results

async def redeem_code(player_id, salt, code):
    """
    Redeem a gift code on Whiteout Survival.

    Args:
        player_id (str): The player's ID.
        salt (str): The secret salt used for signature generation.
        code (str): The gift code to redeem.

    Returns:
        None
    """
    max_retries = 5
    base_delay = 1  # seconds

    for attempt in range(max_retries):
        try:
            login_response = await login_player(player_id, salt)

            if login_response is None:
                print(f"Failed to login player {player_id}")
                break

            request_data = {
                        "fid": player_id,
                        "time": int(time.time() * 1000)  # Convert to milliseconds
                    }
            
            # Update request data with the gift code
            request_data["cdk"] = code
            request_data["sign"] = hashlib.md5(
                f"cdk={request_data['cdk']}&fid={request_data['fid']}&time={request_data['time']}{salt}".encode("utf-8")
            ).hexdigest()

            # Send gift code redemption request
            redeem_request = requests.post(
                URL + "/gift_code", data=request_data, headers=HTTP_HEADER, timeout=30
            )
            redeem_request.raise_for_status()
            redeem_response = redeem_request.json()

            # Handle response
            err_code = redeem_response.get("err_code")
            if err_code == 40014:
                print("\nThe gift code doesn't exist!")
                result = f"The gift code '{code}' doesn't exist!"
                success = False
            elif err_code == 40007:
                print("\nThe gift code is expired!")
                result = f"The gift code '{code}' is expired!"
                deactivate_giftcode(code)
                success = False
            elif err_code in (20000, 40008):  # Successfully claimed or already claimed
                print("\nSuccessful redemption!")
                result = f"Player {login_response['data']['nickname']}. Successful redemption for gift code '{code}'!"
                success = True
            elif err_code == 40005:
                print("\nAlready claimed redemption!")
                result = f"Player {login_response['data']['nickname']}. Already claimed redemption for gift code '{code}'!"
                success = True
            elif err_code == 40004:  # Timeout or retry
                print("\nUnsuccessful redemption. Please retry.")
                result = f"Player {login_response['data']['nickname']}. Unsuccessful redemption for '{code}'. Please retry."
                success = False
            else:
                print("\nRedemption failed with unexpected error.")
                print("Error response:", redeem_response)
                result = f"Player {login_response['data']['nickname']}. Redemption failed for '{code}' with unexpected error."
                success = False

            return {
                "message": result,
                "success": success
            }

        except requests.exceptions.RequestException as e:
            if redeem_request.status_code in [429, 500, 502, 503, 504]:
                # Exponential backoff with jitter
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                print(f"\nNetwork error occurred: {e}")
                break
        except Exception as e:
            print(f"\nAn unexpected error occurred: {e}")
            break

    return {
        "message": f"Player {player_id}. Gift code '{code}'. Redemption failed after {max_retries} attempts.",
        "success": False
    }
