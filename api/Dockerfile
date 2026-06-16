FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY alembic.ini .
COPY pyproject.toml .
COPY migrations ./migrations
COPY app ./app
COPY tests ./tests

RUN useradd --create-home --shell /usr/sbin/nologin appuser
RUN mkdir -p /data/audio /data/portraits && chown -R appuser:appuser /data
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
