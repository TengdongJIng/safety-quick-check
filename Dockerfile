FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT 80
ENV PYTHONUNBUFFERED=1

EXPOSE 80

CMD ["gunicorn", "backend.app:app", "--bind", "0.0.0.0:80", "--workers", "2", "--timeout", "60"]
