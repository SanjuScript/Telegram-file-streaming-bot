# Use a lightweight python base image
FROM python:3.11-slim

# Set environment variables to optimize Python performance
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create and set working directory
WORKDIR /app

# Copy the dependencies file
COPY requirements.txt .

# Install dependencies without cache to minimize image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code
COPY app/ ./app/

# Expose port (must match PORT in .env, default 8000)
EXPOSE 8000

# Command to run the application
CMD ["python", "-m", "app.main"]
