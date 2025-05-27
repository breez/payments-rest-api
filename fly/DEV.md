### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/breez/nodeless-payments.git
   cd nodeless-payments/fly
   ```

2. Install dependencies with Poetry:
   ```bash
   poetry install
   ```

3. Create a `.env` file with your configuration:
   ```bash
   cp .env.example .env
   # Edit .env file with your actual credentials
   ```

4. Run the application:
   ```bash
   poetry run uvicorn main:app --reload
   ```

5. Visit `http://localhost:8000/docs` in your browser to see the API documentation

### Docker

1. Build the Docker image:
   ```bash
   docker build -t payments-rest-api .
   ```

2. Run the container:
   ```bash
   docker run -p 8000:8000 --env-file .env payments-rest-api
   ```
