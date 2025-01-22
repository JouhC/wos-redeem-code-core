import requests
import hashlib
import time

# Redemption API endpoint
URL = "https://wos-giftcode-api.centurygame.com/api"
HTTP_HEADER = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
}

# Secret key for sign generation
SALT = "tB87#kPtkxqOS2"


def redeem_code(player_id, salt, code):
    """
    Redeem a gift code on Whiteout Survival.

    Args:
        player_id (str): The player's ID.
        salt (str): The secret salt used for signature generation.
        code (str): The gift code to redeem.

    Returns:
        None
    """
    try:
        # Create the login request data
        request_data = {
            "fid": player_id,
            "time": int(time.time() * 1000)  # Convert to milliseconds
        }

        # Generate login signature
        request_data["sign"] = hashlib.md5(
            f"fid={request_data['fid']}&time={request_data['time']}{salt}".encode("utf-8")
        ).hexdigest()

        # Send login request
        login_request = requests.post(
            URL + "/player", data=request_data, headers=HTTP_HEADER, timeout=30
        )
        login_request.raise_for_status()
        login_response = login_request.json()

        if login_response.get("msg") != "success":
            print(f"Login failed for player: {player_id}")
            return

        # Update request data with the gift code
        request_data["cdk"] = code
        request_data["sign"] = hashlib.md5(
            f"cdk={request_data['cdk']}&fid={request_data['fid']}&time={request_data['time']}{salt}".encode("utf-8")
        ).hexdigest()

        # Send gift code redemption request
        redeem_request = requests.post(
            URL + "/gift_code", data=request_data, headers=HTTP_HEADER, timeout=30
        )
        redeem_request.raise_for_status()
        redeem_response = redeem_request.json()

        # Handle response
        err_code = redeem_response.get("err_code")
        if err_code == 40014:
            print("\nThe gift code doesn't exist!")
        elif err_code == 40007:
            print("\nThe gift code is expired!")
        elif err_code in (20000, 40008):  # Successfully claimed or already claimed
            print("\nSuccessful redemption!")
        elif err_code == 40004:  # Timeout or retry
            print("\nUnsuccessful redemption. Please retry.")
        else:
            print("\nRedemption failed with unexpected error.")
            print("Error response:", redeem_response)

    except requests.exceptions.RequestException as e:
        print(f"\nNetwork error occurred: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")


def main():
    """Main function to test redemption."""
    # Replace these with actual values for testing
    player_id = "test_player_id"
    code = "test_gift_code"

    print(f"Redeeming code '{code}' for player '{player_id}'...")
    redeem_code(player_id, SALT, code)


if __name__ == "__main__":
    main()
