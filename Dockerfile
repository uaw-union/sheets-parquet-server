# Use the slim version of the Python 3.11 image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1

# Install Poetry
RUN pip install poetry

# Set the working directory
WORKDIR /app

# Copy only requirements to cache them in Docker layer
COPY poetry.lock pyproject.toml ./

# Disable Poetry virtualenv creation and install dependencies
RUN poetry config virtualenvs.create false \
	&& poetry install --no-interaction --no-ansi --no-dev

# Copying the rest of the application
COPY . /app

EXPOSE 3000

# Command to run the Uvicorn server
CMD ["poetry", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "3000"]
