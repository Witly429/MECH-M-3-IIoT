# MCI – Industrial Internet of Things (IIoT)

**Projekt:** Temperatur- und Luftfeuchtigkeitsüberwachung mit Raspberry Pi Pico W  
**Lehrveranstaltung:** Industrial Internet of Things (MCI, WS 2026)  
**Technologien:** CircuitPython, DHT11, MQTT, HTTP, Python, SQLite, Streamlit, Docker Compose

## 1. Projektüberblick

Das Projekt erfasst Temperatur und relative Luftfeuchtigkeit über einen DHT11 am Raspberry Pi Pico W. Der Pico verbindet sich mit einem WLAN, versieht die Messwerte mit UTC-Zeitstempeln und überträgt sie an einen MQTT-Broker. Eine HTTP-API auf dem Pico ermöglicht das Auslesen des Gerätestatus sowie das Ändern des Messintervalls während der Laufzeit.

Ein separater Python-MQTT-Empfänger abonniert die Sensordaten und Statusmeldungen, speichert die Messwerte als CSV und in einer SQLite-Datenbank und registriert neue Sensoren automatisch. Ein Streamlit-Dashboard visualisiert die Daten und zeigt Geräteaktivität und statistische Kennzahlen. Die Cloud-Anwendung wird mit Docker Compose gestartet.

Die Entwicklung ist in drei aufeinander aufbauende Termine unterteilt:

| Termin | Schwerpunkt | Dokumentation |
| --- | --- | --- |
| **1 – MQTT** | Pico W, DHT11, WLAN, MQTT-Telemetrie und Gerätestatus | [Termin 1](Termin_1_MQTT/README.md) |
| **2 – Netzwerke** | HTTP-API (`/config`, `/status`), OpenAPI und automatisierte Tests | [Termin 2](Termin_2_Netzwerke/README.md) |
| **3 – Cloud** | MQTT-Empfänger, CSV, SQLite, Streamlit und Docker Compose | [Termin 3](Termin_3_Cloud/README.md) |

## 2. Systemarchitektur

```text
DHT11 (Temperatur / Feuchtigkeit)
              |
              v
   Raspberry Pi Pico W (CircuitPython)
       |                    |
       | MQTT / TCP 1883    | HTTP / TCP 80 (lokales Netz)
       v                    v
 Externer MQTT-Broker    GET /config, POST /config,
       |                 GET /status, GET /
       |
       | MQTT-Subscription
       v
  Python-MQTT-Empfänger (Docker)
       |
       +------> CSV-Datei
       |
       +------> SQLite-Datenbank <------ Streamlit-Dashboard (Docker)
                                           |
                                           v
                                   http://localhost:8501
```

Der Pico verwendet außerdem NTP zur Ermittlung von UTC-Zeitstempeln. Der MQTT-Broker ist extern; er wird nicht als Teil von Docker Compose betrieben.

## 3. Repository-Struktur

```text
MCI_IIoT_pico/
├── README.md                       # Projektübersicht (diese Datei)
├── .gitignore                      # Ausnahmen für Git
├── Termin_1_MQTT/
│   ├── README.md
│   ├── code.py                      # Dokumentierter Pico-Firmwarestand
│   └── settings.toml               # Konfiguration ohne Zugangsdaten
├── Termin_2_Netzwerke/
│   ├── README.md
│   ├── code.py                      # Firmware mit HTTP-API
│   ├── settings.toml
│   └── tests/
│       └── test_http_api.py        # 17 pytest-Testdurchläufe
└── Termin_3_Cloud/
    ├── README.md
    ├── mqtt_receiver.py
    ├── dashboard.py
    ├── settings.toml
    ├── requirements.txt
    ├── Dockerfile
    ├── compose.yaml
    └── .dockerignore
```

**Nur lokal, nicht in Git:** `Secrets.py`, `.env`, virtuelle Python-Umgebungen sowie der Ordner `Termin_3_Cloud/data/` mit CSV- und SQLite-Dateien.

Die Firmware für Termin 1 und 2 kann teilweise dieselben später erweiterten Funktionen enthalten. Für den tatsächlichen Betrieb auf dem Pico ist jeweils **eine** `code.py` auf dem Laufwerk `CIRCUITPY` aktiv.

## 4. Hardware und Voraussetzungen

- Raspberry Pi Pico W mit CircuitPython
- DHT11, angeschlossen an **GP22**
- WLAN mit Zugang zum externen MQTT-Broker
- Passende CircuitPython-Bibliotheken (`adafruit_dht`, `adafruit_ntp`, `adafruit_minimqtt` sowie deren Abhängigkeiten)
- Für API-Tests: Python 3 und `pytest` auf dem Computer
- Für die Cloud-Anwendung: Docker Engine / Docker Desktop mit Docker Compose

## 5. Pico W einrichten

1. CircuitPython auf dem Pico W installieren und das Laufwerk `CIRCUITPY` öffnen.
2. Die aktuelle Firmware (`Termin_2_Netzwerke/code.py`) und die passende `settings.toml` in das Stammverzeichnis von `CIRCUITPY` kopieren.
3. Die benötigten CircuitPython-Bibliotheken in `CIRCUITPY/lib/` bereitstellen.
4. Im Stammverzeichnis von `CIRCUITPY` eine **lokale** `Secrets.py` mit den eigenen Zugangsdaten anlegen:

   ```python
   WIFI_SSID = "DEIN_WLAN"
   WIFI_PASSWORD = "DEIN_WLAN_PASSWORT"
   MQTT_USERNAME = "DEIN_MQTT_BENUTZERNAME"
   MQTT_PASSWORD = "DEIN_MQTT_PASSWORT"
   ```

5. Den Pico starten und auf der seriellen Konsole die WLAN-Verbindung, IP-Adresse und MQTT-Verbindung prüfen.

**Wichtig:** Die Groß-/Kleinschreibung der Datei `Secrets.py` und der Variablennamen muss zu `import Secrets` im Pico-Code passen. Diese Datei niemals committen.

Die nicht geheimen Einstellungen wie `device_id`, MQTT-Topics, Sensorpin und Messintervall werden über die Pico-`settings.toml` geladen. Der Startwert für `reading_interval_seconds` beträgt gemäß der umgesetzten HTTP-API mindestens **2** (Ganzzahl).

Weitere Details: [Termin 1](Termin_1_MQTT/README.md) und [Termin 2](Termin_2_Netzwerke/README.md).

## 6. HTTP-API und Tests (Termin 2)

Der Pico stellt im lokalen WLAN auf TCP-Port **80** folgende Endpunkte bereit:

| Methode | Endpunkt | Zweck |
| --- | --- | --- |
| `GET` | `/` | Einfacher Erreichbarkeitstest |
| `GET` | `/config` | Aktuelle Konfiguration lesen |
| `POST` | `/config` | Messintervall während der Laufzeit ändern |
| `GET` | `/status` | Gerätestatus, Laufzeit, Verbindungen und letzte Messwerte |

Beispiel (Pico-IP gegebenenfalls anpassen):

```powershell
curl.exe http://172.20.10.5/status
```

Die API orientiert sich an der verbindlichen **OpenAPI-Spezifikation 1.2.0**. Ungültige Konfigurationswerte werden mit HTTP 400 abgewiesen. Das Intervall muss eine Ganzzahl von mindestens 2 Sekunden sein. Änderungen über `POST /config` werden derzeit **nicht dauerhaft** in `settings.toml` gespeichert und gehen bei einem Neustart verloren.

Automatisierte Tests aus dem Repository-Hauptordner ausführen:

```powershell
python -m pip install pytest
python -m pytest .\Termin_2_Netzwerke\tests\test_http_api.py -v
```

**Letzter bestätigter Testlauf:** 17 von 17 `pytest`-Tests bestanden (10.11.2026, realer Pico). Der Computer muss den Pico über das WLAN erreichen können. In der Testdatei ist eine Beispiel-IP hinterlegt; alternativ kann `PICO_BASE_URL` gesetzt werden.

## 7. Cloud-Anwendung mit Docker Compose starten (Termin 3)

Die Cloud-Anwendung benötigt MQTT-Zugangsdaten in einer lokalen Datei `Termin_3_Cloud/.env`:

```dotenv
MQTT_USERNAME=DEIN_MQTT_BENUTZERNAME
MQTT_PASSWORD=DEIN_MQTT_PASSWORT
```

Die Datei bleibt außerhalb von Git. Die Broker-Adresse, Topic-Wildcards und Pfade stehen in `Termin_3_Cloud/settings.toml`.

Im Ordner `Termin_3_Cloud` ausführen:

```powershell
docker compose up -d --build
docker compose ps
```

Dashboard im Browser öffnen: **http://localhost:8501**

Zur Fehlersuche und zum Beenden:

```powershell
docker compose logs --tail=50 mqtt_receiver
docker compose logs --tail=50 dashboard
docker compose down
```

Docker Compose startet zwei Dienste: `mqtt_receiver` und `dashboard`. Beide greifen auf den eingebundenen Host-Ordner `Termin_3_Cloud/data/` zu; darin bleiben die Messwerte bei einem normalen Container-Neustart erhalten. Beim ersten Start wird der Ordner gegebenenfalls neu angelegt. Er ist nicht Teil des Repositorys.

**Bestätigter Projektstand:** Beide Container wurden unter Docker Desktop erfolgreich gestartet; MQTT-Empfang und Dashboard wurden geprüft. Ein vollständiger Persistenztest nach `docker compose down` und anschließendem Start ist bei der Endabnahme zusätzlich empfehlenswert.

Weitere Details: [Termin 3](Termin_3_Cloud/README.md).

## 8. Datenspeicherung und Dashboard

Der MQTT-Empfänger liest Sensormeldungen über Wildcard-Topics wie `iiot/group/+/sensor/+/state` und Statusmeldungen über `iiot/group/+/status`.

Die SQLite-Datenbank enthält die Tabellen:

- `measurements`: Messwerte mit Zeitstempel, Gerätekennung, Sensortyp, Wert und Einheit
- `sensors`: automatisch erkannte Geräte und Messkanäle mit `first_seen` und `last_seen`
- `group_status`: zuletzt empfangene MQTT-Statusmeldungen

Das Dashboard zeigt die Sensorübersicht und die letzte Aktivität, erlaubt die Auswahl von Gruppe, Gerät und Messgröße und visualisiert Zeitverlauf, letzten Messwert, Mittelwert, Minimum und Maximum. Die Ansicht aktualisiert sich etwa alle fünf Sekunden.

## 9. Netzwerk und Sicherheit

| Verbindung | Richtung | Protokoll / Port | Zweck |
| --- | --- | --- | --- |
| Pico → MQTT-Broker | Ausgehend | TCP 1883 | Sensordaten und Status |
| Pico → NTP-Server | Ausgehend | UDP 123 | UTC-Zeitstempel |
| Laptop → Pico | Im lokalen Netz | TCP 80 | HTTP-API und Konfiguration |
| Browser → Dashboard | Lokal auf dem Host | TCP 8501 | Visualisierung |

Die Geräte müssen entsprechend den lokalen Firewall- und WLAN-Regeln erreichbar sein. Die HTTP-API verwendet **kein TLS und keine Authentifizierung** und sollte nicht ungeschützt ins Internet freigegeben werden. Auch das hier verwendete MQTT-Setup auf Port 1883 ist ohne zusätzliche TLS-Konfiguration unverschlüsselt.

Vor einem öffentlichen GitHub-Push sicherstellen, dass **keine Passwörter, Tokens, `.env`-, `Secrets.py`- oder Messdaten-Dateien** im Repository oder in seiner Git-Historie enthalten sind.

## 10. Bekannte Grenzen

- Die HTTP-Konfiguration wird nur während der Laufzeit geändert; ein Neustart lädt erneut `settings.toml`.
- Die HTTP-API ist lokal erreichbar; ein abgesicherter Fernzugriff (z. B. VPN) ist nicht implementiert.
- In der aktuellen Tabelle `measurements` ist kein `group_name` gespeichert. Falls verschiedene Gruppen dieselbe `sensor_id` und denselben `sensor_type` verwenden, könnten die Messwerte in der Analyse vermischt werden.
- Der Dashboard-Gerätestatus kombiniert MQTT-Status und Zeit seit dem letzten Messwert. Diese Heuristik ersetzt keine kontinuierliche Ende-zu-Ende-Erreichbarkeitsprüfung.

## 11. Quellen und Kursmaterial

- [MCI – Kursübersicht und Bewertung](https://jhumci.github.io/MECH-M-3-IIoT/)
- [MCI – Termin 2: Netzwerke](https://jhumci.github.io/MECH-M-3-IIoT/docs/Termin_2_Netzwerke)
- [MCI – Termin 3: Cloud](https://jhumci.github.io/MECH-M-3-IIoT/docs/Termin_3_Cloud.html)
- [OpenAPI-Spezifikation](https://github.com/jhumci/MECH-M-3-IIoT/blob/main/docs/iot-specs/openapi.yaml)
- [Original-Repositories des Kurses](https://github.com/jhumci/MECH-M-3-IIoT)

Die detaillierten Einrichtungsschritte und die terminbezogenen Anforderungen befinden sich jeweils in den Unterordnern.
