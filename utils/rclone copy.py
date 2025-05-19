import os
import subprocess
from pathlib import Path
import pexpect
import time

DB_FILE = Path(os.getenv("DB_FILE")).resolve()
#RCLONE_PASSWORD=os.getenv("RCLONE_PASSWORD")
RCLONE_CONFIG_NAME=os.getenv("RCLONE_CONFIG_NAME")
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

def backup_db_old():
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Start the rclone config process
            child = pexpect.spawn(f"rclone copy {DB_FILE} {RCLONE_CONFIG_NAME}:backup", encoding="utf-8")

            # Interact with the rclone config prompts
            #child.expect("Enter configuration password:")
            #child.sendline(RCLONE_PASSWORD)  # Select 'Set configuration password'
            
            child.expect(pexpect.EOF)

            # Print the output
            #output = child.before
            print("Successfully backed up the database to Google Drive.")
            return child
        except pexpect.exceptions.EOF:
            print("Failed to backup the database to Google Drive.")
        except pexpect.exceptions.ExceptionPexpect as e:
            print(f"An error occurred: {e}")
        
        if attempt < MAX_RETRIES:
            print(f"🔁 Sync DB - Retrying in {RETRY_DELAY} seconds...\n")
            time.sleep(RETRY_DELAY)
        else:
            print("❌ Sync DB - All retry attempts failed. Please check rclone manually.")

def sync_db_old():
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Start the rclone copy process
            child = pexpect.spawn(f"rclone copy {RCLONE_CONFIG_NAME}:backup ./db/", encoding="utf-8")

            # Interact with the rclone config prompts
            #child.expect("Enter configuration password:")
            #child.sendline(RCLONE_PASSWORD)  # Select 'Set configuration password'

            child.expect(pexpect.EOF)

            # Print the output
            #output = child.before
            print("Successfully synced database!")
            return child
        except pexpect.exceptions.TIMEOUT:
            print("⚠️ Sync DB - Timeout occurred while interacting with rclone.")
        except pexpect.exceptions.EOF:
            print("Sync DB - Failed to copy the database from Google Drive.")
        except pexpect.exceptions.ExceptionPexpect as e:
            print(f"Sync DB - An error occurred: {e}")
        
        if attempt < MAX_RETRIES:
            print(f"🔁 Sync DB - Retrying in {RETRY_DELAY} seconds...\n")
            time.sleep(RETRY_DELAY)
        else:
            print("❌ Sync DB - All retry attempts failed. Please check rclone manually.")

def main():
    # Call the backup_db function and print its output
    print("Starting database backup...")
    output = backup_db()
    print(output)

if __name__ == "__main__":
    main()
