FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml ./
COPY main.py ./

RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.34" "aiofiles>=24"

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-8} --no-access-log --no-server-header"]
