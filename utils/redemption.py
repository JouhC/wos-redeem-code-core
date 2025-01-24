import requests
import hashlib
import time
import logging
from db.database import deactivate_giftcode

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redemption API endpoint
URL = "https://wos-giftcode-api.centurygame.com/api"
HTTP_HEADER = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept": "application/json",
}

def login_player(player_id, salt):
    """
    Redeem a gift code on Whiteout Survival.

    Args:
        player_id (str): The player's ID.
        salt (str): The secret salt used for signature generation.

    Returns:
        player details
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
            return None
        
        return login_response, request_data
    
    except requests.exceptions.RequestException as e:
        print(f"\nNetwork error occurred: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")


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
        login_response, request_data = login_player(player_id, salt)

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
            result = f"The gift code '{code}' doesn't exist!"
            success = False
        elif err_code == 40007:
            print("\nThe gift code is expired!")
            result = f"The gift code '{code}' is expired!"
            deactivate_giftcode(code)
            success = False
        elif err_code in (20000, 40008):  # Successfully claimed or already claimed
            print("\nSuccessful redemption!")
            result = f"Player {login_response['data']['nickname']}. Successful redemption for gift code '{code}'!"
            success = True
        elif err_code == 40005:
            print("\nAlready claimed redemption!")
            result = f"Player {login_response['data']['nickname']}. Already claimed redemption for gift code '{code}'!"
            success = True
        elif err_code == 40004:  # Timeout or retry
            print("\nUnsuccessful redemption. Please retry.")
            result = f"Player {login_response['data']['nickname']}. Unsuccessful redemption for '{code}'. Please retry."
            success = False
        else:
            print("\nRedemption failed with unexpected error.")
            print("Error response:", redeem_response)
            result = f"Player {login_response['data']['nickname']}. Redemption failed for '{code}' with unexpected error."
            success = False

    except requests.exceptions.RequestException as e:
        print(f"\nNetwork error occurred: {e}")
        result = f"Player {login_response['data']['nickname']}. Gift code '{code}'. Network error occurred: {e}"
        success = False
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        result = f"Player {login_response['data']['nickname']}. An unexpected error occurred: {e}"
        success = False
    finally:
        return {
            "message": result,
            "success": success
        }
