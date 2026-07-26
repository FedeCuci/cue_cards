FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir flask gunicorn
COPY app.py .
# longer timeout so the "write missing answers" AI call isn't killed mid-request
CMD ["gunicorn", "-b", "0.0.0.0:8100", "--timeout", "180", "app:app"]
