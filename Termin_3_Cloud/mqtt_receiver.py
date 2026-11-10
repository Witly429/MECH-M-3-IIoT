
import os
import json
import csv
import tomllib
import sqlite3

from pathlib import Path
from dotenv import load_dotenv
import paho.mqtt.client as mqtt


# ============================================================
# 1. KONFIGURATION LADEN
# ============================================================

# Verzeichnis bestimmen, in dem sich dieses Python-Skript befindet.
# Dadurch funktionieren die Dateipfade unabhängig davon,
# aus welchem Verzeichnis das Programm gestartet wird.
BASE_DIR = Path(__file__).resolve().parent

# Zugangsdaten aus der .env-Datei laden.
# Diese Datei enthält sensible Informationen und wird
# deshalb nicht im Git-Repository gespeichert.
load_dotenv(BASE_DIR / ".env")

# Allgemeine Einstellungen aus settings.toml einlesen.
# TOML enthält unter anderem die MQTT- und Speicherparameter.
with open(BASE_DIR / "settings.toml", "rb") as file:
    settings = tomllib.load(file)

# MQTT-Broker und Verbindungsparameter
BROKER = settings["mqtt"]["broker_address"]
PORT = settings["mqtt"]["broker_port"]
KEEP_ALIVE = settings["mqtt"]["keep_alive"]

# MQTT-Topic für Sensormesswerte.
# Durch Wildcards (+) können Messwerte verschiedener
# Gruppen und Sensortypen empfangen werden.
TOPIC = settings["mqtt"]["telemetry_topic"]

# MQTT-Topic für Gerätestatusmeldungen
STATUS_TOPIC = settings["mqtt"]["status_topic"]

# Benutzername und Passwort aus den Umgebungsvariablen.
# Die Variablen wurden zuvor aus .env geladen.
USERNAME = os.environ["MQTT_USERNAME"]
PASSWORD = os.environ["MQTT_PASSWORD"]

# Speicherorte für CSV-Datei und SQLite-Datenbank.
# Die Pfade werden relativ zum Projektverzeichnis gebildet.
CSV_FILE = BASE_DIR / settings["storage"]["csv_file"]
DB_FILE = BASE_DIR / settings["storage"]["database_file"]


# ============================================================
# 2. CSV-SPEICHERUNG
# ============================================================

def save_to_csv(data, sensor_type):
    """
    Speichert einen empfangenen Sensormesswert in einer CSV-Datei.

    Parameter:
        data:
            Dictionary mit timestamp, sensor_id, value und unit.

        sensor_type:
            Art des Sensors, z. B. temperature oder humidity.

    Die CSV-Datei wird bei Bedarf angelegt.
    Neue Messwerte werden an das Dateiende angehängt.
    """

    # Prüfen, ob die CSV-Datei bereits vorhanden ist.
    file_exists = CSV_FILE.exists()

    # Datei im Append-Modus öffnen.
    # Dadurch bleiben bereits gespeicherte Messwerte erhalten.
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as file:

        writer = csv.writer(file)

        # Spaltenüberschriften nur schreiben, wenn die Datei
        # neu erstellt wurde oder noch leer ist.
        if not file_exists or CSV_FILE.stat().st_size == 0:
            writer.writerow([
                "timestamp",
                "sensor_id",
                "sensor_type",
                "value",
                "unit"
            ])

        # Aktuellen Messwert als neue CSV-Zeile speichern.
        writer.writerow([
            data["timestamp"],
            data["sensor_id"],
            sensor_type,
            data["value"],
            data["unit"]
        ])


# ============================================================
# 3. SQLITE-DATENBANK
# ============================================================

def init_database():
    """
    Initialisiert die SQLite-Datenbank.

    Falls die Datenbank oder einzelne Tabellen noch nicht
    existieren, werden sie automatisch angelegt.

    Es werden drei Tabellen verwendet:

        measurements:
            Speichert sämtliche empfangenen Messwerte.

        sensors:
            Verwaltet automatisch erkannte Sensoren.

        group_status:
            Speichert den zuletzt empfangenen Status
            der jeweiligen MQTT-Gruppe.
    """

    # Verbindung zur SQLite-Datenbank herstellen.
    # Die Datenbankdatei wird bei Bedarf neu erstellt.
    with sqlite3.connect(DB_FILE) as conn:

        # ----------------------------------------------------
        # Tabelle 1: measurements
        # ----------------------------------------------------
        # Speichert jeden empfangenen Sensormesswert.
        #
        # id:
        #     Eindeutige, automatisch erzeugte Datensatz-ID.
        #
        # timestamp:
        #     Zeitstempel der Messung.
        #
        # sensor_id:
        #     Kennung des sendenden Geräts.
        #
        # sensor_type:
        #     Sensortyp, z. B. temperature oder humidity.
        #
        # value:
        #     Numerischer Messwert.
        #
        # unit:
        #     Physikalische Einheit des Messwerts.

        conn.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                sensor_id TEXT NOT NULL,
                sensor_type TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL
            )
        """)

        # ----------------------------------------------------
        # Tabelle 2: sensors
        # ----------------------------------------------------
        # Registriert Sensoren automatisch anhand
        # der empfangenen MQTT-Nachrichten.
        #
        # Ein Sensor wird durch die Kombination aus
        # group_name, sensor_id und sensor_type identifiziert.
        #
        # first_seen:
        #     Zeitpunkt der ersten Registrierung.
        #
        # last_seen:
        #     Zeitpunkt der letzten empfangenen Messung.
        #
        # Dadurch kann das Dashboard erkennen, welche
        # Sensoren vorhanden sind und zuletzt aktiv waren.

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sensors (
                group_name TEXT NOT NULL,
                sensor_id TEXT NOT NULL,
                sensor_type TEXT NOT NULL,
                unit TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,

                PRIMARY KEY (
                    group_name,
                    sensor_id,
                    sensor_type
                )
            )
        """)

        # ----------------------------------------------------
        # Tabelle 3: group_status
        # ----------------------------------------------------
        # Speichert den zuletzt gemeldeten Gerätestatus
        # einer MQTT-Gruppe.
        #
        # Mögliche Statuswerte sind beispielsweise:
        #     ok
        #     error
        #     offline
        #
        # Pro Gruppe wird nur der aktuelle Status gespeichert.

        conn.execute("""
            CREATE TABLE IF NOT EXISTS group_status (
                group_name TEXT PRIMARY KEY,
                sensor_id TEXT,
                status TEXT NOT NULL,
                last_status_at TEXT NOT NULL
            )
        """)

    print("SQLite-Datenbank bereit:", DB_FILE)


# ============================================================
# 4. MESSWERTE IN SQLITE SPEICHERN
# ============================================================

def save_to_database(data, sensor_type):
    """
    Speichert einen einzelnen Sensormesswert in SQLite.

    Jeder empfangene Messwert wird als neuer Datensatz
    in der Tabelle measurements abgelegt.

    Die SQL-Platzhalter (?) ermöglichen die sichere
    Übergabe der Messwerte an die Datenbank.
    """

    with sqlite3.connect(DB_FILE) as conn:

        conn.execute("""
            INSERT INTO measurements (
                timestamp,
                sensor_id,
                sensor_type,
                value,
                unit
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            data["timestamp"],
            data["sensor_id"],
            sensor_type,
            float(data["value"]),
            data["unit"]
        ))


# ============================================================
# 5. AUTOMATISCHE SENSORERKENNUNG
# ============================================================

def register_sensor(data, group_name, sensor_type):
    """
    Registriert einen Sensor in der SQLite-Datenbank.

    Wird ein Sensor zum ersten Mal erkannt, wird ein
    neuer Eintrag in der Tabelle sensors erstellt.

    Ist der Sensor bereits vorhanden, werden lediglich
    last_seen und die Einheit aktualisiert.

    Die Erkennung basiert auf:
        group_name
        sensor_id
        sensor_type
    """

    # ----------------------------------------------------
    # Aktuellen Empfangszeitpunkt bestimmen
    # ----------------------------------------------------

    # Der Zeitpunkt wird in UTC gespeichert, damit
    # alle Sensoren eine einheitliche Zeitbasis besitzen.
    from datetime import datetime, timezone

    now = datetime.now(
        timezone.utc
    ).isoformat()

    # ----------------------------------------------------
    # Sensor registrieren oder aktualisieren
    # ----------------------------------------------------

    with sqlite3.connect(DB_FILE) as conn:

        # INSERT legt einen neuen Sensor an.
        #
        # ON CONFLICT verhindert doppelte Einträge
        # bei bereits bekannten Sensoren.
        #
        # In diesem Fall wird der vorhandene Eintrag
        # mit dem neuen Empfangszeitpunkt aktualisiert.

        conn.execute("""
            INSERT INTO sensors (
                group_name,
                sensor_id,
                sensor_type,
                unit,
                first_seen,
                last_seen
            )
            VALUES (?, ?, ?, ?, ?, ?)

            ON CONFLICT (
                group_name,
                sensor_id,
                sensor_type
            )
            DO UPDATE SET
                last_seen = excluded.last_seen,
                unit = excluded.unit

        """, (
            group_name,
            data["sensor_id"],
            sensor_type,
            data["unit"],
            now,
            now
        ))


# ============================================================
# 6. MQTT-GERÄTESTATUS SPEICHERN
# ============================================================

def save_status(group_name, data):
    """
    Speichert den zuletzt empfangenen Status einer Gruppe.

    Die Statusinformationen werden aus einer MQTT-Nachricht
    ausgelesen und in der Tabelle group_status gespeichert.

    Existiert bereits ein Eintrag für die Gruppe,
    wird dieser mit dem neuen Status überschrieben.

    Zusätzlich wird der Empfangszeitpunkt in UTC gespeichert.
    """

    from datetime import datetime, timezone

    # Statusfeld aus der empfangenen JSON-Nachricht lesen.
    status = data.get("status")

    # Nachrichten ohne gültigen Status ignorieren.
    if not isinstance(status, str):
        print("Statusnachricht ohne gueltigen Status")
        return

    # Gerätekennung auslesen.
    # Falls keine gültige Kennung vorhanden ist,
    # wird in der Datenbank NULL gespeichert.
    sensor_id = data.get("sensor_id")

    if not isinstance(sensor_id, str):
        sensor_id = None

    # Aktuellen Empfangszeitpunkt bestimmen.
    now = datetime.now(timezone.utc).isoformat()

    # ----------------------------------------------------
    # Gruppenstatus in SQLite speichern
    # ----------------------------------------------------

    with sqlite3.connect(DB_FILE) as conn:

        # Jede Gruppe besitzt genau einen Statuseintrag.
        #
        # Bei einem neuen Status wird der vorhandene
        # Eintrag durch ON CONFLICT aktualisiert.

        conn.execute("""
            INSERT INTO group_status (
                group_name,
                sensor_id,
                status,
                last_status_at
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(group_name)
            DO UPDATE SET
                sensor_id = excluded.sensor_id,
                status = excluded.status,
                last_status_at = excluded.last_status_at
        """, (
            group_name,
            sensor_id,
            status,
            now
        ))

    print("Status aktualisiert:", group_name, status)


# ============================================================
# 7. MQTT-CALLBACK: VERBINDUNG HERGESTELLT
# ============================================================

def on_connect(client, userdata, flags, reason_code, properties):
    """
    Wird aufgerufen, sobald sich der MQTT-Client
    mit dem Broker verbunden hat.

    Bei erfolgreicher Verbindung werden die Topics
    für Sensormesswerte und Gerätestatus abonniert.

    Die Callback-Signatur entspricht der
    Paho-MQTT Callback API Version 2.
    """

    # reason_code == 0 bedeutet erfolgreiche Verbindung.
    if reason_code == 0:
        print("MQTT verbunden!")

        # Sensormesswerte abonnieren.
        client.subscribe(TOPIC)

        # Gerätestatusmeldungen abonnieren.
        client.subscribe(STATUS_TOPIC)

        # Abonnierte Topics zur Kontrolle ausgeben.
        print("Messwerte:", TOPIC)
        print("Status:", STATUS_TOPIC)

    else:
        # Fehlercode ausgeben, wenn die Verbindung
        # zum MQTT-Broker fehlgeschlagen ist.
        print("MQTT Fehler:", reason_code)


# ============================================================
# 8. MQTT-CALLBACK: NACHRICHT EMPFANGEN
# ============================================================

def on_message(client, userdata, msg):
    """
    Verarbeitet eingehende MQTT-Nachrichten.

    Abhängig vom MQTT-Topic wird zwischen
    zwei Nachrichtentypen unterschieden:

        1. Statusmeldungen
        2. Sensormesswerte

    Die empfangenen JSON-Nachrichten werden überprüft
    und anschließend in der Datenbank gespeichert.

    Sensormesswerte werden zusätzlich in CSV abgelegt.
    """

    # ----------------------------------------------------
    # 8.1 Leere Nachrichten überprüfen
    # ----------------------------------------------------

    # Leere MQTT-Nachrichten enthalten keine auswertbaren
    # Sensordaten und werden deshalb ignoriert.
    if not msg.payload:
        print("Leere MQTT-Nachricht ignoriert:", msg.topic)
        return

    # ----------------------------------------------------
    # 8.2 JSON-Nachricht dekodieren
    # ----------------------------------------------------

    try:
        # Empfangene Bytes zuerst in UTF-8 dekodieren
        # und anschließend als JSON interpretieren.
        data = json.loads(msg.payload.decode("utf-8"))

    except (ValueError, UnicodeError):
        # Ungültige JSON-Nachrichten werden verworfen,
        # ohne das gesamte Programm zu beenden.
        print("Kein gueltiges JSON:", msg.topic)
        return

    # Es werden ausschließlich JSON-Objekte erwartet.
    # Andere JSON-Datentypen werden ignoriert.
    if not isinstance(data, dict):
        print("Ungueltiges Nachrichtenformat:", msg.topic)
        return

    # ----------------------------------------------------
    # 8.3 MQTT-Topic analysieren
    # ----------------------------------------------------

    # Beispiel für ein Sensortopic:
    #
    # iiot/group/gruppe/sensor/temperature/state
    #
    # Aufteilung:
    # [0] iiot
    # [1] group
    # [2] gruppe
    # [3] sensor
    # [4] temperature
    # [5] state

    topic_parts = msg.topic.split("/")

    # Topics mit zu wenigen Bestandteilen ignorieren.
    if len(topic_parts) < 4:
        print("Unbekanntes MQTT-Topic:", msg.topic)
        return

    # Gruppennamen aus dem Topic extrahieren.
    group_name = topic_parts[2]

    # ----------------------------------------------------
    # 8.4 Statusnachrichten verarbeiten
    # ----------------------------------------------------

    # Erwartetes Topic:
    #
    # iiot/group/<gruppe>/status
    #
    # Eine Statusnachricht besitzt vier Topic-Bestandteile.

    if len(topic_parts) == 4 and topic_parts[3] == "status":

        # Prüfen, ob ein gültiges Statusfeld vorhanden ist.
        if not isinstance(data.get("status"), str):
            print("Status ohne gueltiges Feld:", msg.topic)
            return

        # Status der entsprechenden Gruppe speichern.
        save_status(group_name, data)
        return

    # ----------------------------------------------------
    # 8.5 Sensormesswerte verarbeiten
    # ----------------------------------------------------

    # Erwartetes Topic:
    #
    # iiot/group/<gruppe>/sensor/<sensortyp>/state
    #
    # Beispielsweise:
    # iiot/group/testgruppe/sensor/temperature/state
    # iiot/group/testgruppe/sensor/humidity/state
    #
    # Der Sensortyp wird direkt aus dem Topic gelesen.

    if (
        len(topic_parts) == 6
        and topic_parts[3] == "sensor"
        and topic_parts[5] == "state"
    ):

        try:
            # Sensortyp aus dem MQTT-Topic extrahieren.
            sensor_type = topic_parts[4]

            # Messwert in der SQLite-Datenbank speichern.
            save_to_database(data, sensor_type)

            # Messwert zusätzlich in CSV speichern.
            save_to_csv(data, sensor_type)

            # Sensor automatisch registrieren oder
            # den letzten Empfangszeitpunkt aktualisieren.
            register_sensor(data, group_name, sensor_type)

            # Erfolgreiche Speicherung protokollieren.
            print(
                "Messwert gespeichert:",
                group_name,
                sensor_type,
                data["value"]
            )

        except (ValueError, KeyError, TypeError) as error:
            # Unvollständige oder ungültige Messwerte
            # werden protokolliert und ignoriert.
            print("Ungueltiger Messwert:", error)

        return

    # ----------------------------------------------------
    # 8.6 Nicht unterstützte Topics
    # ----------------------------------------------------

    # Nachrichten, die keiner der beiden erwarteten
    # Topic-Strukturen entsprechen, werden ignoriert.
    print("Nicht unterstuetztes Topic:", msg.topic)


# ============================================================
# 9. MQTT-CLIENT INITIALISIEREN
# ============================================================

# MQTT-Client mit Paho Callback API Version 2 erstellen.
client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2
)

# Benutzername und Passwort für die Broker-Anmeldung setzen.
client.username_pw_set(USERNAME, PASSWORD)

# Callback-Funktionen registrieren.
# Diese werden später automatisch von Paho-MQTT aufgerufen.
client.on_connect = on_connect
client.on_message = on_message


# ============================================================
# 10. DATENBANK INITIALISIEREN
# ============================================================

# Vor dem MQTT-Empfang sicherstellen, dass alle
# benötigten SQLite-Tabellen vorhanden sind.
init_database()


# ============================================================
# 11. MQTT-VERBINDUNG STARTEN
# ============================================================

print("Verbinde mit MQTT-Broker...")

# Verbindung zum MQTT-Broker herstellen.
client.connect(BROKER, PORT, KEEP_ALIVE)

# MQTT-Ereignisschleife dauerhaft starten.
#
# Diese Funktion verarbeitet unter anderem:
#   - Eingehende MQTT-Nachrichten
#   - Verbindungsereignisse
#   - MQTT-Keep-Alive
#   - Aufrufe der registrierten Callback-Funktionen
#
# Das Programm läuft dadurch kontinuierlich,
# bis es manuell beendet wird oder ein Fehler auftritt.
client.loop_forever()
