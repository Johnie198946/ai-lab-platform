FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HERMES_HOME=/opt/hermes \
    AI_LAB_HERMES_TEMPLATE=/opt/ai-lab/hermes-template \
    AI_LAB_SANDBOX_ROOT=/var/lib/ai-lab/sandboxes \
    AI_LAB_STATE_DB=/var/lib/ai-lab/state/runs.sqlite3

WORKDIR /srv/ai-lab
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend

RUN mkdir -p /opt/ai-lab/hermes-template /var/lib/ai-lab/sandboxes /var/lib/ai-lab/state
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
