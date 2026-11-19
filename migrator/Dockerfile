FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt/gaq
COPY migrator/requirements.txt /opt/gaq/requirements.txt
RUN pip install --no-cache-dir -r /opt/gaq/requirements.txt && useradd --system --uid 10002 gaqmigrator
COPY migrator/ensure.py /opt/gaq/ensure.py
COPY db/ /opt/gaq/sql/
USER gaqmigrator
CMD ["python", "/opt/gaq/ensure.py"]
