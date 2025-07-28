FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY custom_agent.py .
COPY api.py .
COPY agent_cli.py .
COPY templates ./templates
COPY static-frontend ./static-frontend

# Create necessary directories
RUN mkdir -p /app/logs

# Expose port
EXPOSE 8080

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV HOST="0.0.0.0"

# AgentCore Memory ID should be provided at runtime

# ENV AGENTCORE_MEMORY_ID="memory_io2n5-94iksj6Jr7"


# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "api.py"]
