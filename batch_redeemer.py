from db.database import (
    init_db, add_player, get_players, add_giftcode, get_giftcodes, get_giftcodes_unchecked, deactivate_giftcode,
    record_redemption, get_redeemed_codes, update_players_table, update_player, get_unredeemed_code_player_list,
    record_captcha, update_captcha_feedback
)
from utils.fetch_gc_async import fetch_latest_codes_async
from utils.rclone import backup_db
from utils.wos_api import PlayerAPI
import asyncio
import logging
import pandas as pd
from utils.captcha_solver import CaptchaSolver
import os
import json
from collections import defaultdict
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

player_api = None
solve_captcha = CaptchaSolver()

BATCH_DELAY = 1           # 1 second delay
MAX_WORKERS = 3           # adjust based on your rate limit
SALT = os.getenv("SALT")
CACHE_DIR = "./cache"
error_codes = json.load(open("error_codes.json", "r"))

def make_progress_updater(task_results: dict, task_id: str):
    """Returns a function inc(delta) that increments progress safely."""
    def inc(delta: int):
        cur = task_results.get(task_id, {}).get("progress", 0)
        task_results[task_id]["progress"] = max(0, min(100, int(cur) + int(delta)))
    return inc

def create_cache(cache_type, data):
    os.makedirs(CACHE_DIR, exist_ok=True)

    if cache_type == "expired_giftcode":
        cache_file = os.path.join(CACHE_DIR, "expired_giftcode.json")
    elif cache_type == "redeemed_giftcode":
        cache_file = os.path.join(CACHE_DIR, "redeemed_giftcode.json")
    elif cache_type == "success_captcha":
        cache_file = os.path.join(CACHE_DIR, "success_captcha.json")
    elif cache_type == "players":
        cache_file = os.path.join(CACHE_DIR, "players.json")
    else:
        raise ValueError(f"Unknown cache_type: {cache_type}")

    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            try:
                existing_data = json.load(f)
            except json.JSONDecodeError:
                existing_data = []
    else:
        existing_data = []

    if data in existing_data:
        logger.info(f"Data already exists in {cache_file}")
        return

    existing_data.append(data)
    with open(cache_file, "w") as f:
        json.dump(existing_data, f, indent=2)

def process_cache():
    cache_files = ["expired_giftcode.json", "redeemed_giftcode.json", "success_captcha.json", "players.json"]
    for cache_file in cache_files:
        file_path = os.path.join(CACHE_DIR, cache_file)
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                data = json.load(f)
                for item in data:
                    if cache_file == "expired_giftcode.json":
                        deactivate_giftcode(item['code'])
                    elif cache_file == "redeemed_giftcode.json":
                        record_redemption(item['fid'], item['code'])
                    elif cache_file == "success_captcha.json":
                        update_captcha_feedback(item['captcha_id'])
                    elif cache_file == "players.json":
                        # expect item like {"fid": "...", "token": "..."} or similar
                        update_player(item)
            os.remove(file_path)

def clear_cache():
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)

async def process(fid, code, progress_cb, progress_multiplier):
    login_response = await player_api.login_player(fid, SALT)

    if not login_response:
        logger.info(f"Login failed for {fid}. Skipping...")
        return None

    # stash player token for later persistence
    if isinstance(login_response, dict) and 'token' in login_response:
        create_cache("players", login_response['token'])

    retries = 0
    result = None

    while retries < 4:
        retries += 1
        captcha_data = await player_api.get_captcha(fid, SALT)
        if captcha_data is None:
            logger.info(f"Captcha data is None for {fid}. Retrying...")
            await asyncio.sleep(2)
            continue

        captcha_solution, captcha_id = solve_captcha.solve(captcha_data)
        result = await player_api.redeem_code(fid, code, captcha_solution, SALT)

        if result:
            msg = result.get("msg")
            if msg == "Sign Error":
                logger.info(f"Sign Error for {fid}: {code}")
                await asyncio.sleep(2)
                continue

            err_code = result.get("err_code")
            if err_code == 0:
                logger.info(f"Code redeemed successfully for {fid}: {code}")
                create_cache("redeemed_giftcode", {"fid": fid, "code": code})
                create_cache("success_captcha", {"captcha_id": captcha_id})
                break

            elif str(err_code) in error_codes:
                ec = error_codes[str(err_code)]
                logger.info(ec.get('message', f"err_code {err_code}"))
                if ec.get('captcha_error'):
                    await asyncio.sleep(2)
                    continue
                elif ec.get('success'):
                    create_cache("redeemed_giftcode", {"fid": fid, "code": code})
                    create_cache("success_captcha", {"captcha_id": captcha_id})
                    break
                elif ec.get('expired'):
                    create_cache("expired_giftcode", {"code": code})
                    create_cache("success_captcha", {"captcha_id": captcha_id})
                    break
                else:
                    await asyncio.sleep(2)
                    continue
            else:
                logger.info(error_codes['default']['message'])
                logger.info(result)
        else:
            logger.info("None Response!")
        await asyncio.sleep(10)

    # progress for this (fid, code) task
    progress_cb(progress_multiplier)
    logger.info(f"[{fid} | {code}] -> {result}")
    await asyncio.sleep(BATCH_DELAY)

async def worker(queue, progress_cb, progress_multiplier):
    try:
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            fid, code = item
            try:
                await process(fid, code, progress_cb, progress_multiplier)
            finally:
                queue.task_done()
    except asyncio.CancelledError:
        logger.info("Worker was cancelled.")
        raise

async def process_unredeemed_df(unredeemed_df: pd.DataFrame, progress_cb, progress_share=50):
    """Run the queue/worker pipeline for the given DataFrame (cols: fid, code)."""
    if unredeemed_df is None or unredeemed_df.empty:
        return []

    queue = asyncio.Queue()
    progress_multiplier = max(1, int(progress_share / max(1, len(unredeemed_df))))

    workers = [asyncio.create_task(worker(queue, progress_cb, progress_multiplier)) for _ in range(MAX_WORKERS)]

    # Group by code to redeem per code across fids
    code_to_fids = defaultdict(list)
    for _, row in unredeemed_df.iterrows():
        code_to_fids[row["code"]].append(row["fid"])

    try:
        for code, fids in code_to_fids.items():
            for fid in fids:
                queue.put_nowait((fid, code))
        await queue.join()
    finally:
        for _ in range(MAX_WORKERS):
            queue.put_nowait(None)
        await asyncio.gather(*workers, return_exceptions=True)
        return workers

async def _run_default_player(progress_cb, default_player: str = None, n: int = None):
    """Run the default player through the queue/worker pipeline."""
    if not default_player:
        logger.info("No default player provided. Skipping default player run.")
        return []

    codes = get_giftcodes_unchecked() or []
    if not codes:
        logger.info("No unchecked giftcodes for default player.")
        return []
    logger.info(f"here the codes: {codes}")
    
    unredeemed_df = pd.DataFrame({"fid": [default_player] * len(codes), "code": codes})

    # Smaller share if also running the full main logic
    progress_share = 10 if n else 90
    return await process_unredeemed_df(unredeemed_df, progress_cb, progress_share=progress_share)

async def _main_logic(task_results: dict, task_id: str, progress_cb, salt: str, default_player: str = None, n: int = None, new_codes_true: list = None):
    """Main logic for processing unredeemed codes."""
    global player_api
    # ensure single session
    if player_api is not None:
        await player_api.close_session()
    player_api = PlayerAPI()

    # flush cache from previous run (if any)
    if os.path.exists(CACHE_DIR):
        process_cache()
        backup_db()
        clear_cache()

    players = get_players()
    if not players:
        task_results[task_id] = {
            "status": "Completed", "progress": 100,
            "message": "No subscribed players found. Exiting."
        }
        return []
    
    all_codes = get_giftcodes()

    # Always compute unredeemed list; sample only if n is provided
    unredeemed_data = get_unredeemed_code_player_list()
    if not unredeemed_data:
        task_results[task_id] = {
            "status": "Completed", "progress": 100,
            "message": "No unredeemed codes found. Exiting.",
            "giftcodes": all_codes, "players": players, "new_codes": new_codes_true
        }
        return []

    unredeemed_df = pd.DataFrame(unredeemed_data)  # expect cols: fid, code
    if n:
        unredeemed_df = unredeemed_df.sample(n=min(n, len(unredeemed_df)), random_state=42)

    if unredeemed_df.empty:
        task_results[task_id] = {
            "status": "Completed", "progress": 100,
            "message": "No unredeemed codes to process.",
            "giftcodes": all_codes, "players": players, "new_codes": new_codes_true
        }
        return []

    workers = await process_unredeemed_df(unredeemed_df, progress_cb, progress_share= 100 - task_results.get(task_id, {}).get("progress", 0))
    return workers

async def main(task_results: dict, task_id: str, salt: str, default_player: str = None, n: int = None, timeout=300):
    global player_api
    # single session lifecycle inside main
    if player_api is not None:
        await player_api.close_session()
    player_api = PlayerAPI()

    workers_all = []
    
    progress_cb = make_progress_updater(task_results, task_id)
    task_results[task_id] = {"status": "Processing", "progress": 0}

    try:
        new_codes = await fetch_latest_codes_async("whiteoutsurvival", "gift code")
        new_codes_true = [code for code in (add_giftcode(c) for c in new_codes) if code is not None]
        progress_cb(10)

        w1_starttime = asyncio.get_event_loop().time()
        w1 = await asyncio.wait_for(_run_default_player(progress_cb, default_player, n), timeout=timeout)
        w1_elapsed_time = asyncio.get_event_loop().time() - w1_starttime

        if not w1:  
            logger.info("Default player skipped.")
        if n:
            w2 = await asyncio.wait_for(_main_logic(task_results, task_id, progress_cb, salt, default_player, n, new_codes_true), timeout=timeout-w1_elapsed_time)

        if task_results[task_id].get("status") == "Processing":
            task_results[task_id] = {
                "status": "Completed", "progress": 100,
                "message": "Main logic executed successfully.",
                "giftcodes": get_giftcodes(), "players": get_players(), "new_codes": new_codes_true
            }

    except asyncio.TimeoutError:
        task_results[task_id] = {
            "status": "Timeout", "progress": 100,
            "error": f"Timeout: Task exceeded {timeout} seconds.",
            "giftcodes": get_giftcodes(), "players": get_players()
        }
        logger.warning("⏰ Timeout reached. Cancelling workers...")
        for w in workers_all:
            try:
                w.cancel()
            except Exception:
                pass
        await asyncio.gather(*workers_all, return_exceptions=True)

    finally:
        if player_api:
            await player_api.close_session()
            player_api = None
        if os.path.exists(CACHE_DIR):
            process_cache()
            backup_db()
            clear_cache()
