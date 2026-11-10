# Termin 2 – Netzwerke und HTTP-API

**MCI · Industrial Internet of Things (IIoT) · Wintersemester 2026/27**  
**Hardware:** Raspberry Pi Pico W mit DHT11 · **Firmware:** CircuitPython

## 1. Projektübersicht

In Termin 2 wird die MQTT-Sensoranwendung aus Termin 1 um eine lokale **HTTP-API** erweitert. Der Raspberry Pi Pico W misst weiterhin Temperatur und relative Luftfeuchtigkeit und sendet sie an einen MQTT-Broker. Zusätzlich beantwortet er HTTP-Anfragen auf **TCP-Port 80**.

Über die Schnittstelle lassen sich die aktuelle Konfiguration und der Gerätestatus abrufen. Das Messintervall kann zur Laufzeit geändert werden. Die API orientiert sich an der für den Kurs verbindlichen **OpenAPI-Spezifikation Version 1.2.0**.

**Umgesetzte Funktionen:**

- `GET /` als einfacher Erreichbarkeitstest
- `GET /config` zum Auslesen der Konfiguration
- `POST /config` zum Ändern des Messintervalls im laufenden Betrieb
- `GET /status` für Gerätestatus und letzte Sensorwerte
- JSON-Antworten und geeignete HTTP-Statuscodes (`200`, `400`, `404`, `405`)
- Integration von HTTP, MQTT und Sensormessung in der Pico-Hauptschleife
- Automatisierte Tests mit `pytest`

**Testergebnis:** Die **17 automatisierten Testfälle** wurden am 10.11.2026 vom Projektteam gegen den realen Pico W ausgeführt und waren **alle erfolgreich** (`17 passed`). Dieses Ergebnis bezieht sich auf die vorhandenen Tests und ersetzt keine vollständige, automatisierte OpenAPI-Schemaprüfung.

## 2. Systemarchitektur

```text
                        Lokales WLAN / Hotspot
  +------------------+                         +-----------------------+
  | Laptop           | -- HTTP / TCP 80 ----> | Raspberry Pi Pico W   |
  | Browser / curl   |                         | CircuitPython         |
  | pytest           | <--- JSON / Text ----- | HTTP-Server           |
  +------------------+                         |                       |
                                               | DHT11 an GP22         |
                                               | MQTT-Client           |
                                               +-----------+-----------+
                                                           |
                                                           | MQTT / TCP 1883
                                                           v
                                               +-----------------------+
                                               | Externer MQTT-Broker  |
                                               +-----------------------+

  NTP-Zeitserver -- UDP 123 --> Pico W (UTC-Zeitstempel)
```

Der HTTP-Server wurde in CircuitPython direkt mit `socketpool` umgesetzt. Er läuft auf dem Pico selbst; auf dem Laptop wird dafür keine Serveranwendung benötigt.

## 3. Dateien im Repository

```text
MCI_IIoT_pico/
├── .gitignore
├── Termin_1_MQTT/
├── Termin_2_Netzwerke/
│   ├── code.py                 # Pico-Firmware: MQTT, DHT11 und HTTP-API
│   ├── settings.toml           # Konfiguration ohne Zugangsdaten
│   ├── tests/
│   │   └── test_http_api.py    # Automatisierte HTTP-API-Tests
│   └── README.md               # Diese Dokumentation
└── Termin_3_Cloud/
```

**Nicht im Git-Repository speichern:** `Secrets.py`, `.env`, WLAN- oder MQTT-Passwörter und lokale Messdaten. Die produktiven Zugangsdaten werden auf dem Pico in einer separaten, nicht versionierten Datei `Secrets.py` hinterlegt.

## 4. Hardware und Software

| Komponente | Aufgabe |
| --- | --- |
| Raspberry Pi Pico W | WLAN-fähiger Mikrocontroller und HTTP-Server |
| DHT11 an GP22 | Temperatur- und Feuchtigkeitsmessung |
| CircuitPython | Ausführung der Firmware |
| `wifi`, `socketpool`, `board` | Netzwerk und GPIO des Pico |
| `adafruit_dht` | DHT11 auslesen |
| `adafruit_minimqtt` | MQTT-Daten versenden |
| `adafruit_ntp` | UTC-Uhrzeit beziehen |
| Python 3 und `pytest` auf dem Laptop | Automatisierte API-Tests |

Die zusätzlichen CircuitPython-Bibliotheken und ihre Abhängigkeiten müssen passend zur installierten CircuitPython-Version auf dem Pico im Verzeichnis `CIRCUITPY/lib/` liegen.

## 5. Einrichtung und Konfiguration

1. CircuitPython auf dem Pico W installieren.
2. `code.py` und die **bereinigte** `settings.toml` aus `Termin_2_Netzwerke/` in das Stammverzeichnis des Laufwerks `CIRCUITPY` kopieren.
3. Die benötigten Bibliotheken in `CIRCUITPY/lib/` bereitstellen.
4. Direkt neben `code.py` eine lokale `Secrets.py` mit WLAN- und MQTT-Zugangsdaten anlegen.
5. Pico und Test-Laptop mit demselben erreichbaren WLAN verbinden.
6. Die serielle Ausgabe kontrollieren. Sie zeigt unter anderem die IP-Adresse des Pico und den Start des HTTP-Servers auf Port 80 an.

### Zugangsdaten (`Secrets.py`)

Die Datei ist **nur lokal auf dem Pico** erforderlich und darf nicht committed werden:

```python
WIFI_SSID = "DEIN_WLAN"
WIFI_PASSWORD = "DEIN_WLAN_PASSWORT"
MQTT_USERNAME = "DEIN_MQTT_BENUTZERNAME"
MQTT_PASSWORD = "DEIN_MQTT_PASSWORT"
```

Die Firmware verwendet `import Secrets`. Groß- und Kleinschreibung der Variablennamen müssen daher genau stimmen.

### Einstellungen (`settings.toml`)

Die Firmware liest die Konfiguration beim Start mit `os.getenv()` ein. Für Termin 2 ist insbesondere dieser Parameter wichtig:

```toml
reading_interval_seconds = 2
```

Der Wert muss eine **Ganzzahl ab 2 Sekunden** sein. Weitere Einstellungen umfassen Gerätekennung, Sensor-Pin, Broker, MQTT-Topics, Statusmeldungen und Keep-Alive. Die verwendete Konfigurationsdatei im Repository darf keine Zugangsdaten enthalten.

**Wichtig:** `POST /config` ändert das Intervall nur **im Arbeitsspeicher**. Nach einem Neustart gilt wieder der Wert aus `settings.toml`. Eine dauerhafte Speicherung per HTTP ist nicht implementiert und wird für die Grundanforderung nicht vorausgesetzt.

## 6. HTTP-API

**Basisadresse:** `http://<PICO_IP>`  
**Protokoll:** HTTP ohne TLS · **Port:** 80

| Methode | Pfad | Beschreibung | Antwort |
| --- | --- | --- | --- |
| `GET` | `/` | Erreichbarkeit prüfen | `200`, Text `pico laeuft` |
| `GET` | `/config` | Aktuelle Konfiguration auslesen | `200`, JSON |
| `POST` | `/config` | Messintervall ändern | `200` oder `400`, JSON |
| `GET` | `/status` | Gerätestatus und letzte Messwerte | `200`, JSON |
| Andere Methode auf bekanntem Pfad | – | Methode nicht erlaubt | `405`, JSON |
| Unbekannter Pfad | – | Endpunkt nicht gefunden | `404`, JSON |

Die folgenden Beispiele verwenden die **während der Entwicklung genutzte** Pico-IP `172.20.10.5`. Sie kann sich ändern; maßgeblich ist die IP aus der seriellen Ausgabe des Pico.

### 6.1 `GET /` – Verbindung prüfen

```powershell
curl.exe http://172.20.10.5/
```

Erwartete Textantwort:

```text
pico laeuft
```

### 6.2 `GET /config` – Konfiguration auslesen

```powershell
curl.exe http://172.20.10.5/config
```

Beispielantwort:

```json
{
  "device_id": "pico-hvw-resch-jacobs-doleschel-01",
  "reading_interval_seconds": 2
}
```

Die `device_id` stammt aus der konkreten `settings.toml` und kann bei einem anderen Gerät anders lauten.

### 6.3 `POST /config` – Messintervall ändern

Der folgende PowerShell-Befehl setzt das Intervall auf fünf Sekunden:

```powershell
$body = @{ reading_interval_seconds = 5 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://172.20.10.5/config" -Method Post -ContentType "application/json" -Body $body
```

Anschließend kann das neue Intervall mit `GET /config` überprüft werden.

**Validierung gemäß OpenAPI 1.2.0:** Nur ganze Zahlen von mindestens `2` werden akzeptiert. Beispiele:

| Übermittelter Wert | Erwarteter HTTP-Status |
| --- | --- |
| `2`, `5`, `120` | `200 OK` |
| `1`, `0`, `-5` | `400 Bad Request` |
| `2.5`, `"5"`, `true`, `null` | `400 Bad Request` |
| Fehlendes Feld oder fehlerhaftes JSON | `400 Bad Request` |

Eine fehlgeschlagene Konfigurationsanfrage liefert beispielsweise:

```json
{"error": "Ungueltige Konfiguration"}
```

Die Gerätekennung `device_id` kann nicht über diesen Endpunkt geändert werden.

### 6.4 `GET /status` – Gerätestatus

```powershell
curl.exe http://172.20.10.5/status
```

Beispielantwort (Werte zur Veranschaulichung):

```json
{
  "device_id": "pico-hvw-resch-jacobs-doleschel-01",
  "uptime_seconds": 28,
  "wifi_connected": true,
  "mqtt_connected": true,
  "last_telemetry": {
    "timestamp": "2026-11-10T13:18:53Z",
    "value": 23.2,
    "unit": "°C"
  },
  "last_humidity_percent": 46,
  "last_temperature": 23.2,
  "last_humidity": 46,
  "last_timestamp": "2026-11-10T13:18:53Z",
  "reading_interval_seconds": 2
}
```

Die ersten sechs Felder entsprechen den Pflichtfeldern der OpenAPI-Spezifikation:

| Feld | Bedeutung |
| --- | --- |
| `device_id` | Eindeutige Gerätekennung |
| `uptime_seconds` | Laufzeit seit Programmstart |
| `wifi_connected` | Status der WLAN-Verbindung |
| `mqtt_connected` | Status der MQTT-Verbindung laut Firmware |
| `last_telemetry` | Letzte Temperaturmessung mit UTC-Zeitstempel und Einheit `°C` |
| `last_humidity_percent` | Letzte gemessene relative Luftfeuchtigkeit |

Vor der ersten erfolgreichen Messung können `last_telemetry` und `last_humidity_percent` den Wert `null` haben. Die übrigen Felder (`last_temperature`, `last_humidity`, `last_timestamp`, `reading_interval_seconds`) sind zusätzliche Informationen zur Kompatibilität und Diagnose.

## 7. Automatisierte Tests mit `pytest`

Die Tests befinden sich unter `tests/test_http_api.py` und werden **auf dem Laptop gegen den laufenden Pico** ausgeführt, nicht auf dem Mikrocontroller.

### Installation

```powershell
python -m pip install pytest
```

Alternativ kann eine vorhandene Python-Umgebung benutzt werden, in der `pytest` installiert ist.

### Tests starten

Im Hauptverzeichnis `MCI_IIoT_pico`:

```powershell
python -m pytest .\Termin_2_Netzwerke\tests\test_http_api.py -v
```

Wenn die virtuelle Python-Umgebung von Termin 3 genutzt wird:

```powershell
.\Termin_3_Cloud\.venv\Scripts\python.exe -m pytest .\Termin_2_Netzwerke\tests\test_http_api.py -v
```

Die Testdatei verwendet standardmäßig `http://172.20.10.5`. Die Adresse kann ohne Codeänderung in PowerShell überschrieben werden:

```powershell
$env:PICO_BASE_URL = "http://172.20.10.5"
python -m pytest .\Termin_2_Netzwerke\tests\test_http_api.py -v
```

### Abgedeckte Testfälle

| Test | Prüfung |
| --- | --- |
| `test_root` | `GET /` antwortet mit HTTP 200 |
| `test_get_config` | Geräte-ID und Ganzzahl-Intervall ab 2 Sekunden |
| `test_get_status` | Pflichtfelder, Typen und Temperatur-Zeitstempel |
| `test_post_config` | Intervall ändern, auslesen und wiederherstellen |
| `test_404` | Unbekannter Pfad führt zu 404 |
| `test_405` | Nicht erlaubte Methode führt zu 405 |
| `test_invalid_config` | Sieben ungültige Werte werden separat getestet |
| `test_missing_config_field` | Fehlender Konfigurationsparameter führt zu 400 |
| `test_malformed_json` | Fehlerhaftes JSON führt zu 400 |
| `test_device_id_not_changeable` | Änderung allein über `device_id` wird abgewiesen |
| `test_server_still_responds` | Server funktioniert nach ungültigen Anfragen weiter |

Die Parametrisierung von `test_invalid_config` erzeugt sieben einzelne Testdurchläufe. Insgesamt werden somit **17 Tests** ausgeführt.

**Zuletzt gemeldetes Ergebnis (10.11.2026):**

```text
17 passed
```

Der Test `test_post_config` stellt das ursprüngliche Messintervall in einem `finally`-Block wieder her. Die Tests prüfen die genannten Anwendungsfälle; sie führen keine vollständige maschinelle Validierung aller OpenAPI-Schemaeigenschaften durch.

## 8. Technische Umsetzung

- HTTP-Listen-Socket auf `0.0.0.0:80`, bereitgestellt über `socketpool`.
- `accept()` verwendet einen nicht blockierenden Socket, damit die Hauptschleife nicht dauerhaft auf einen HTTP-Client wartet.
- `SO_REUSEADDR` und ein verzögerter erneuter Startversuch helfen bei Socket-Problemen nach einem Neustart.
- HTTP-Header und Request-Body werden getrennt eingelesen. Die Implementierung berücksichtigt `Content-Length` und in mehreren Paketen eintreffende Anfragen.
- Header und Body sind auf 4096 beziehungsweise 2048 Bytes begrenzt.
- Client-Verbindungen werden nach der Bearbeitung geschlossen.
- `server.poll()` wird nach der Korrektur in jedem Durchlauf der Hauptschleife unabhängig vom MQTT-Fehlerzweig aufgerufen.
- Sensorwerte werden weiterhin gemäß `SEND_INTERVAL` gemessen und über MQTT veröffentlicht.

Die Firmware und der HTTP-Server werden im selben CircuitPython-Prozess ausgeführt. Die Verarbeitung ist nicht parallel; längere Netzwerkoperationen können daher die Reaktionszeit beeinflussen.

## 9. Netzwerkintegration und Firewall

Die örtliche IT-Abteilung muss das 2,4-GHz-WLAN und erforderliche Verbindungen freigeben. Bei Firewall-Whitelists sind folgende Kommunikationswege relevant:

| Richtung | Kommunikationspartner | Protokoll / Port | Zweck |
| --- | --- | --- | --- |
| Pico → MQTT-Broker | `158.180.44.197` | TCP `1883` | MQTT-Messwerte und Gerätestatus |
| Pico → NTP-Server | NTP-Zeitquelle | UDP `123` | UTC-Zeitsynchronisation |
| Pico → DNS, wenn erforderlich | DNS-Resolver | UDP/TCP `53` | Hostnamen auflösen |
| Laptop → Pico | Lokaler Test-/Administrationsrechner | TCP `80` | HTTP-API aufrufen |

Zusätzlich sind folgende Netzwerkbedingungen wichtig:

- Das WLAN muss mit dem Pico W kompatibel sein (2,4 GHz).
- Der Laptop muss den Pico erreichen können; **Client Isolation**, VLAN-Regeln oder Firewalls dürfen den lokalen HTTP-Zugriff nicht blockieren.
- Ausgehende MQTT-Verbindungen zum Broker und gegebenenfalls NTP/DNS müssen erlaubt sein.
- Die Geräte-IP kann sich durch DHCP ändern; eine DHCP-Reservierung kann die Verwaltung erleichtern.
- Nur unbedingt notwendige Ports und Quellnetze freigeben.

### Zugriff von außerhalb des lokalen WLANs

Die HTTP-Schnittstelle verwendet **unverschlüsseltes HTTP ohne Zugangskontrolle**. Sie sollte deshalb **nicht direkt über eine Router-Portweiterleitung ins öffentliche Internet freigegeben** werden. Für Fernzugriff wäre beispielsweise ein VPN in das lokale Netzwerk oder ein abgesicherter Gateway mit TLS und Authentifizierung sinnvoll. Diese Lösungen sind im Projekt nicht implementiert.

Auch die im Projekt verwendete MQTT-Verbindung über TCP-Port 1883 ist nicht TLS-verschlüsselt. Deshalb sollte der Betrieb auf geeignete, vertrauenswürdige Netze beschränkt oder für einen produktiven Einsatz entsprechend abgesichert werden.

## 10. Fehlerbehebung

| Problem | Mögliche Ursache / Lösung |
| --- | --- |
| `curl` läuft in einen Timeout | Pico-IP und WLAN prüfen; HTTP-Hauptschleife oder blockierende Operationen kontrollieren |
| `Connection refused` | Server nicht gestartet oder Port 80 nicht gebunden; serielle Pico-Ausgabe lesen |
| `404 Not Found` | Pfad falsch geschrieben |
| `405 Method Not Allowed` | Unzulässige HTTP-Methode verwendet |
| `400 Bad Request` bei `/config` | Intervall fehlt, ist kleiner als 2, keine Ganzzahl oder JSON fehlerhaft |
| `pytest` nicht gefunden | Richtige virtuelle Umgebung aktivieren oder `python -m pip install pytest` |
| API im Hotspot erreichbar, aber nicht im Standortnetz | Firewall, VLANs oder Client Isolation überprüfen |
| Messintervall nach Neustart zurückgesetzt | Erwartetes Verhalten: HTTP-Änderungen werden nicht persistent gespeichert |

## 11. Projektstand und Grenzen

**Erfolgreich umgesetzt und getestet:** HTTP-Endpunkte, Pflichtfelder, ganzzahliges Messintervall ab 2 Sekunden, Fehlerantworten und 17 automatisierte Testfälle am Pico W.

**Bewusste Einschränkungen:**

- Die Konfiguration wird über HTTP nur zur Laufzeit geändert.
- Die HTTP-API verfügt weder über TLS noch über Authentifizierung.
- Die Tests verwenden `pytest`, kein automatisches OpenAPI-Schema-Testwerkzeug wie Schemathesis.
- Ein vollständiger Sicherheitstest oder Belastungstest wurde nicht durchgeführt.

**Vor der endgültigen Git-Abgabe noch prüfen:** Die *aktualisierte* `code.py`, die bereinigte `settings.toml`, diese README und die aktuelle `tests/test_http_api.py` müssen im selben Repository-Stand liegen. Die lokal getestete Firmware auf dem Pico darf nicht mit einer älteren Git-Kopie verwechselt werden.

## 12. Referenzen

- [MCI – Termin 2: Netzwerke und Aufgabenstellung](https://jhumci.github.io/MECH-M-3-IIoT/docs/Termin_2_Netzwerke)
- [Verbindliche OpenAPI-Spezifikation, Version 1.2.0](https://github.com/jhumci/MECH-M-3-IIoT/blob/main/docs/iot-specs/openapi.yaml)
- [MQTT-/Datenkonventionen](https://github.com/jhumci/MECH-M-3-IIoT/blob/main/docs/iot-specs/conventions.md)

---

**Einordnung:** Die MQTT-Grundlagen sind in [`../Termin_1_MQTT/`](../Termin_1_MQTT/) dokumentiert. Datenspeicherung, Streamlit-Dashboard und Docker Compose gehören zu [`../Termin_3_Cloud/`](../Termin_3_Cloud/).
