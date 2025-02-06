from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import os
if not bool(os.getenv("RENDER")): 
    from dotenv import load_dotenv
    load_dotenv()  # Load .env file in local development
from db.database import (
    init_db, add_player, get_players, add_giftcode, get_giftcodes, deactivate_giftcode,
    record_redemption, get_redeemed_codes, update_players_table, update_player, get_unredeemed_code_player_list
)
from utils.fetch_gc_async import fetch_latest_codes_async
from utils.rclone import backup_db
from utils.wos_api import PlayerAPI, process_redemption_batches, process_logins_batches
import pandas as pd
import logging
from time import time
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("request_logger")

# Secret key for sign generation
SALT = os.getenv("SALT")
DEFAULT_PLAYER = os.getenv("DEFAULT_PLAYER")

# Check if running in production (Render sets the RENDER environment variable)
if not bool(os.getenv("RENDER")):
    async def init_default_player():
        init_db()
        player_api = PlayerAPI()
        login_response = await player_api.login_player(DEFAULT_PLAYER, SALT)
        add_player(login_response['token'])

    import asyncio
    asyncio.run(init_default_player())

# Initialize FastAPI app
app = FastAPI(
    title="Gift Code Redemption API",
    description="API for managing players, fetching gift codes, and redeeming them.",
    version="1.0.0"
)

# Middleware for logging requests and responses
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Log incoming request details
    start_time = time()
    logger.info(f"Request: {request.method} {request.url}")
    logger.info(f"Headers: {request.headers}")
    logger.info(f"Client Host: {request.client.host}")
    try:
        body = await request.body()
        logger.info(f"Body: {body.decode('utf-8')}")
    except Exception:
        logger.info("Body: Unable to retrieve")

    # Process the request and calculate response time
    response = await call_next(request)
    process_time = time() - start_time

    # Log response details
    logger.info(f"Response status: {response.status_code}")
    logger.info(f"Completed in {process_time:.2f}s")
    completed_time = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    logger.info(f"Completed datetime: {completed_time}")
    return response

# Models
class Player(BaseModel):
    player_id: str

class GiftCodeSetStatusInactive(BaseModel):
    code: str

class RedemptionRequest(BaseModel):
    player_id: str

@app.get("/")
async def root():
    return {"message": "Welcome to the Gift Code Redemption API!"}

# Player endpoints
@app.get("/players/list/")
async def list_players():
    players = get_players()
    return {"players": players}

@app.post("/players/create")
async def create_player(player: Player):
    try:
        player_api = PlayerAPI()
        login_response = await player_api.login_player(player.player_id, SALT)
        add_player(login_response['token'])
        message = backup_db()
        print(message)
        return {"message": f"Player '{player.player_id}' added successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/players/update/")
async def update_player_profile(player: Player):
    try:
        player_api = PlayerAPI()
        login_response = await player_api.login_player(player.player_id, SALT)
        update_player(login_response['token'])
        message = backup_db()
        print(message)
        return {"message": f"Player '{player.player_id}' info updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Gift code endpoints
@app.get("/giftcodes/fetch/")
async def fetch_giftcodes():
    fetched_codes = await fetch_latest_codes_async("whiteoutsurvival", "gift code")
    new_codes = []
    for code in fetched_codes:
        new_code = add_giftcode(code)
        if new_code is not None:
            new_codes.append(new_code)
    message = backup_db()
    print({"message": "Gift codes fetched and added to the database.", "new_codes": new_codes})
    return {"message": "Gift codes fetched and added to the database.", "new_codes": new_codes}

@app.get("/giftcodes/")
async def list_giftcodes():
    codes = get_giftcodes()
    return {"giftcodes": codes}

@app.post("/giftcodes/deactivate/")
async def set_inactive(code: GiftCodeSetStatusInactive):
    try:
        message = deactivate_giftcode(code.code)
        return {"message": f"{message}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Redemption endpoints
@app.post("/redeem/")
async def redeem_giftcode(request: RedemptionRequest):
    results = []
    codes = get_giftcodes()
    player_api = PlayerAPI()
    for code in codes:
        redeemed_codes = get_redeemed_codes(request.player_id)
        if code in redeemed_codes:
            result = {"message": f"Code '{code}' already redeemed for player '{request.player_id}'."}
        else:
            login_response = await player_api.login_player(request.player_id, SALT)
            result = await player_api.redeem_code(request.player_id, SALT, code)
            if result['success']:
                record_redemption(request.player_id, code)
        results.append(result)
    message = backup_db()
    print(message)
    return {"results": results}

@app.get("/redemptions/{player_id}/")
async def list_redeemed_codes(player_id: str):
    redeemed_codes = get_redeemed_codes(player_id)
    return {"player_id": player_id, "redeemed_codes": redeemed_codes}

@app.post("/backup-db/")
async def run_backup_db():
    message = backup_db()
    return {"result": message}

@app.post("/update-players/")
async def update_players():
    try:
        players = get_players()
        if not players:
            return {"message": "No subscribed players found. Exiting.", "players": []}  # Return empty list
        
        player_ids = []
        for player in players:
            player_ids.append(player['fid'])

        results = await process_logins_batches(player_ids, SALT)

        if results == []:
            print("No players updated.")
        else:
            update_players_table(results)
            print(f"{len(results)} players updated.")

        return get_players()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/automate-all/")
async def run_main_logic():
    """
    Run the main logic:
    - Fetch subscribed players.
    - Fetch new gift codes from the subreddit.
    - Merge new codes with the database.
    - Redeem codes for players.
    - Update the database with redemptions.
    """
    try:
        # Step 1: Fetch subscribed players
        players = get_players()
        
        if not players:
            return {"message": "No subscribed players found. Exiting."}

        player_ids = []
        for player in players:
            player_ids.append(player['fid'])

        new_codes = await fetch_latest_codes_async("whiteoutsurvival", "gift code")
        for code in new_codes:
            add_giftcode(code)
        
        all_codes = get_giftcodes()
        
        unredeemed_data = get_unredeemed_code_player_list()
        if unredeemed_data == []:
            return {
                "message": "No unredeemed codes found. Exiting.",
                "giftcodes": all_codes,
                "players": players}
        
        unredeemed_data = pd.DataFrame(get_unredeemed_code_player_list())

        # Process players in batches (max 30 per batch per code)
        player_tokens, redeem_results = await process_redemption_batches(unredeemed_data, SALT)

        for player in player_tokens:
            update_player(player)

        for result in redeem_results:
            if result['success']:
                record_redemption(result['player_id'], result['code'])
            else:
                print(f"Redemption failed for player {result['player_id']} with code {result['code']}")

        message = backup_db()
        print(message)
        return {
            "message": "Main logic executed successfully.",
            "giftcodes": all_codes,
            "players": get_players()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
