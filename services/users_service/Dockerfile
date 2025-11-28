FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

COPY ../../ .

RUN pip install --no-cache-dir -r requirements.txt

ENV FLASK_APP=services.users_service.app
ENV DB_PATH=/app/database/project.db

EXPOSE 5001

CMD ["python", "services/users_service/app.py"]
