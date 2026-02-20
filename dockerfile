FROM python:3.11-slim

WORKDIR /app

# System deps if needed (psycopg3 binary usually fine; keep minimal)
RUN python -m pip install --upgrade pip

# Copy only requirements first for caching
COPY requirements.txt /app/requirements.txt
RUN python -m pip install -r requirements.txt

# Now copy the repo
COPY . /app

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]