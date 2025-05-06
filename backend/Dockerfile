# Use Python base image
FROM python:3.9

# Set working directory
WORKDIR /app

# Copy backend code
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt


# Run the Flask app
CMD ["python", "app.py"]

