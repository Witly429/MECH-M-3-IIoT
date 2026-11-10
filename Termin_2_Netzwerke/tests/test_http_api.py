
"""
Automatisierte HTTP-API-Tests für Termin 2 (OpenAPI 1.2.0).

Aufruf im Repository-Hauptverzeichnis:
    python -m pytest Termin_2_Netzwerke/tests/test_http_api.py -v

Der Pico muss eingeschaltet und vom Laptop erreichbar sein.
Die URL kann mit der Umgebungsvariable PICO_BASE_URL überschrieben werden.
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime

import pytest


# --------------------------------------------------
# Konfiguration
# --------------------------------------------------

# IP-Adresse gegebenenfalls an das aktuelle WLAN anpassen.
BASE_URL = os.environ.get(
    "PICO_BASE_URL",
    "http://172.20.10.5"
).rstrip("/")


# --------------------------------------------------
# Hilfsfunktion für HTTP-Anfragen
# --------------------------------------------------

def request(method, path, data=None, raw_body=None):
    """
    HTTP-Anfrage senden.

    Auch HTTP-Fehlerantworten (z. B. 400, 404, 405)
    werden als Ergebnis zurückgegeben.
    """

    body = None
    headers = {}

    # Python-Daten in JSON umwandeln
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    # Alternativ einen unveränderten JSON-String senden
    elif raw_body is not None:
        body = raw_body.encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        BASE_URL + path,
        data=body,
        headers=headers,
        method=method
    )

    try:
        response = urllib.request.urlopen(req, timeout=10)

    except urllib.error.HTTPError as error:
        response = error

    with response:
        text = response.read().decode("utf-8")
        return response.status, text


# --------------------------------------------------
# Test 1: Erreichbarkeit des Pico
# --------------------------------------------------

def test_root():
    """GET / muss HTTP 200 zurückgeben."""

    status, body = request("GET", "/")

    assert status == 200
    assert "pico laeuft" in body


# --------------------------------------------------
# Test 2: Konfiguration auslesen
# --------------------------------------------------

def test_get_config():
    """GET /config liefert Geräte-ID und gültiges Messintervall."""

    status, body = request("GET", "/config")

    assert status == 200

    data = json.loads(body)

    assert isinstance(data["device_id"], str)
    assert data["device_id"]

    # Messintervall muss eine Ganzzahl >= 2 sein
    assert type(data["reading_interval_seconds"]) is int
    assert data["reading_interval_seconds"] >= 2


# --------------------------------------------------
# Test 3: Gerätestatus auslesen
# --------------------------------------------------

def test_get_status():
    """GET /status enthält die Pflichtfelder aus OpenAPI 1.2.0."""

    status, body = request("GET", "/status")

    assert status == 200

    data = json.loads(body)

    # Vorgeschriebene Felder überprüfen
    required = (
        "device_id",
        "uptime_seconds",
        "wifi_connected",
        "mqtt_connected",
        "last_telemetry",
        "last_humidity_percent"
    )

    for field in required:
        assert field in data, f"Pflichtfeld fehlt: {field}"

    # Datentypen kontrollieren
    assert isinstance(data["device_id"], str)

    assert type(data["uptime_seconds"]) is int
    assert data["uptime_seconds"] >= 0

    assert type(data["wifi_connected"]) is bool
    assert type(data["mqtt_connected"]) is bool

    # Luftfeuchtigkeit kann vor der ersten Messung null sein
    humidity = data["last_humidity_percent"]

    assert humidity is None or (
        type(humidity) in (int, float)
    )

    # Letzte Temperaturmessung kontrollieren
    telemetry = data["last_telemetry"]

    if telemetry is not None:

        assert isinstance(telemetry, dict)

        assert all(
            key in telemetry
            for key in ("timestamp", "value", "unit")
        )

        assert isinstance(telemetry["timestamp"], str)

        # ISO-8601-Zeitstempel mit Zeitzoneninformation
        timestamp = datetime.fromisoformat(
            telemetry["timestamp"].replace("Z", "+00:00")
        )

        assert timestamp.tzinfo is not None

        assert type(telemetry["value"]) in (int, float)
        assert telemetry["unit"] == "°C"


# --------------------------------------------------
# Test 4: Konfiguration ändern
# --------------------------------------------------

def test_post_config():
    """
    Messintervall auf 5 Sekunden ändern.

    Danach wird der ursprüngliche Wert wiederhergestellt,
    damit die Tests die Gerätekonfiguration nicht verändern.
    """

    # Ursprüngliches Messintervall speichern
    status, body = request("GET", "/config")

    assert status == 200

    old_interval = json.loads(body)[
        "reading_interval_seconds"
    ]

    try:
        # Neues Messintervall setzen
        status, body = request(
            "POST",
            "/config",
            {"reading_interval_seconds": 5}
        )

        assert status == 200

        response_data = json.loads(body)

        assert type(
            response_data["reading_interval_seconds"]
        ) is int

        assert response_data["reading_interval_seconds"] == 5

        # Kontrollieren, ob der neue Wert gespeichert wurde
        status, body = request("GET", "/config")

        assert status == 200

        data = json.loads(body)

        assert data["reading_interval_seconds"] == 5

    finally:
        # Ursprüngliche Einstellung wiederherstellen
        request(
            "POST",
            "/config",
            {"reading_interval_seconds": old_interval}
        )


# --------------------------------------------------
# Test 5: Unbekannter Endpunkt
# --------------------------------------------------

def test_404():
    """Ein unbekannter Pfad muss HTTP 404 liefern."""

    status, body = request("GET", "/xyz")

    assert status == 404


# --------------------------------------------------
# Test 6: Nicht erlaubte HTTP-Methode
# --------------------------------------------------

def test_405():
    """POST /status muss HTTP 405 liefern."""

    status, body = request("POST", "/status")

    assert status == 405


# --------------------------------------------------
# Tests 7-13: Ungültige Messintervalle
# --------------------------------------------------

@pytest.mark.parametrize(
    "invalid_value",
    [-5, 0, 1, 2.5, "5", True, None]
)
def test_invalid_config(invalid_value):
    """
    Nur ganzzahlige Messintervalle ab 2 Sekunden
    dürfen akzeptiert werden.

    pytest führt diesen Test für jeden der sieben
    angegebenen Werte separat aus.
    """

    status, body = request(
        "POST",
        "/config",
        {"reading_interval_seconds": invalid_value}
    )

    assert status == 400
    assert "error" in json.loads(body)


# --------------------------------------------------
# Test 14: Fehlendes Konfigurationsfeld
# --------------------------------------------------

def test_missing_config_field():
    """Ein fehlendes Pflichtfeld muss HTTP 400 auslösen."""

    status, body = request(
        "POST",
        "/config",
        {"unexpected": 5}
    )

    assert status == 400
    assert "error" in json.loads(body)


# --------------------------------------------------
# Test 15: Fehlerhaftes JSON
# --------------------------------------------------

def test_malformed_json():
    """
    Ungültiges JSON darf den HTTP-Server
    nicht zum Absturz bringen.
    """

    status, body = request(
        "POST",
        "/config",
        raw_body='{"reading_interval_seconds":'
    )

    assert status == 400
    assert "error" in json.loads(body)


# --------------------------------------------------
# Test 16: Geräte-ID darf nicht geändert werden
# --------------------------------------------------

def test_device_id_not_changeable():
    """
    Eine Anfrage, die nur eine andere Geräte-ID enthält,
    darf die Konfiguration nicht ändern.
    """

    status, body = request(
        "POST",
        "/config",
        {"device_id": "andere-id"}
    )

    assert status == 400


# --------------------------------------------------
# Test 17: Server nach Fehlern erreichbar
# --------------------------------------------------

def test_server_still_responds():
    """
    Der HTTP-Server muss nach ungültigen Anfragen
    weiterhin erreichbar sein.
    """

    status, body = request("GET", "/status")

    assert status == 200
    assert "device_id" in json.loads(body)
