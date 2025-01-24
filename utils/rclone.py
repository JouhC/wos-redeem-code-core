import subprocess
import os
from pathlib import Path

DB_FILE = Path(os.getenv("DB_FILE")).resolve()

def backup_db():
    try:
        # Run `rclone` command to list Google Drive files
        result = subprocess.run(
            ["rclone", "copy", DB_FILE, "remote-gdrive:backup"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout
        else:
            return f"Error: {result.stderr}"
    except Exception as e:
        return str(e)

def sync_db():
    try:
        # Run `rclone` command to list Google Drive files
        result = subprocess.run(
            ["rclone", "copy", "remote-gdrive:backup", "./db/"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout
        else:
            return f"Error: {result.stderr}"
    except Exception as e:
        return str(e)

def main():
    # Call the backup_db function and print its output
    print("Starting database backup...")
    output = backup_db()
    print(output)

if __name__ == "__main__":
    main()
