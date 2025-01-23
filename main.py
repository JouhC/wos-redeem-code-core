from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from dotenv import load_dotenv
if not bool(os.getenv("RENDER")): load_dotenv()  # Load .env file in local development
from db.database import (
    init_db, add_player, get_players, add_giftcode, get_giftcodes, deactivate_giftcode,
    record_redemption, get_redeemed_codes
)
from utils.fetch_giftcodes import fetch_latest_codes
from utils.redemption import login_player, redeem_code
from utils.rclone import sync_db
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Secret key for sign generation
SALT = os.getenv("SALT")
RCLONE_CONFIG_PATH = os.getenv("RCLONE_CONFIG_PATH")
DEFAULT_PLAYER = os.getenv("DEFAULT_PLAYER")

# Check if running in production (Render sets the RENDER environment variable)
if not bool(os.getenv("RENDER")):
    init_db()
    login_response, _ = login_player(DEFAULT_PLAYER, SALT)
    add_player(login_response['data'])
else:
    sync_db()

    # Save RCLONE_CONFIG content to the default location
    config_path = os.path.expanduser(RCLONE_CONFIG_PATH)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        f.write(os.getenv("RCLONE_CONFIG", ""))

# Initialize FastAPI app
app = FastAPI(
    title="Gift Code Redemption API",
    description="API for managing players, fetching gift codes, and redeeming them.",
    version="1.0.0"
)

# Models
class Player(BaseModel):
    player_id: str

class GiftCodeSetStatusInactive(BaseModel):
    code: str

class RedemptionRequest(BaseModel):
    player_id: str

class MainLogicRequest(BaseModel):
    subreddit_name: str
    keyword: str

@app.get("/")
async def root():
    return {"message": "Welcome to the Gift Code Redemption API!"}

# Player endpoints
@app.post("/players/")
async def create_player(player: Player):
    try:
        login_response, request_data = login_player(player.player_id, SALT)
        add_player(login_response['data'])
        return {"message": f"Player '{player.player_id}' added successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/players/")
async def list_players():
    players = get_players()
    return {"players": players}

# Gift code endpoints
@app.get("/giftcodes/fetch/")
async def fetch_giftcodes():
    new_codes = fetch_latest_codes("whiteoutsurvival", "gift code")
    for code in new_codes:
        add_giftcode(code)
    return {"message": "Gift codes fetched and added to the database.", "codes": new_codes}

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
    return {"results": results}

@app.get("/redemptions/{player_id}/")
async def list_redeemed_codes(player_id: str):
    redeemed_codes = get_redeemed_codes(player_id)
    return {"player_id": player_id, "redeemed_codes": redeemed_codes}

@app.post("/automate-all/")
async def run_main_logic(request: MainLogicRequest):
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

        # Step 2: Fetch new gift codes
        new_codes = fetch_latest_codes(request.subreddit_name, request.keyword)
        if not new_codes:
            return {"message": "No new gift codes found. Exiting."}

        # Step 3: Merge new gift codes with the database
        for code in new_codes:
            add_giftcode(code)

        # Step 4: Redeem gift codes for each player
        all_codes = get_giftcodes()
        redemption_results = []

        for player_id in players:
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

        return {
            "message": "Main logic executed successfully.",
            "redemption_results": redemption_results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))