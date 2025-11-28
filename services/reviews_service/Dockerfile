FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

COPY ../../ .

RUN pip install --no-cache-dir -r requirements.txt

ENV FLASK_APP=services.reviews_service.app
ENV DB_PATH=/data/project.db

EXPOSE 5004

CMD ["python", "services/reviews_service/app.py"]
