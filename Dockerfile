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

# Expose the port FastAPI will use
EXPOSE 8000

# Start FastAPI
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
