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

def backup_db():
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = subprocess.run(
                ["rclone", "copy", DB_FILE, f"{RCLONE_CONFIG_NAME}:backup"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True  # Raise CalledProcessError on non-zero exit
            )
            print("✅ Successfully backed up the database to Google Drive.")
            return result
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to backup the database (exit code {e.returncode}):\n{e.stderr.strip()}")
        except Exception as e:
            print(f"❌ Unexpected error during backup: {e}")
        
        if attempt < MAX_RETRIES:
            print(f"🔁 Retry {attempt}/{MAX_RETRIES} - Waiting {RETRY_DELAY} seconds before retrying...\n")
            time.sleep(RETRY_DELAY)
        else:
            print("❌ All retry attempts failed. Please check rclone manually.")

def sync_db():
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = subprocess.run(
                ["rclone", "copy", f"{RCLONE_CONFIG_NAME}:backup", "./db/"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True  # Raises CalledProcessError if exit code != 0
            )
            print("✅ Successfully synced database!")
            return result  # Contains stdout, stderr, returncode, etc.
        except subprocess.CalledProcessError as e:
            print(f"❌ Sync DB - rclone failed (exit code {e.returncode}):\n{e.stderr.strip()}")
        except Exception as e:
            print(f"❌ Sync DB - Unexpected error: {e}")

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
