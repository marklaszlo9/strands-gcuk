FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt


COPY api.py .
COPY model_tooluse.txt . 
COPY templates ./templates


EXPOSE 5001

ENV PYTHONUNBUFFERED=1
ENV PORT=5001
ENV HOST="0.0.0.0" 
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "5001"]
