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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set python and pip alternatives
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Install Poetry
RUN pip install poetry --break-system-packages

# Copy project files
COPY pyproject.toml .
COPY main.py .

# Create a README.md file if it doesn't exist to satisfy Poetry
RUN touch README.md

# Copy environment file template
COPY .env.example .env

# Configure Poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies without installing the project itself
RUN poetry install --no-interaction --no-ansi --no-root

# Create tmp directory for Breez SDK
RUN mkdir -p ./tmp

# Expose the port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]