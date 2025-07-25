FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt


COPY agent.py .

EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV HOST="0.0.0.0" 
CMD ["uvicorn", "agent:app", "--host", "0.0.0.0", "--port", "8080"]