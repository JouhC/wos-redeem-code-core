import aiohttp
import asyncio
import hashlib
import time
import logging
import pandas as pd
from itertools import islice
from utils.captcha_solver import CaptchaSolver
from app.db.database import update_captcha_feedback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redemption API endpoint
URL = "https://wos-giftcode-api.centurygame.com/api"
HTTP_HEADER = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}
captcha_solver = CaptchaSolver()

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
    
    async def get_captcha_and_solve(self, player_id, salt, delay=2, max_retries=5):
        """Get CAPTCHA then solve it for a logged-in player with retry on 429 Too Many Requests."""
        if player_id not in self.players_data:
            logger.info(f"Error: Player {player_id} is not logged in.")
            return None
        
        await asyncio.sleep(delay)

        captcha_request_data = self.players_data[player_id]["request_data"].copy()

        retries = 0
        backoff = 1  # Start with 1 second backoff

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

                    if captcha_response.get("msg") != "SUCCESS":
                        logger.info(f"Captcha retrieval failed for player {player_id}: {captcha_response}")
                        return None
                    
                    self.players_data[player_id]['to_solve'] = captcha_response

                    return captcha_solver.solve(captcha_response)
    
            except aiohttp.ClientError as e:
                logger.info(f"Captcha - Network error for player {player_id}: {e}")
            except Exception as e:
                logger.info(f"Captcha - Unexpected error for player {player_id}: {e}")

    async def redeem_code(self, player_id, code, salt, delay=1, max_retries=5):
        """Redeems a gift code for a logged-in player with retry on 429 Too Many Requests."""
        if player_id not in self.players_data:
            logger.info(f"Error: Player {player_id} is not logged in.")
            return None
        
        await asyncio.sleep(delay)

        redeem_request_data = self.players_data[player_id]["request_data"].copy()
        redeem_request_data["cdk"] = code

        retries = 0
        backoff = 1  # Start with 1 second backoff

        while retries <= max_retries:
            try:
                redeem_request_data["captcha_code"], captcha_id = await self.get_captcha_and_solve(player_id, salt)
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
                    redeem_response = await response.json()

                    err_code = redeem_response.get("err_code")
                    if err_code == 40014:
                        result = f"Player {player_id}: The gift code '{code}' doesn't exist!"
                        success, expired = False, True
                    elif err_code == 40007:
                        result = f"Player {player_id}: The gift code '{code}' is expired!"
                        success, expired = False, True
                    elif err_code in (20000, 40008):  # Successfully claimed or already claimed
                        result = f"Player {player_id}: Successful redemption for gift code '{code}'!"
                        success, expired = True, False
                    elif err_code == 40005:
                        result = f"Player {player_id}: Already claimed redemption for gift code '{code}'!"
                        success, expired = True, False
                    elif err_code == 40004:  # Timeout or retry
                        result = f"Player {player_id}: Unsuccessful redemption for '{code}'. Please retry."
                        logger.warning(result)

                        await asyncio.sleep(backoff)
                        success, expired = False, False
                        backoff *= 2  # Exponential backoff
                        retries += 1
                        continue  # Retry request
                    elif err_code == 40103:  # CAPTCHA CHECK ERROR.
                        result = f"Player {player_id}: Unsuccessful redemption for '{code}'. CAPTCHA CHECK ERROR."
                        logger.warning(result)
                        await asyncio.sleep(backoff)
                        success, expired = False, False
                        backoff *= 2
                        retries += 1
                        continue # Retry request
                    else:
                        result = f"Player {player_id}: Redemption failed for '{code}' with unexpected error. {redeem_response}"
                        success, expired = False, False

                    if success:
                        update_captcha_feedback(str(captcha_id))  # Update captcha feedback in DB

                    return {"message": result, "success": success, "player_id": player_id, "code": code, "expired": expired}

            except aiohttp.ClientError as e:
                result = f"Network error during redemption for player {player_id}: {e}"
                success, expired = False, False
                print(result, redeem_response)
                break  # No retries for network errors

            except Exception as e:
                result = f"Unexpected error during redemption for player {player_id}: {e}"
                success, expired = False, False
                print(result, redeem_response)
                break  # No retries for unknown errors

        # If max retries exceeded
        result = f"Player {player_id}: Max retries exceeded. Redemption failed for '{code}'."
        return {"message": result, "success": False, "player_id": player_id, "code": code, "expired": False}

    async def close_session(self):
        """Closes the session when done."""
        await self.session.close()

async def process_logins_batches(players_list, salt, batch_size=30):
    player_api = PlayerAPI()

    def batch_iterator(lst, batch_size):
        it = iter(lst)
        while True:
            batch = list(islice(it, batch_size))
            if not batch:
                break
            yield batch

    try:
        for i, batch in enumerate(batch_iterator(players_list, batch_size)):
            # Process players in batches (max 30 per batch per code)
            login_tasks = [player_api.login_player(player_id, salt) for player_id in batch]
            login_results = await asyncio.gather(*login_tasks, return_exceptions=True)

            update_list = []
            player_tokens = []
            for login in login_results:
                if login and 'token' in login:
                    if login['token']['fid'] in update_list:
                        continue
                    player_tokens.append(login['token'])
                    update_list.append(login['token']['fid'])
            
            if i < len(players_list) // batch_size:
                logger.info(f"Batch {i + 1} processed. Waiting before next batch...")
                await asyncio.sleep(60)  # Wait before processing the next batch

    except Exception as e:
        logger.info(f"An error occurred: {e}")
    
    finally:
        await player_api.close_session()  # Close session when done
        return player_tokens

async def process_redemption_batches(unredeemed_data, salt, update_progress=None, batch_size=5):
    player_api = PlayerAPI()
    
    def batch_iterator(df, batch_size):
        """Yield batches of the DataFrame by index"""
        it = iter(df.index)
        while True:
            batch = list(islice(it, batch_size))
            if not batch:
                break
            yield df.loc[batch]

    redeem_results = []
    player_tokens = []

    try:
        all_codes = unredeemed_data['code'].unique()
        total_batches = sum(
            (len(group) + batch_size - 1) // batch_size
            for _, group in unredeemed_data.groupby('code')
        )
        progress_multiplier = 50 // total_batches if total_batches else 1
        batch_index = 0

        for code in all_codes:
            code_df = unredeemed_data[unredeemed_data['code'] == code]

            for batch in batch_iterator(code_df, batch_size):
                # Step 1: Login
                player_ids = batch['fid'].unique()
                login_tasks = [player_api.login_player(fid, salt) for fid in player_ids]
                login_results = await asyncio.gather(*login_tasks, return_exceptions=True)
                player_tokens.extend(login['token'] for login in login_results if login and 'token' in login)

                login_df = pd.DataFrame({
                    'fid': player_ids,
                    'login_result': login_results
                })

                # Step 2: Merge login results back into batch
                batch = batch.merge(login_df, on='fid', how='left')

                # Step 3: Prepare redeem tasks
                redeem_tasks = []
                for row in batch.itertuples(index=False):
                    if isinstance(row.login_result, Exception):
                        logger.info(f"[{code}] Login failed for fid={row.fid}: {row.login_result}")
                        continue
                    redeem_tasks.append(player_api.redeem_code(row.fid, code, salt))

                if redeem_tasks:
                    batch_results = await asyncio.gather(*redeem_tasks, return_exceptions=True)
                    redeem_results.extend(batch_results)

                if update_progress:
                    update_progress(progress_multiplier)

                logger.info(f"[{code}] Batch {batch_index + 1} processed. Waiting before next batch...")
                await asyncio.sleep(1)  # 1 second delay
                batch_index += 1

    except Exception as e:
        logger.info(f"An error occurred: {e}")

    finally:
        logger.info("All batches are done.")
        logger.info(f"Results: {redeem_results}")
        await player_api.close_session()
        return player_tokens, redeem_results

# Example Usage
async def main():
    player_api = PlayerAPI()
    salt = "your_secret_salt"

    # List of 60 player IDs
    player_ids = [f"player_{i}" for i in range(1, 61)]
    gift_code = "PROMO2025"

    # Process players in batches (max 30 per batch per code)
    redeem_results = await player_api.process_players_in_batches(player_ids, gift_code, salt)

    for result in redeem_results:
        logger.info(result)

    await player_api.close_session()  # Close session when done

if __name__ == "__main__":
    # Run the async function
    asyncio.run(main())
