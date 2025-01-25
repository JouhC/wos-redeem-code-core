import os
import pexpect
from utils.rclone import sync_db

RCLONE_CONFIG_PATH=os.getenv("RCLONE_CONFIG_PATH")
RCLONE_CONFIG_NAME=os.getenv("RCLONE_CONFIG_NAME")
RCLONE_TYPE=os.getenv("RCLONE_TYPE")
RCLONE_SCOPE=os.getenv("RCLONE_SCOPE")
RCLONE_ROOT_FOLDER_ID=os.getenv("RCLONE_ROOT_FOLDER_ID")
RCLONE_TOKEN=os.getenv("RCLONE_TOKEN")
RCLONE_TEAM_DRIVE=os.getenv("RCLONE_TEAM_DRIVE")
RCLONE_PASSWORD=os.getenv("RCLONE_PASSWORD")

def add_rclone_config_password():
    """Add a configuration password to rclone."""
    try:
        # Start the rclone config process
        child = pexpect.spawn("rclone config", encoding="utf-8")

        # Interact with the rclone config prompts
        child.expect("e/n/d/r/c/s/q>")
        child.sendline("s")  # Select 'Set configuration password'
        child.expect("a/q>")
        child.sendline("a")  # Select 'Add Password'
        child.expect("Enter NEW configuration password:")
        child.sendline("your_password_here")  # Replace with your desired password
        child.expect("Confirm NEW configuration password:")
        child.sendline("your_password_here")  # Confirm the password
        child.expect("c/u/q>")
        child.sendline("q")  # Quit to main menu
        child.expect("e/n/d/r/c/s/q>")
        child.sendline("q")  # Quit the config menu

        print("\nConfiguration password successfully added to rclone.")
    except pexpect.exceptions.EOF:
        print("\nFailed to add the configuration password to rclone.")
    except pexpect.exceptions.ExceptionPexpect as e:
        print(f"\nAn error occurred: {e}")

def main():
     # Validate required environment variables
    required_vars = [
        "RCLONE_CONFIG_PATH", "RCLONE_CONFIG_NAME", "RCLONE_TYPE",
        "RCLONE_SCOPE", "RCLONE_ROOT_FOLDER_ID", "RCLONE_TOKEN", "RCLONE_TEAM_DRIVE"
    ]
    
    missing_vars = [var for var in required_vars if globals().get(var) is None]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    

    rclone_conf = f"""\
        [{RCLONE_CONFIG_NAME}]
        type = {RCLONE_TYPE}
        scope = {RCLONE_SCOPE}
        root_folder_id = {RCLONE_ROOT_FOLDER_ID}
        token = {RCLONE_TOKEN}
        team_drive = {RCLONE_TEAM_DRIVE}
        """

    # Handle the rclone config path
    expanded_path = os.path.expanduser(RCLONE_CONFIG_PATH)
    dir_path = os.path.dirname(expanded_path)

    if not os.path.exists(expanded_path):
        # Create directory if it doesn't exist
        os.makedirs(dir_path, exist_ok=True)
        # Write the rclone configuration
        with open(expanded_path, "w") as f:
            f.write(rclone_conf)
        print("rclone config has been created.")
        add_rclone_config_password()
    else:
        print("rclone config is already configured.")

# Entry point
if __name__ == "__main__":
    main()
    message = sync_db()
    print(message)