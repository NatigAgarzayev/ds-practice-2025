FROM python:3.11-slim
WORKDIR /app

# Copy requirements and install
COPY books_database/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire src folder (including initial_stock.json!)
COPY books_database/src /app/books_database/src

# Also copy utils for your vector_clock & pb stubs
COPY utils /app/utils

CMD ["python", "books_database/src/app.py"]
