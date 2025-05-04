FROM python:3.11-slim
WORKDIR /app
COPY payment/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY utils /app/utils
COPY payment/src /app/payment/src
CMD ["python", "payment/src/app.py"]