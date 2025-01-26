import subprocess
import os
from pathlib import Path
import pexpect

DB_FILE = Path(os.getenv("DB_FILE")).resolve()
RCLONE_PASSWORD=os.getenv("RCLONE_PASSWORD")

def backup_db():
    try:
        # Start the rclone config process
        child = pexpect.spawn(f"rclone copy {DB_FILE} remote-gdrive:backup", encoding="utf-8")

        # Interact with the rclone config prompts
        child.expect("password")
        child.sendline(RCLONE_PASSWORD)  # Select 'Set configuration password'
        
        print("Successfully backup the database to Google Drive.")
        return child.after   
    except pexpect.exceptions.EOF:
        print("Failed to backup the database to Google Drive.")
    except pexpect.exceptions.ExceptionPexpect as e:
        print(f"An error occurred: {e}")

def sync_db():
    try:
        # Start the rclone copy process
        child = pexpect.spawn("rclone copy remote-gdrive:backup ./db/", encoding="utf-8")

        # Interact with the rclone config prompts
        child.expect("password")
        child.sendline(RCLONE_PASSWORD)  # Select 'Set configuration password'

        print("Successfully copied the database from Google Drive.")
        return child.after   
    except pexpect.exceptions.EOF:
        print("Failed to copy the database from Google Drive.")
    except pexpect.exceptions.ExceptionPexpect as e:
        print(f"An error occurred: {e}")

def main():
    # Call the backup_db function and print its output
    print("Starting database backup...")
    output = backup_db()
    print(output)

if __name__ == "__main__":
    main()
