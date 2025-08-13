# Use the official Python base image
FROM python:3.12.0

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first (leveraging Docker layer caching)
#COPY requirements.txt /app/
#RUN pip install --no-cache-dir -r requirements.txt

# Install uv
RUN pip install uv

# Copy the entire project code into the container
COPY . /app

# Install dependencies with uv
RUN uv sync --frozen --no-dev

# Install SQLite3 and rclone
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 curl && \
    curl https://rclone.org/install.sh | bash && \
    rm -rf /var/lib/apt/lists/*

# Expose the port FastAPI will use
EXPOSE 8000

# Install a process manager (supervisord) to run uvicorn
RUN uv add supervisor
COPY supervisord.conf /etc/supervisord.conf

# Start supervisord
CMD ["uv", "run", "supervisord", "-c", "/etc/supervisord.conf"]