# Use the official Python base image
FROM python:3.12.0

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project code into the container
COPY . /app/

# Install cron
RUN apt-get update && apt-get install -y cron

# Add a cron job to run the Python backup script every hour
RUN echo "0 * * * * python3 /app/utils/rclone.py >> /var/log/cron.log 2>&1" > /etc/cron.d/backup_cron

# Give execution rights on the cron job
RUN chmod 0644 /etc/cron.d/backup_cron

# Apply the cron job
RUN crontab /etc/cron.d/backup_cron

# Create a log file for cron jobs
RUN touch /var/log/cron.log

# Expose the port FastAPI will use
EXPOSE 8000

# Start both cron and the FastAPI app
CMD ["sh", "-c", "cron && uvicorn main:app --host 0.0.0.0 --port 8000"]