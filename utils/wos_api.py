import aiohttp
import asyncio
import hashlib
import time
import logging
from collections import defaultdict
from itertools import islice

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

    async def login_player(self, player_id, salt):
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

        try:
            async with self.session.post(f"{URL}/player", json=request_data, headers=HTTP_HEADER, timeout=30) as response:
                response.raise_for_status()
                login_response = await response.json()

                if login_response.get("msg") != "success":
                    print(f"Login failed for player {player_id}: {login_response}")
                    return None

                self.players_data[player_id] = {
                    "token": login_response.get("data", {}),
                    "request_data": request_data
                }
                return self.players_data[player_id]

        except aiohttp.ClientError as e:
            print(f"Network error for player {player_id}: {e}")
        except Exception as e:
            print(f"Unexpected error for player {player_id}: {e}")

        return None

    async def redeem_code(self, player_id, code, salt):
        """Redeems a gift code for a logged-in player."""
        if player_id not in self.players_data:
            print(f"Error: Player {player_id} is not logged in.")
            return None

        # Use stored request data
        redeem_request_data = self.players_data[player_id]["request_data"].copy()
        redeem_request_data["cdk"] = code
        redeem_request_data["sign"] = hashlib.md5(
            f"cdk={redeem_request_data['cdk']}&fid={redeem_request_data['fid']}&time={redeem_request_data['time']}{salt}".encode("utf-8")
        ).hexdigest()

        try:
            async with self.session.post(f"{URL}/gift_code", json=redeem_request_data, headers=HTTP_HEADER, timeout=30) as response:
                response.raise_for_status()
                redeem_response = await response.json()

                err_code = redeem_response.get("err_code")
                if err_code == 40014:
                    result = f"Player {player_id}: The gift code '{code}' doesn't exist!"
                    success = False
                    expired = True
                elif err_code == 40007:
                    result = f"Player {player_id}: The gift code '{code}' is expired!"
                    success = False
                    expired = True
                elif err_code in (20000, 40008):  # Successfully claimed or already claimed
                    result = f"Player {player_id}: Successful redemption for gift code '{code}'!"
                    success = True
                    expired = False
                elif err_code == 40005:
                    result = f"Player {player_id}: Already claimed redemption for gift code '{code}'!"
                    success = True
                    expired = False
                elif err_code == 40004:  # Timeout or retry
                    result = f"Player {player_id}: Unsuccessful redemption for '{code}'. Please retry."
                    success = False
                    expired = False
                else:
                    result = f"Player {player_id}: Redemption failed for '{code}' with unexpected error."
                    success = False
                    expired = False
        except aiohttp.ClientError as e:
            result = f"Network error during redemption for player {player_id}: {e}"
            success = False
            expired = False
        except Exception as e:
            result = f"Unexpected error during redemption for player {player_id}: {e}"
            success = False
            expired = False
        finally:
            return {"message": result,
                    "success": success,
                    "player_id": player_id,
                    "code": code,
                    "expired": expired}

    async def process_players_in_batches2(self, player_ids, code, salt, batch_size=30):
        """Logs in players and redeems a gift code in batches to comply with API limits."""
        results = []
        for i in range(0, len(player_ids), batch_size):
            batch = player_ids[i:i + batch_size]
            print(f"Processing batch {i // batch_size + 1} of {len(player_ids) // batch_size + 1}")

            # Step 1: Log in all players in batch
            login_tasks = [self.login_player(player_id, salt) for player_id in batch]
            await asyncio.gather(*login_tasks)

            # Step 2: Redeem code for all logged-in players in batch
            redeem_tasks = [self.redeem_code(player_id, code, salt) for player_id in batch]
            batch_results = await asyncio.gather(*redeem_tasks)

            results.extend(batch_results)

            # Step 3: Wait 120 seconds before processing the next batch
            if i + batch_size < len(player_ids):
                print("Waiting 120 seconds before processing next batch...")
                await asyncio.sleep(120)

        return results
    
    async def process_players_in_batches3(self, df, salt, batch_size=30):
        """
        Logs in players in batches of 30 and redeems multiple codes per player.
        df: Pandas DataFrame with columns ['player_id', 'code']
        """
        # Step 1: Convert DataFrame into a dictionary {player_id: [code1, code2, ...]}
        player_codes = defaultdict(list)
        for _, row in df.iterrows():
            player_codes[str(row['fid'])].append(row['code'])  # Ensure player_id is a string

        unique_players = list(player_codes.keys())  # Unique player list
        results = []

        for i in range(0, len(unique_players), batch_size):
            batch_players = unique_players[i:i + batch_size]
            print(f"Processing batch {i // batch_size + 1} of {len(unique_players) // batch_size + 1}")

            # Step 2: Log in all players in the batch
            login_tasks = [self.login_player(player_id, salt) for player_id in batch_players]
            await asyncio.gather(*login_tasks)

            # Step 3: Redeem all codes for each logged-in player
            for player_id in batch_players:
                if player_id in self.players_data:
                    redeem_tasks = [self.redeem_code(player_id, code, salt) for code in player_codes[player_id]]
                    batch_results = await asyncio.gather(*redeem_tasks)
                    results.extend(batch_results)

            # Step 4: Wait 120 seconds before processing the next batch
            if i + batch_size < len(unique_players):
                print("Waiting 120 seconds before processing next batch...")
                await asyncio.sleep(120)

        return results
    

    
    async def process_players_in_batches(self, df, salt, batch_size=30):
        """
        Logs in players in batches of 30 and redeems multiple codes per player.
        df: Pandas DataFrame with columns ['player_id', 'code']
        """
        def batch_iterator(df, batch_size):
            it = iter(df.index)
            while True:
                batch = list(islice(it, batch_size))
                if not batch:
                    break
                yield df.loc[batch]
        

        for i, batch in enumerate(batch_iterator(df, batch_size)):
            login_tasks = [self.login_player(player_id, salt) for player_id in batch_players]

        
        # Step 1: Convert DataFrame into a dictionary {player_id: [code1, code2, ...]}
        player_codes = defaultdict(list)
        for _, row in df.iterrows():
            player_codes[str(row['fid'])].append(row['code'])  # Ensure player_id is a string

        unique_players = list(player_codes.keys())  # Unique player list
        results = []

        for i in range(0, len(unique_players), batch_size):
            batch_players = unique_players[i:i + batch_size]
            print(f"Processing batch {i // batch_size + 1} of {len(unique_players) // batch_size + 1}")

            # Step 2: Log in all players in the batch
            login_tasks = [self.login_player(player_id, salt) for player_id in batch_players]
            await asyncio.gather(*login_tasks)

            # Step 3: Redeem all codes for each logged-in player
            for player_id in batch_players:
                if player_id in self.players_data:
                    redeem_tasks = [self.redeem_code(player_id, code, salt) for code in player_codes[player_id]]
                    batch_results = await asyncio.gather(*redeem_tasks)
                    results.extend(batch_results)

            # Step 4: Wait 120 seconds before processing the next batch
            if i + batch_size < len(unique_players):
                print("Waiting 120 seconds before processing next batch...")
                await asyncio.sleep(120)

        return results

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
                print(f"Batch {i + 1} processed. Waiting before next batch...")
                await asyncio.sleep(60)  # Wait before processing the next batch

    except Exception as e:
        print(f"An error occurred: {e}")
    
    finally:
        await player_api.close_session()  # Close session when done
        return player_tokens

async def process_redemption_batches(unredeemed_data, salt, batch_size=30):
    player_api = PlayerAPI()

    def batch_iterator(df, batch_size):
        it = iter(df.index)
        while True:
            batch = list(islice(it, batch_size))
            if not batch:
                break
            yield df.loc[batch]

    redeem_results = []
    try:
        for i, batch in enumerate(batch_iterator(unredeemed_data, batch_size)):
            # Process players in batches (max 30 per batch per code)
            login_tasks = [player_api.login_player(row.fid, salt) for row in batch.itertuples(index=False)]
            login_results = await asyncio.gather(*login_tasks, return_exceptions=True)

            update_list = []
            player_tokens = []
            for login in login_results:
                if login and 'token' in login:
                    if login['token']['fid'] in update_list:
                        continue
                    player_tokens.append(login['token'])
                    update_list.append(login['token']['fid'])

            redeem_tasks = []
            for row, login_result in zip(batch.itertuples(index=False), login_results):
                if isinstance(login_result, Exception):
                    print(f"Login failed for fid={row.fid}: {login_result}")
                    continue  # Skip redemption if login failed
                
                redeem_tasks.append(player_api.redeem_code(row.fid, row.code, salt))

            if redeem_tasks:
                batch_results = await asyncio.gather(*redeem_tasks, return_exceptions=True)
                redeem_results.extend(batch_results)
            
            if i < len(unredeemed_data) // batch_size:
                print(f"Batch {i + 1} processed. Waiting before next batch...")
                await asyncio.sleep(60)  # Wait before processing the next batch

    except Exception as e:
        print(f"An error occurred: {e}")
    
    finally:
        await player_api.close_session()  # Close session when done
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
        print(result)

    await player_api.close_session()  # Close session when done

if __name__ == "__main__":
    # Run the async function
    asyncio.run(main())
