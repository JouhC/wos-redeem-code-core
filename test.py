from utils.fetch_giftcodes import fetch_latest_codes
from utils.redemption import redeem_code
from db.database import (
    init_db, add_player, get_players, add_giftcode, get_giftcodes, 
    record_redemption, get_redeemed_codes
)

# Initialize the database
init_db()

def main():
    # Step 1: Fetch subscribed players
    players = get_players()
    print(f"Subscribed players: {players}")

    # Step 2: Fetch new gift codes
    subreddit_name = "whiteoutsurvival"
    keyword = "gift code"  
    new_codes = fetch_latest_codes(subreddit_name, keyword)
    print(f"New gift codes fetched: {new_codes}")

    # Step 3: Merge new gift codes with the database
    for code in new_codes:
        add_giftcode(code)

    # Step 4: Check and redeem gift codes for each player
    all_codes = get_giftcodes()
    for player_id in players:
        redeemed_codes = get_redeemed_codes(player_id)
        for code in all_codes:
            if code not in redeemed_codes:
                print(f"Redeeming code '{code}' for player '{player_id}'...")
                redeem_code(player_id, "tB87#kPtkxqOS2", code)
                record_redemption(player_id, code)

    # Update complete
    print("Daily update completed.")

if __name__ == "__main__":
    main()
