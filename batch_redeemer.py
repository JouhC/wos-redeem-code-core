from db.database import (
    init_db, add_player, get_players, add_giftcode, get_giftcodes, deactivate_giftcode,
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
import logging
from collections import defaultdict
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

player_api = None
solve_captcha = CaptchaSolver()

BATCH_DELAY = 1  # 1 second delay
MAX_WORKERS = 3  # adjust based on your rate limit
SALT = os.getenv("SALT")
CACHE_DIR = "./cache"
error_codes = json.load(open("error_codes.json", "r"))


def create_cache(cache_type, data):
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

    if cache_type == "expired_giftcode":
        cache_file = os.path.join(CACHE_DIR, "expired_giftcode.json")
    elif cache_type == "redeemed_giftcode":
        cache_file = os.path.join(CACHE_DIR, "redeemed_giftcode.json")
    elif cache_type == "success_captcha":
        cache_file = os.path.join(CACHE_DIR, "success_captcha.json")
    elif cache_type == "players":
        cache_file = os.path.join(CACHE_DIR, "players.json")
        
    # Create directory if it doesn't exist
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Load existing data or initialize as empty list
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
    
    # Append new data
    existing_data.append(data)

    # Save back to file
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
                        update_player(item)
            os.remove(file_path)

def clear_cache():
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)

async def process(fid, code, update_progress, progress_multiplier):
    login_response = await player_api.login_player(fid, SALT)
    create_cache("players", login_response['token'])

    if not login_response:
        print(f"Login failed for {fid}. Skipping...")
        return None
    
    retries = 0
    result = None

    while retries < 4:
        retries += 1
        captcha_data = await player_api.get_captcha(fid, SALT)
        if captcha_data is None:
            logger.info(f"Captcha data is None for {fid}. Retrying...")
            continue
        captcha_solution, captcha_id = solve_captcha.solve(captcha_data)
        result = await player_api.redeem_code(fid, code, captcha_solution, SALT)
        
        if result:
            msg = result.get("msg")
            if msg == "Sign Error":
                logger.info(f"Sign Error for {fid}: {code}")
                continue
            err_code = result.get("err_code")
            if err_code == 0:
                logger.info(f"Code redeemed successfully for {fid}: {code}")
                create_cache("redeemed_giftcode", {"fid": fid, "code": code})
                create_cache("success_captcha", {"captcha_id": captcha_id})
                break
            elif str(err_code) in error_codes:
                logger.info(error_codes[str(err_code)]['message'])
                if error_codes[str(err_code)]['captcha_error'] == True:
                    await asyncio.sleep(2)
                    continue
                elif error_codes[str(err_code)]['success'] == True:
                    create_cache("redeemed_giftcode", {"fid": fid, "code": code})
                    create_cache("success_captcha", {"captcha_id": captcha_id})
                    break
                elif error_codes[str(err_code)]['expired'] == True:
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

    update_progress(progress_multiplier)
    logger.info(f"[{fid} | {code}] -> {result}")
    await asyncio.sleep(BATCH_DELAY)

async def worker(queue, update_progress, progress_multiplier):
    try:
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break

            fid, code = item
            try:
                await process(fid, code, update_progress, progress_multiplier)
            finally:
                queue.task_done()
    except asyncio.CancelledError:
        print("Worker was cancelled.")
        raise

async def _main_logic(task_results: dict, task_id: str, salt: str, default_player: str = None, n: int = None):
    def update_progress(progress: int):
        task_results[task_id]["progress"] += progress

    global player_api
    if player_api is not None:
        await player_api.close_session()
    player_api = PlayerAPI()

    if os.path.exists(CACHE_DIR):
        process_cache()
        backup_db()
        clear_cache()

    task_results[task_id] = {"status": "Processing", "progress": 0}
    players = get_players()
    if not players:
        task_results[task_id] = {"status": "Completed", "progress": 100, "message": "No subscribed players found. Exiting."}
        return []
    update_progress(10)

    new_codes = await fetch_latest_codes_async("whiteoutsurvival", "gift code")
    new_codes_true = [code for code in (add_giftcode(c) for c in new_codes) if code is not None]
    all_codes = get_giftcodes()
    update_progress(10)

    if default_player:
        unredeemed_df = pd.DataFrame({"fid": [default_player] * len(all_codes), "code": all_codes})
    else:
        unredeemed_data = get_unredeemed_code_player_list()
        if not unredeemed_data:
            task_results[task_id] = {"status": "Completed", "progress": 100, "message": "No unredeemed codes found. Exiting.", "giftcodes": all_codes, "players": players, "new_codes": new_codes_true}
            return []
        unredeemed_df = pd.DataFrame(unredeemed_data)

    if n:
        unredeemed_df = unredeemed_df.sample(n=n)
    unredeemed_df = unredeemed_df.sample(n=min(20, len(unredeemed_df)))  # Limit to 20 tasks
    if unredeemed_df.empty:
        task_results[task_id] = {"status": "Completed", "progress": 100, "message": "No unredeemed codes to process.", "giftcodes": all_codes, "players": players, "new_codes": new_codes_true}
        return []

    queue = asyncio.Queue()
    progress_multiplier = int(50 / len(unredeemed_df))

    workers = [asyncio.create_task(worker(queue, update_progress, progress_multiplier)) for _ in range(MAX_WORKERS)]
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

    task_results[task_id] = {"status": "Completed", "progress": 100, "message": "Main logic executed successfully. Limiting to 20 tasks.", "giftcodes": get_giftcodes(), "players": get_players(), "new_codes": new_codes_true}
    return workers

async def main(task_results: dict, task_id: str, salt: str, default_player: str = None, n: int = None, timeout=300):
    global player_api
    workers = []
    try:
        async def _wrapped_logic():
            nonlocal workers
            workers = await _main_logic(task_results, task_id, salt, default_player, n)

        await asyncio.wait_for(_wrapped_logic(), timeout=timeout)

    except asyncio.TimeoutError:
        task_results[task_id] = {"status": "Timeout", "progress": 100, "error": f"Timeout: Task exceeded {timeout} seconds.", "giftcodes": get_giftcodes(), "players": get_players()}
        print("⏰ Timeout reached. Cancelling workers...")
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    finally:
        if player_api:
            await player_api.close_session()
        if os.path.exists(CACHE_DIR):
            process_cache()
            backup_db()
            clear_cache()