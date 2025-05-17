FROM ubuntu:24.04

WORKDIR /app

# Install system dependencies and Python 3.12
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    python3 \
    python3-venv \
    python3-pip \
    python3-full \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set python and pip alternatives
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Create a virtual environment
RUN python3 -m venv /app/venv

# Install Poetry in the virtual environment
RUN /app/venv/bin/pip install poetry

# Copy project files
COPY fly/pyproject.toml .
COPY fly/main.py .
COPY nodeless.py .
# Copy environment file template
COPY fly/.env.example .env

# Create a README.md file if it doesn't exist to satisfy Poetry
RUN touch README.md

# Install dependencies using the virtual environment's pip
RUN /app/venv/bin/poetry install --no-interaction --no-ansi --no-root

# Create tmp directory for Breez SDK
RUN mkdir -p ./tmp

# Expose the port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/venv/bin:$PATH"

# Run the application (now using the venv's Python)
CMD ["/app/venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]