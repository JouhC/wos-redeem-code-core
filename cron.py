from utils.rclone import backup_db
from db.database import (
    init_db, add_player, get_players, add_giftcode, get_giftcodes, deactivate_giftcode,
    record_redemption, get_redeemed_codes
)
from utils.fetch_giftcodes import fetch_latest_codes
from utils.redemption import login_player, redeem_code
import os
import pandas as pd

SALT = os.getenv("SALT")

def automate_all():
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

        new_codes = fetch_latest_codes("whiteoutsurvival", "gift code")
        for code in new_codes:
            add_giftcode(code)

        # Step 3: Merge new gift codes with the database
        for code in new_codes:
            add_giftcode(code)

        # Step 4: Redeem gift codes for each player
        all_codes = get_giftcodes()
        redemption_results = []

        for row in players_df.iterrows():
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

        return {
            "message": "Main logic executed successfully.",
            "redemption_results": redemption_results
        }
    except Exception as e:
        raise e

def main():
    # Call the backup_db function and print its output
    print("Starting database backup...")
    output = backup_db()
    print(output)

    automate_output = automate_all()
    print(automate_output)

if __name__ == "__main__":
    main()