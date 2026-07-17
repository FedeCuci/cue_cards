FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn
COPY app.py .
CMD ["gunicorn", "-b", "0.0.0.0:8100", "app:app"]
