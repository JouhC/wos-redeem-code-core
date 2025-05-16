import os
if not bool(os.getenv("RENDER")): 
    from dotenv import load_dotenv
    load_dotenv()  # Load .env file in local development
from db.database import (
    init_db, add_player, remove_player, get_players, add_giftcode, get_giftcodes, deactivate_giftcode,
    record_redemption, get_redeemed_codes, update_players_table, update_player
)
import batch_redeemer
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from time import time
from utils.fetch_gc_async import fetch_latest_codes_async
from utils.rclone import backup_db
from utils.wos_api import PlayerAPI
import asyncio
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("request_logger")

# Secret key for sign generation
SALT = os.getenv("SALT")
DEFAULT_PLAYER = os.getenv("DEFAULT_PLAYER")
is_ready = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    global is_ready
    # Check if running in production (Render sets the RENDER environment variable)
    if not bool(os.getenv("RENDER")):
        async def init_default_player():
            init_db()
            player_api = PlayerAPI()
            login_response = await player_api.login_player(DEFAULT_PLAYER, SALT)
            add_player(login_response['token'])
            await player_api.close_session()
        
        await init_default_player()  

    is_ready = True  # App is ready to serve requests
    yield

# Initialize FastAPI app
app = FastAPI(
    title="Gift Code Redemption API",
    description="API for managing players, fetching gift codes, and redeeming them.",
    version="2.2.0",
    lifespan=lifespan
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

class AutomationRequest(BaseModel):
    n: str = "all"

@app.get("/")
async def root():
    return {"message": "Welcome to the Gift Code Redemption API!"}

@app.get("/healthz")
async def healthz():
    return {"ready": is_ready}

@app.get("/health")
async def health():
    return {"status": "ok"}

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
        if login_response is None:
            raise HTTPException(status_code=400, detail=f"Adding Player '{player.player_id}' was unsuccessful.")
        
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
        logger.info(f"Player {player.player_id}'s token: {login_response['token']}")
        update_player(login_response['token'])
        message = backup_db()
        logger.info(message)
        return {"message": f"Player '{player.player_id}' info updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await player_api.close_session()

@app.post("/players/remove/")
async def remove_player_db(player: Player):
    try:
        response = remove_player(player.player_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        message = backup_db()
        logger.info(message)
        return {"response": response}

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
    task_id = str(uuid.uuid4())
    task_results[task_id] = {"status": "Processing", "progress": 0}

    # Run automation logic asynchronously in the background
    asyncio.create_task(batch_redeemer.main(task_results, task_id, salt=os.getenv("SALT"), default_player=DEFAULT_PLAYER))

    return {"task_id": task_id, "status": "Processing", "progress": 0}

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

@app.post("/automate-all/")
async def automate_all(request: AutomationRequest):
    """
    Starts the automate-all process and returns a task ID.
    The client should poll `/task_status/{task_id}` to get updates.
    """
    task_id = str(uuid.uuid4())
    task_results[task_id] = {"status": "Processing", "progress": 0}

    if request.n == "all":
        n = None
    else:
        n = int(request.n)

    # Run automation logic asynchronously in the background
    asyncio.create_task(batch_redeemer.main(task_results, task_id, salt=os.getenv("SALT"), default_player=None, n=n))

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

@app.post("/task_status/reset")
def reset():
    task_results.clear()
    return {"status": "cleared"}
