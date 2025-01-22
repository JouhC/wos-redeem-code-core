from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from db.database import (
    init_db, add_player, get_players, add_giftcode, get_giftcodes,
    record_redemption, get_redeemed_codes
)
from utils.fetch_giftcodes import fetch_latest_codes
from utils.redemption import redeem_code

# Initialize the database
init_db()

# Initialize FastAPI app
app = FastAPI(
    title="Gift Code Redemption API",
    description="API for managing players, fetching gift codes, and redeeming them.",
    version="1.0.0"
)

# Models
class Player(BaseModel):
    player_id: str

class GiftCodeFetchRequest(BaseModel):
    subreddit_name: str
    keyword: str

class RedemptionRequest(BaseModel):
    player_id: str
    code: str

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
        add_player(player.player_id)
        return {"message": f"Player '{player.player_id}' added successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/players/")
async def list_players():
    players = get_players()
    return {"players": players}

# Gift code endpoints
@app.post("/giftcodes/fetch/")
async def fetch_giftcodes(request: GiftCodeFetchRequest):
    new_codes = fetch_latest_codes(request.subreddit_name, request.keyword)
    for code in new_codes:
        add_giftcode(code)
    return {"message": "Gift codes fetched and added to the database.", "codes": new_codes}

@app.get("/giftcodes/")
async def list_giftcodes():
    codes = get_giftcodes()
    return {"giftcodes": codes}

# Redemption endpoints
@app.post("/redeem/")
async def redeem_giftcode(request: RedemptionRequest):
    redeemed_codes = get_redeemed_codes(request.player_id)
    if request.code in redeemed_codes:
        return {"message": f"Code '{request.code}' already redeemed for player '{request.player_id}'."}

    redeem_code(request.player_id, "tB87#kPtkxqOS2", request.code)
    record_redemption(request.player_id, request.code)
    return {"message": f"Code '{request.code}' redeemed for player '{request.player_id}'."}

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
                        redeem_code(player_id, "tB87#kPtkxqOS2", code)
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