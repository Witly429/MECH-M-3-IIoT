import wifi
import socketpool
import os
import time
import json
import board
import adafruit_dht
import adafruit_ntp
import adafruit_minimqtt.adafruit_minimqtt as MQTT
import Secrets

print("Secrets-Datei:", dir(Secrets))

# --------------------------------------------------
# Einstellungen aus settings.toml laden
# --------------------------------------------------

DEVICE_ID = os.getenv("device_id")
NAMES = os.getenv("names")
LOCATION = os.getenv("location")

MQTT_BROKER = os.getenv("broker_address")
MQTT_PORT = int(os.getenv("broker_port"))

WIFI_SSID = Secrets.WIFI_SSID
WIFI_PASSWORD = Secrets.WIFI_PASSWORD

MQTT_USER = Secrets.MQTT_USERNAME
MQTT_PASSWORD = Secrets.MQTT_PASSWORD

DATA_TOPIC = os.getenv("telemetry_topic")
HUMIDITY_TOPIC = os.getenv("humidity_topic")
STATUS_TOPIC = os.getenv("status_topic")

SEND_INTERVAL = int(os.getenv("reading_interval_seconds"))
DHT_PIN = int(os.getenv("sensor_pin"))

SENSOR_TYPE = os.getenv("sensor_type")
SENSOR_UNIT = os.getenv("sensor_unit")

STATUS_OK = os.getenv("status_ok")
STATUS_ERROR = os.getenv("status_error")
STATUS_OFFLINE = os.getenv("status_offline")

STATUS_QOS = int(os.getenv("status_qos"))
STATUS_RETAIN = bool(os.getenv("status_retain"))

LWT_QOS = int(os.getenv("lwt_qos"))
LWT_RETAIN = bool(os.getenv("lwt_retain"))

MQTT_KEEP_ALIVE = int(os.getenv("mqtt_keep_alive"))
MQTT_CLIENT_ID = os.getenv("mqtt_client_id")


# --------------------------------------------------
# Statusinformationen
# --------------------------------------------------

START_TIME = time.monotonic()

LAST_TEMPERATURE = None
LAST_HUMIDITY = None
LAST_TIMESTAMP = None

MQTT_CONNECTED = False

LAST_STATUS = None


# --------------------------------------------------
# WLAN
# --------------------------------------------------

print("Verbinde mit WLAN...")

wifi.radio.connect(
    WIFI_SSID,
    WIFI_PASSWORD
)

print("WLAN verbunden!")
print("IP:", wifi.radio.ipv4_address)

pool = socketpool.SocketPool(wifi.radio)


# --------------------------------------------------
# Uhrzeit über NTP
# UTC, weil ISO-8601 mit Z verwendet wird
# --------------------------------------------------

ntp = adafruit_ntp.NTP(
    pool,
    tz_offset=0
)


# --------------------------------------------------
# DHT11
# --------------------------------------------------

dht_pin = getattr(
    board,
    "GP" + str(DHT_PIN)
)

dht = adafruit_dht.DHT11(
    dht_pin
)


# --------------------------------------------------
# MQTT
# --------------------------------------------------

mqtt_client = MQTT.MQTT(
    broker=MQTT_BROKER,
    port=MQTT_PORT,
    username=MQTT_USER,
    password=MQTT_PASSWORD,
    client_id=MQTT_CLIENT_ID,
    socket_pool=pool,
    keep_alive=MQTT_KEEP_ALIVE
)


# --------------------------------------------------
# Last Will
# --------------------------------------------------

offline_payload = json.dumps({
    "status": STATUS_OFFLINE,
    "sensor_id": DEVICE_ID
})

mqtt_client.will_set(
    STATUS_TOPIC,
    offline_payload,
    qos=LWT_QOS,
    retain=LWT_RETAIN
)


# --------------------------------------------------
# MQTT verbinden
# --------------------------------------------------

print("Verbinde mit MQTT...")

mqtt_client.connect()
MQTT_CONNECTED = True

print("MQTT verbunden!")


# --------------------------------------------------
# Online-Status senden
# --------------------------------------------------

ok_payload = json.dumps({
    "status": STATUS_OK,
    "sensor_id": DEVICE_ID
})

mqtt_client.publish(
    STATUS_TOPIC,
    ok_payload,
    qos=STATUS_QOS,
    retain=STATUS_RETAIN
)

LAST_STATUS = STATUS_OK

print("Status ->", STATUS_OK)


# --------------------------------------------------
# HTTP-Server
# --------------------------------------------------

class WebServer:

    def __init__(self, socket_pool):
        self._pool = socket_pool
        self._server = None
        self._next_start = 0

    def start(self):
        if self._server is not None:
            return

        if time.monotonic() < self._next_start:
            return

        sock = None

        try:
            sock = self._pool.socket(
                self._pool.AF_INET,
                self._pool.SOCK_STREAM
            )

            sock.setsockopt(
                self._pool.SOL_SOCKET,
                self._pool.SO_REUSEADDR,
                1
            )

            sock.setblocking(False)
            sock.bind(("0.0.0.0", 80))
            sock.listen(1)

            self._server = sock

            print("HTTP-Server auf Port 80")

        except OSError as error:
            print("HTTP-Start fehlgeschlagen:", error)

            if sock is not None:
                sock.close()

            self._next_start = time.monotonic() + 3

    def poll(self):
        global SEND_INTERVAL

        if self._server is None:
            self.start()
            return

        try:
            client, _addr = self._server.accept()

        except OSError:
            return

        try:
            client.settimeout(2)

            # HTTP-Anfrage vollständig empfangen
            request_data = bytearray()
            buffer = bytearray(512)

            # Header einlesen
            while b"\r\n\r\n" not in request_data:

                received = client.recv_into(buffer)

                if received == 0:
                    raise ValueError("Verbindung geschlossen")

                request_data.extend(buffer[:received])

                if len(request_data) > 4096:
                    raise ValueError("HTTP-Header zu gross")

            header_bytes, _, body_bytes = bytes(
                request_data
            ).partition(b"\r\n\r\n")

            header = header_bytes.decode("utf-8")

            # Content-Length auslesen
            content_length = 0

            for line in header.split("\r\n"):

                if line.lower().startswith("content-length:"):
                    content_length = int(
                        line.split(":", 1)[1].strip()
                    )

            if content_length > 2048 or content_length < 0:
                raise ValueError("Ungueltige Content-Length")

            # Restlichen Body empfangen
            while len(body_bytes) < content_length:

                received = client.recv_into(buffer)

                if received == 0:
                    raise ValueError("Body unvollstaendig")

                body_bytes += bytes(buffer[:received])

            body = body_bytes[:content_length].decode("utf-8")

            # Request-Zeile auswerten
            first_line = header.split("\r\n")[0]
            parts = first_line.split(" ")

            method = parts[0]
            path = parts[1].split("?", 1)[0]

            status = "200 OK"
            content_type = "application/json"

            # ------------------------------------------
            # GET /
            # ------------------------------------------

            if method == "GET" and path == "/":

                response_body = "pico laeuft"
                content_type = "text/plain"

            # ------------------------------------------
            # GET /config
            # ------------------------------------------

            elif method == "GET" and path == "/config":

                response_body = json.dumps({
                    "device_id": DEVICE_ID,
                    "reading_interval_seconds": SEND_INTERVAL
                })

            # ------------------------------------------
            # GET /status
            # Gerätestatus gemäß OpenAPI 1.2.0
            # ------------------------------------------

            elif method == "GET" and path == "/status":

                # Letzte Temperaturmessung zusammenstellen
                last_telemetry = None

                if LAST_TIMESTAMP is not None and LAST_TEMPERATURE is not None:
                    last_telemetry = {
                        "timestamp": LAST_TIMESTAMP,
                        "value": LAST_TEMPERATURE,
                        "unit": SENSOR_UNIT
                    }

                response_body = json.dumps({
                    "device_id": DEVICE_ID,
                    "uptime_seconds": int(
                        time.monotonic() - START_TIME
                    ),
                    "wifi_connected": wifi.radio.connected,
                    "mqtt_connected": MQTT_CONNECTED,
                    "last_telemetry": last_telemetry,
                    "last_humidity_percent": LAST_HUMIDITY,

                    # Bisherige Felder beibehalten
                    "last_temperature": LAST_TEMPERATURE,
                    "last_humidity": LAST_HUMIDITY,
                    "last_timestamp": LAST_TIMESTAMP,
                    "reading_interval_seconds": SEND_INTERVAL
                })

            # ------------------------------------------
            # POST /config
            # ------------------------------------------

            elif method == "POST" and path == "/config":

                try:
                    data = json.loads(body)
                    interval = data["reading_interval_seconds"]

                    if (
                        isinstance(interval, bool)
                        or not isinstance(interval, int)
                        or interval < 2
                    ):
                        raise ValueError("Ungueltiges Intervall")

                    SEND_INTERVAL = int(interval)

                    response_body = json.dumps({
                        "device_id": DEVICE_ID,
                        "reading_interval_seconds": SEND_INTERVAL
                    })

                    print("Neues Messintervall:", SEND_INTERVAL)

                except (ValueError, KeyError, TypeError):

                    status = "400 Bad Request"

                    response_body = json.dumps({
                        "error": "Ungueltige Konfiguration"
                    })

            # ------------------------------------------
            # 405 Method Not Allowed
            # ------------------------------------------

            elif path in ("/", "/config", "/status"):

                status = "405 Method Not Allowed"

                response_body = json.dumps({
                    "error": "HTTP-Methode nicht erlaubt"
                })

            # ------------------------------------------
            # 404 Not Found
            # ------------------------------------------

            else:

                status = "404 Not Found"

                response_body = json.dumps({
                    "error": "Endpunkt nicht gefunden"
                })

            # HTTP-Antwort senden
            payload = response_body.encode("utf-8")

            response = (
                f"HTTP/1.1 {status}\r\n"
                f"Content-Type: {content_type}\r\n"
                "Connection: close\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "\r\n"
            ).encode("utf-8") + payload

            client.send(response)

        except Exception as error:
            print("HTTP-Fehler:", error)

        finally:
            client.close()


server = WebServer(pool)
server.start()


# --------------------------------------------------
# Hauptschleife
# --------------------------------------------------

letzte_messung = 0

while True:

    # MQTT-Verbindung bedienen
    try:
        mqtt_client.loop(timeout=1)

    except Exception as error:

        MQTT_CONNECTED = False

        print("---------------------------")
        print("MQTT-Verbindungsfehler!")
        print("Fehler:", repr(error))
        print("Uptime:", int(time.monotonic() - START_TIME))
        print("WLAN verbunden:", wifi.radio.connected)
        print("---------------------------")

        try:
            print("MQTT Reconnect...")

            mqtt_client.reconnect()

            MQTT_CONNECTED = True

            mqtt_client.publish(
                STATUS_TOPIC,
                json.dumps({
                    "status": STATUS_OK,
                    "sensor_id": DEVICE_ID
                }),
                qos=STATUS_QOS,
                retain=STATUS_RETAIN
            )

            LAST_STATUS = STATUS_OK

            print("MQTT wieder verbunden!")
            print("Status ->", STATUS_OK)

        except Exception as reconnect_error:
            MQTT_CONNECTED = False
            print("Reconnect fehlgeschlagen:", repr(reconnect_error))
            time.sleep(3)
            
    # HTTP-Server bedienen
    try:
        server.poll()

    except Exception as error:
        print("HTTP:", error)

    # Sensorwerte in eingestelltem Intervall messen
    if time.monotonic() - letzte_messung >= SEND_INTERVAL:

        letzte_messung = time.monotonic()

        try:
            # ------------------------------------------
            # Temperatur und Luftfeuchtigkeit auslesen
            # ------------------------------------------

            temperatur = dht.temperature
            feuchtigkeit = dht.humidity

            # ------------------------------------------
            # UTC-Zeit über NTP
            # ------------------------------------------

            now = ntp.datetime

            timestamp = (
                f"{now.tm_year:04d}-"
                f"{now.tm_mon:02d}-"
                f"{now.tm_mday:02d}T"
                f"{now.tm_hour:02d}:"
                f"{now.tm_min:02d}:"
                f"{now.tm_sec:02d}Z"
            )

            # Letzte Messwerte für HTTP speichern
            LAST_TEMPERATURE = temperatur
            LAST_HUMIDITY = feuchtigkeit
            LAST_TIMESTAMP = timestamp

            # ------------------------------------------
            # Temperatur per MQTT senden
            # ------------------------------------------

            temperature_payload = {
                "timestamp": timestamp,
                "sensor_id": DEVICE_ID,
                "value": temperatur,
                "unit": SENSOR_UNIT
            }

            temperature_message = json.dumps(
                temperature_payload
            )

            mqtt_client.publish(
                DATA_TOPIC,
                temperature_message
            )

            print("Temperatur gesendet:")
            print(DATA_TOPIC)
            print(temperature_message)

            # ------------------------------------------
            # Luftfeuchtigkeit per MQTT senden
            # ------------------------------------------

            humidity_payload = {
                "timestamp": timestamp,
                "sensor_id": DEVICE_ID,
                "value": feuchtigkeit,
                "unit": "%"
            }

            humidity_message = json.dumps(
                humidity_payload
            )

            mqtt_client.publish(
                HUMIDITY_TOPIC,
                humidity_message
            )

            # Nach erfolgreicher Messung Status korrigieren
            if LAST_STATUS != STATUS_OK:

                mqtt_client.publish(
                    STATUS_TOPIC,
                    json.dumps({
                        "status": STATUS_OK,
                        "sensor_id": DEVICE_ID
                    }),
                    qos=STATUS_QOS,
                    retain=STATUS_RETAIN
                )

                LAST_STATUS = STATUS_OK

                print("Status wieder OK")

            print("Luftfeuchtigkeit gesendet:")
            print(HUMIDITY_TOPIC)
            print(humidity_message)

            print("---------------------")

        # ----------------------------------------------
        # DHT11 Fehlerbehandlung
        # ----------------------------------------------

        except RuntimeError as error:

            print("DHT Fehler:", error)

            error_payload = json.dumps({
                "status": STATUS_ERROR,
                "sensor_id": DEVICE_ID
            })

            mqtt_client.publish(
                STATUS_TOPIC,
                error_payload,
                qos=STATUS_QOS,
                retain=STATUS_RETAIN
            )

            LAST_STATUS = STATUS_ERROR