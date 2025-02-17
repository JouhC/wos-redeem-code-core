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
import uuid
import asyncio

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
        await player_api.close_session()

    asyncio.run(init_default_player())

# Initialize FastAPI app
app = FastAPI(
    title="Gift Code Redemption API",
    description="API for managing players, fetching gift codes, and redeeming them.",
    version="1.0.0"
)

# Task tracking dictionary
task_results = {}

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
        logger.info(message)
        return {"message": f"Player '{player.player_id}' added successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await player_api.close_session()

@app.post("/players/update/")
async def update_player_profile(player: Player):
    try:
        player_api = PlayerAPI()
        login_response = await player_api.login_player(player.player_id, SALT)
        update_player(login_response['token'])
        message = backup_db()
        logger.info(message)
        return {"message": f"Player '{player.player_id}' info updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await player_api.close_session()

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
    logger.info({"message": "Gift codes fetched and added to the database.", "new_codes": new_codes})
    return {"message": "Gift codes fetched and added to the database.", "new_codes": new_codes}

@app.get("/giftcodes/")
async def list_giftcodes():
    codes = get_giftcodes()
    return {"giftcodes": codes}

@app.post("/giftcodes/deactivate/")
async def set_inactive(code: GiftCodeSetStatusInactive):
    try:
        message = deactivate_giftcode(code.code)
        backup_db()
        return {"message": f"{message}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@app.post("/giftcodes/expired-check/")
async def expired_codes():
    try:
        player_api = PlayerAPI()
        login_response = await player_api.login_player(DEFAULT_PLAYER, SALT)
        expired = []
        if login_response:
            for code in get_giftcodes():
                result = await player_api.redeem_code(DEFAULT_PLAYER, code, SALT)
                if result['expired']:
                    expired.append(code)
                    deactivate_giftcode(code)
        backup_db()
        return {"message": "Gift codes are updated with expired status.", "expired_codes": expired, "active_codes": get_giftcodes()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await player_api.close_session()

# Redemption endpoints
@app.post("/redeem/")
async def redeem_giftcode(request: RedemptionRequest):
    try:
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
        logger.info(message)
        return {"results": results}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await player_api.close_session()

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
            logger.info("No players updated.")
        else:
            update_players_table(results)
            logger.info(f"{len(results)} players updated.")

        backup_db()
        return get_players()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def run_automate_all(task_id: str, salt: str):
    try:

        def update_progress(progress: int):
            task_results[task_id]["progress"] += progress

        # Step 1: Fetch subscribed players
        task_results[task_id] = {"status": "Processing", "progress": 0}
        players = get_players()
        if not players:
            task_results[task_id] = {"status": "Completed", "progress": 100, "message": "No subscribed players found. Exiting."}
            return
        update_progress(10)

        # Step 2: Fetch new gift codes
        new_codes = await fetch_latest_codes_async("whiteoutsurvival", "gift code")
        for code in new_codes:
            add_giftcode(code)
        all_codes = get_giftcodes()
        update_progress(10)

        # Step 3: Get unredeemed codes
        unredeemed_data = get_unredeemed_code_player_list()
        if not unredeemed_data:
            task_results[task_id] = {
                "status": "Completed",
                "progress": 100,
                "message": "No unredeemed codes found. Exiting.",
                "giftcodes": all_codes,
                "players": players
            }
            return
        update_progress(10)

        # Step 4: Convert to DataFrame and process redemptions
        unredeemed_df = pd.DataFrame(unredeemed_data)
        player_tokens, redeem_results = await process_redemption_batches(unredeemed_df, salt, update_progress)

        for player in player_tokens:
            update_player(player)
        update_progress(50)

        expired = []
        for result in redeem_results:
            if result['success']:
                record_redemption(result['player_id'], result['code'])
            elif result['expired']:
                if result['code'] not in expired:
                    deactivate_giftcode(result['code'])
                    expired.append(result['code'])
        update_progress(10)

        # Step 5: Backup database
        backup_db()

        # Store task result
        task_results[task_id] = {
            "status": "Completed",
            "progress": 100,
            "message": "Main logic executed successfully.",
            "giftcodes": all_codes,
            "players": get_players()
        }
    except Exception as e:
        task_results[task_id] = {"status": "Failed", "progress": 100, "error": str(e)}

@app.post("/automate-all/")
async def automate_all():
    """
    Starts the automate-all process and returns a task ID.
    The client should poll `/task_status/{task_id}` to get updates.
    """
    task_id = str(uuid.uuid4())
    task_results[task_id] = {"status": "Processing", "progress": 0}

    # Run automation logic asynchronously in the background
    asyncio.create_task(run_automate_all(task_id, salt=os.getenv("SALT")))

    return {"task_id": task_id, "status": "Processing", "progress": 0}

@app.get("/task_status/{task_id}")
async def get_task_status(task_id: str):
    """
    Checks the status of an asynchronous task, including progress.
    """
    return task_results.get(task_id, {"status": "Not Found", "progress": 0})

@app.get("/task_status/check_inprogress/")
async def get_task_inprogress():
    """
    Checks if there is a task in progress.
    """
    if task_results:
        for _, task_id in enumerate(task_results):
            if task_results[task_id]['status'] == 'Processing':
                return task_id

    return None
