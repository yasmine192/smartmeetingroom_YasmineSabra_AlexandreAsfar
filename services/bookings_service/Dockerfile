FROM python:3.12-slim

WORKDIR /app

# Copy requirements from project root
COPY requirements.txt .

RUN pip install -r requirements.txt

# Copy ONLY this service's code
COPY services/bookings_service /app

CMD ["python", "app.py"]
