# Use an official Python runtime as a parent image (adjust version as needed)
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Using --no-cache-dir to reduce image size
# Ensure your requirements.txt includes 'uvicorn', 'python-dotenv', 'markdown' etc.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container at /app
# This includes api.py, model_tooluse.txt, and the entire templates directory
COPY api.py .
COPY model_tooluse.txt . 
COPY templates ./templates

# Make port 5001 available to the world outside this container
# This should match the port your uvicorn server in api.py listens on
EXPOSE 5001

# Define environment variables that your application needs.
# These should be set in your runtime environment (e.g., ECS Task Definition)
ENV PYTHONUNBUFFERED=1
ENV PORT=5001
ENV HOST="0.0.0.0" # Important for Docker to allow external connections to the container
# ENV STRANDS_KNOWLEDGE_BASE_ID="your-kb-id-from-runtime-env"
# ENV AWS_REGION="your-aws-region-from-runtime-env" # e.g., us-east-1
# ENV SESSION_SECRET_KEY="a-very-strong-random-secret-key-from-runtime-env"

# Command to run your application using Uvicorn
# Note: "api:app" refers to the 'app' FastAPI instance in the 'api.py' file.
# reload=True is removed for production/containerized environments.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "5001"]
