FROM python:3.12-alpine

WORKDIR /app

RUN pip install --no-cache-dir aiohttp==3.10.11

COPY app.py /app/app.py

EXPOSE 8080

ENV PORT=8080

CMD ["python", "/app/app.py"]
