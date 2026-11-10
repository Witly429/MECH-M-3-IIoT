
# Python 3.12 als Basis
FROM python:3.12-slim

# Arbeitsverzeichnis im Container
WORKDIR /app

# Python-Ausgaben sofort anzeigen
ENV PYTHONUNBUFFERED=1

# Abhängigkeiten installieren
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Projektdateien kopieren
COPY mqtt_receiver.py .
COPY dashboard.py .
COPY settings.toml .

# Verzeichnis für Messdaten
RUN mkdir -p /app/data

# Streamlit-Port
EXPOSE 8501
