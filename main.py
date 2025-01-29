from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import os
if not bool(os.getenv("RENDER")): 
    from dotenv import load_dotenv
    load_dotenv()  # Load .env file in local development
from db.database import (
    init_db, add_player, get_players, add_giftcode, get_giftcodes, deactivate_giftcode,
    record_redemption, get_redeemed_codes, update_players_table, update_player
)
from utils.fetch_gc_async import fetch_latest_codes_async
from utils.redemption import login_player, redeem_code
from utils.rclone import backup_db
import pandas as pd
import logging
from time import time
from datetime import datetime
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("request_logger")

# Secret key for sign generation
SALT = os.getenv("SALT")
DEFAULT_PLAYER = os.getenv("DEFAULT_PLAYER")

# Check if running in production (Render sets the RENDER environment variable)
if not bool(os.getenv("RENDER")):
    init_db()
    login_response, _ = login_player(DEFAULT_PLAYER, SALT)
    add_player(login_response['data'])

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
        login_response, request_data = login_player(player.player_id, SALT)
        add_player(login_response['data'])
        message = backup_db()
        print(message)
        return {"message": f"Player '{player.player_id}' added successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/players/update/")
async def update_player_profile(player: Player):
    try:
        login_response, request_data = await login_player(player.player_id, SALT)
        update_player(login_response['data'])
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
        new_codes.append(new_code)
    message = backup_db()
    print(message)
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
    for code in codes:
        redeemed_codes = get_redeemed_codes(request.player_id)
        if code in redeemed_codes:
            result = {"message": f"Code '{code}' already redeemed for player '{request.player_id}'."}
        else:
            result = redeem_code(request.player_id, SALT, code)
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
        
        players_df = pd.DataFrame(players)
        players_df = players_df[players_df['redeemed_all'] == 0]

        new_codes = await fetch_latest_codes_async("whiteoutsurvival", "gift code")
        for code in new_codes:
            add_giftcode(code)

        # Step 4: Redeem gift codes for each player
        all_codes = get_giftcodes()
        redemption_results = []

        for _, row in players_df.iterrows():
            player_id = row['fid']
            redeemed_codes = get_redeemed_codes(player_id)
            for code in all_codes:
                if code not in redeemed_codes:
                    try:
                        # Attempt to redeem the code
                        redeem_code(player_id, SALT, code)
                        record_redemption(player_id, code)
                        redemption_results.append({"player_id": player_id, "code": code, "status": "redeemed"})
                    except Exception as e:
                        redemption_results.append({"player_id": player_id, "code": code, "status": f"failed: {str(e)}"})
        message = backup_db()
        print(message)
        return {
            "message": "Main logic executed successfully.",
            "redemption_results": redemption_results,
            "giftcodes": all_codes,
            "players": get_players()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/update-players/")
async def update_players():
    """Updates the information of subscribed players."""
    try:
        players = get_players()
        if not players:
            return {"message": "No subscribed players found. Exiting."}

        players_df = pd.DataFrame(players, columns=[
            'fid', 'nickname', 'kid', 'stove_lv', 'stove_lv_content', 'avatar_image', 'total_recharge_amount'
        ]).head(10)

        # Perform concurrent API requests for player login
        tasks = [login_player(row['fid'], SALT) for _, row in players_df.iterrows()]
        updated_players_data = await asyncio.gather(*tasks)
        updated_players_data = [data for data in updated_players_data if data]

        if not updated_players_data:
            return {"message": "No updates found."}

        updated_players_df = pd.DataFrame(updated_players_data)
        updated_players_df = updated_players_df.astype(players_df.dtypes.to_dict())

        # Find differences
        comparison_df = players_df.merge(updated_players_df, on=[
            'fid', 'nickname', 'kid', 'stove_lv', 'stove_lv_content', 'avatar_image', 'total_recharge_amount'
        ], how='outer', indicator=True)

        differences_df = comparison_df[comparison_df['_merge'] == 'right_only'].drop(columns=['_merge'])

        if not differences_df.empty:
            update_players_table(differences_df)

        backup_db()

        return {"result": "Players updated successfully.", "differences": differences_df.to_dict(orient='records')}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating players: {str(e)}")