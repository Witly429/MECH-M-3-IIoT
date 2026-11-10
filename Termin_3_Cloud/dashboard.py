
import sqlite3
import tomllib

from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh


# ============================================================
# 1. KONFIGURATION LADEN
# ============================================================

# Verzeichnis bestimmen, in dem sich dieses Python-Skript befindet.
# Dadurch funktionieren die Dateipfade unabhängig davon,
# von welchem Verzeichnis aus das Dashboard gestartet wird.
BASE_DIR = Path(__file__).resolve().parent

# Einstellungen aus der settings.toml einlesen.
# Die Datei enthält unter anderem den Speicherort der Datenbank.
with open(BASE_DIR / "settings.toml", "rb") as file:
    settings = tomllib.load(file)

# Vollständigen Pfad zur SQLite-Datenbank erstellen.
# Die Datenbank wird vom MQTT-Empfänger mit Messwerten befüllt
# und vom Dashboard ausschließlich ausgelesen.
DB_FILE = BASE_DIR / settings["storage"]["database_file"]


# ============================================================
# 2. DATENBANKFUNKTIONEN
# ============================================================

def read_sql(query, params=()):
    """
    Führt eine SQL-Abfrage auf der SQLite-Datenbank aus.

    Parameter:
        query:
            SQL-Abfrage, die ausgeführt werden soll.

        params:
            Optionale Parameter für die SQL-Abfrage.

    Rückgabe:
        pandas.DataFrame mit den Ergebnissen der Abfrage.

    Die Datenbankverbindung wird nach der Abfrage
    automatisch wieder geschlossen.
    """

    # Verbindung zur SQLite-Datenbank herstellen.
    # timeout=10 erlaubt eine Wartezeit von bis zu 10 Sekunden,
    # falls die Datenbank vorübergehend gesperrt ist.
    with sqlite3.connect(DB_FILE, timeout=10) as conn:
        return pd.read_sql_query(query, conn, params=params)


def load_group_status():
    """
    Lädt die zuletzt gespeicherten MQTT-Statusmeldungen.

    Die Tabelle group_status enthält pro Gruppe
    den zuletzt empfangenen Gerätestatus.

    Verwendete Informationen:
        group_name:
            Name der MQTT-Gruppe.

        sensor_id:
            Gerätekennung.

        status:
            Zuletzt gemeldeter Status, beispielsweise
            ok, error oder offline.

        last_status_at:
            Empfangszeitpunkt der Statusmeldung.
    """

    return read_sql("""
        SELECT
            group_name,
            sensor_id,
            status,
            last_status_at
        FROM group_status
        ORDER BY group_name
    """)


def load_sensors():
    """
    Lädt alle automatisch registrierten Sensoren.

    Die Sensoren werden vom MQTT-Empfänger bei
    eingehenden Messwerten erkannt und in der
    Tabelle sensors gespeichert.

    Neben den Sensorinformationen werden auch
    der erste und letzte Empfangszeitpunkt geladen.
    """

    return read_sql("""
        SELECT
            group_name,
            sensor_id,
            sensor_type,
            unit,
            first_seen,
            last_seen
        FROM sensors
        ORDER BY group_name, sensor_id, sensor_type
    """)


def load_measurements(sensor_id, sensor_type):
    """
    Lädt die gespeicherten Messwerte eines Sensors.

    Parameter:
        sensor_id:
            Kennung des ausgewählten Geräts.

        sensor_type:
            Art der Messgröße, beispielsweise
            temperature oder humidity.

    Rückgabe:
        DataFrame mit Zeitstempel, Messwert und Einheit.

    Die SQL-Abfrage verwendet Platzhalter (?),
    um die Parameter sicher zu übergeben.

    Die Ergebnisse werden chronologisch sortiert.
    """

    return read_sql("""
        SELECT
            timestamp,
            value,
            unit
        FROM measurements
        WHERE sensor_id = ?
          AND sensor_type = ?
        ORDER BY timestamp
    """, (sensor_id, sensor_type))


# ============================================================
# 3. STREAMLIT-SEITE KONFIGURIEREN
# ============================================================

# Grundlegende Eigenschaften der Weboberfläche festlegen.
#
# page_title:
#     Titel des Browser-Tabs.
#
# page_icon:
#     Symbol im Browser-Tab.
#
# layout="wide":
#     Verwendet die verfügbare Bildschirmbreite.
st.set_page_config(
    page_title="MCI IIoT Dashboard",
    page_icon="📊",
    layout="wide"
)


# ============================================================
# 4. AUTOMATISCHE AKTUALISIERUNG
# ============================================================

# Das Dashboard soll neue Sensordaten automatisch anzeigen.
#
# st_autorefresh sorgt dafür, dass das Streamlit-Skript
# in regelmäßigen Abständen erneut ausgeführt wird.
#
# interval=5000:
#     Aktualisierung alle 5000 ms = 5 Sekunden.
#
# key:
#     Eindeutige Kennung der Aktualisierungskomponente.
#
# refresh_count:
#     Anzahl der bisherigen automatischen Aktualisierungen.
refresh_count = st_autorefresh(
    interval=5000,
    key="dashboard_refresh"
)

# Überschrift und kurze Beschreibung des Dashboards.
st.title("MCI – IIoT Dashboard")
st.caption("Temperatur- und Luftfeuchtigkeitsüberwachung")

# Anzahl der automatischen Aktualisierungen anzeigen.
st.caption(
    f"Automatische Aktualisierungen: {refresh_count}"
)

# Zusätzlich zur automatischen Aktualisierung kann
# das Dashboard manuell neu geladen werden.
if st.button("Daten aktualisieren"):
    st.rerun()

# Überprüfen, ob die SQLite-Datenbank vorhanden ist.
#
# Ohne Datenbank können keine Sensoren oder
# gespeicherten Messwerte angezeigt werden.
#
# st.stop() beendet die aktuelle Streamlit-Ausführung,
# sodass nachfolgende Datenbankabfragen vermieden werden.
if not DB_FILE.exists():
    st.error("Datenbank nicht gefunden.")
    st.stop()


# ============================================================
# 5. MQTT-GERÄTESTATUS UND AKTIVITÄTSPRÜFUNG
# ============================================================

st.header("MQTT-Gerätestatus")

# Zeitspanne, nach der ein Sensor als nicht mehr
# aktuell betrachtet wird.
#
# Hier werden 30 Sekunden verwendet.
OFFLINE_TIMEOUT = 30  # Sekunden ohne Messwert

try:
    # --------------------------------------------------------
    # 5.1 MQTT-Statusmeldungen laden
    # --------------------------------------------------------

    # Die zuletzt gemeldeten Zustände der Gruppen
    # aus der Tabelle group_status auslesen.
    status_df = load_group_status()

    # --------------------------------------------------------
    # 5.2 Letzten Empfang pro Gerät bestimmen
    # --------------------------------------------------------

    # Für jedes Gerät wird der aktuellste last_seen-Wert
    # aus der Sensortabelle ermittelt.
    #
    # MAX(last_seen) liefert den letzten Empfangszeitpunkt
    # über sämtliche Messkanäle eines Geräts.
    #
    # Dadurch reicht beispielsweise eine aktuelle
    # Temperaturmessung aus, um das Gerät als aktiv
    # zu erkennen.
    activity_df = read_sql("""
        SELECT
            group_name,
            sensor_id,
            MAX(last_seen) AS last_seen
        FROM sensors
        GROUP BY group_name, sensor_id
    """)

    # --------------------------------------------------------
    # 5.3 MQTT-Status und Sensoraktivität zusammenführen
    # --------------------------------------------------------

    # Die beiden Tabellen werden anhand von
    # group_name und sensor_id verbunden.
    #
    # how="left":
    #     Alle Geräte aus activity_df bleiben erhalten,
    #     auch wenn keine passende MQTT-Statusmeldung
    #     vorhanden ist.
    status_df = activity_df.merge(
        status_df,
        on=["group_name", "sensor_id"],
        how="left"
    )

    # --------------------------------------------------------
    # 5.4 Zeitstempel verarbeiten
    # --------------------------------------------------------

    # Den gespeicherten Zeitpunkt der letzten Messung
    # in einen pandas-Zeitstempel umwandeln.
    #
    # utc=True:
    #     Einheitliche Verwendung der UTC-Zeitzone.
    #
    # errors="coerce":
    #     Nicht interpretierbare Zeitstempel werden NaT
    #     (Not a Time), statt einen Fehler auszulösen.
    status_df["last_seen"] = pd.to_datetime(
        status_df["last_seen"],
        utc=True,
        errors="coerce"
    )

    # Aktuellen Zeitpunkt in UTC bestimmen.
    now = pd.Timestamp.now(tz="UTC")

    # --------------------------------------------------------
    # 5.5 Zeit seit dem letzten Messwert berechnen
    # --------------------------------------------------------

    # Differenz zwischen aktueller Zeit und letzter
    # empfangener Messung berechnen.
    #
    # dt.total_seconds() wandelt die Zeitdifferenz
    # in Sekunden um.
    status_df["seconds_since_last_seen"] = (
        now - status_df["last_seen"]
    ).dt.total_seconds()

    # --------------------------------------------------------
    # 5.6 Tatsächlichen Gerätestatus bestimmen
    # --------------------------------------------------------

    def determine_status(row):
        """
        Bestimmt den angezeigten Gerätestatus anhand von:

            1. Zuletzt gemeldetem MQTT-Status
            2. Zeit seit dem letzten Sensormesswert

        Die Kombination beider Informationen ermöglicht
        eine bessere Einschätzung als die alleinige
        Verwendung der MQTT-Statusmeldung.

        Ein Gerät kann beispielsweise weiterhin aktuelle
        Messwerte senden, obwohl beim Broker noch eine
        ältere Offline-Meldung gespeichert ist.

        Der Status ist deshalb eine Kombination aus
        gemeldetem Zustand und beobachteter Aktivität.
        """

        # Zuletzt über MQTT gemeldeter Gerätestatus.
        mqtt_status = row["status"]

        # Sekunden seit dem letzten empfangenen Messwert.
        seconds = row["seconds_since_last_seen"]

        # ----------------------------------------------------
        # Fall 1: Kein gültiger Zeitstempel vorhanden
        # ----------------------------------------------------

        if pd.isna(seconds):
            return "Unbekannt"

        # ----------------------------------------------------
        # Fall 2: Keine aktuellen Messwerte vorhanden
        # ----------------------------------------------------

        # Wenn länger als OFFLINE_TIMEOUT kein Messwert
        # empfangen wurde, ist die Sensoraktivität veraltet.
        if seconds > OFFLINE_TIMEOUT:

            # Wenn zusätzlich eine Offline-Meldung
            # vorliegt, wird das Gerät als offline angezeigt.
            if mqtt_status == "offline":
                return "Offline"

            # Ohne bestätigten Offline-Status lässt sich
            # nur feststellen, dass aktuelle Daten fehlen.
            return "Keine aktuellen Messwerte"

        # ----------------------------------------------------
        # Fall 3: Aktuelle Messwerte vorhanden
        # ----------------------------------------------------

        # Obwohl neue Daten empfangen werden, wurde
        # ein Sensorfehler über MQTT gemeldet.
        if mqtt_status == "error":
            return "Aktiv – Sensorfehler gemeldet"

        # Das Gerät sendet aktuelle Messwerte,
        # obwohl der letzte MQTT-Status offline lautet.
        #
        # Mögliche Ursache ist eine veraltete oder
        # widersprüchliche Statusmeldung.
        if mqtt_status == "offline":
            return "Aktiv – MQTT-Status veraltet oder widersprüchlich"

        # Aktuelle Messwerte und positiver MQTT-Status.
        if mqtt_status == "ok":
            return "Online / OK"

        # Aktuelle Messwerte vorhanden, aber kein
        # bekannter bzw. gültiger MQTT-Status.
        return "Aktiv – Status unbekannt"

    # --------------------------------------------------------
    # 5.7 Status für alle Geräte berechnen
    # --------------------------------------------------------

    # Die Funktion determine_status wird auf
    # jede Zeile des DataFrames angewendet.
    #
    # axis=1:
    #     Verarbeitung erfolgt zeilenweise.
    #
    # Das Ergebnis wird in einer neuen Spalte gespeichert.
    status_df["Status"] = status_df.apply(
        determine_status,
        axis=1
    )

    # --------------------------------------------------------
    # 5.8 MQTT-Gerätestatus anzeigen
    # --------------------------------------------------------

    # Die wichtigsten Informationen werden in einer
    # übersichtlichen Tabelle dargestellt.
    #
    # column_config ermöglicht benutzerfreundliche
    # Spaltennamen und Zahlenformate.
    st.dataframe(
        status_df[[
            "group_name",
            "sensor_id",
            "Status",
            "seconds_since_last_seen",
            "last_seen"
        ]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "group_name": "Gruppe",
            "sensor_id": "Gerät",
            "seconds_since_last_seen":
                st.column_config.NumberColumn(
                    "Letzter Kontakt vor (s)",
                    format="%.0f"
                ),
            "last_seen": "Letzter Kontakt"
        }
    )

except sqlite3.Error as error:
    # Falls die Statusdaten nicht ausgelesen werden können,
    # wird eine Warnung angezeigt.
    #
    # Das übrige Dashboard kann weiterhin verwendet werden.
    st.warning(
        f"Statusdaten konnten nicht geladen werden: {error}"
    )


# ============================================================
# 6. SENSORÜBERSICHT
# ============================================================

st.header("Sensorübersicht")

# Alle automatisch erkannten Sensoren aus
# der SQLite-Datenbank laden.
try:
    sensors = load_sensors()

except sqlite3.Error as error:
    # Bei einem Datenbankfehler wird die Ausführung
    # abgebrochen, da die Sensorinformationen für
    # die weiteren Auswahlelemente benötigt werden.
    st.error(f"Datenbankfehler: {error}")
    st.stop()

# Prüfen, ob bereits Sensoren registriert wurden.
#
# Ohne Sensoren können weder Geräte ausgewählt
# noch Messwerte analysiert werden.
if sensors.empty:
    st.warning("Noch keine Sensoren registriert.")
    st.stop()


# ============================================================
# 7. ANZAHL DER SENSOREN UND GERÄTE
# ============================================================

# Zwei nebeneinanderliegende Spalten erzeugen,
# um die wichtigsten Kennzahlen anzuzeigen.
col1, col2 = st.columns(2)

# Anzahl der registrierten Messkanäle.
#
# Ein Gerät mit Temperatur- und Feuchtigkeitssensor
# besitzt beispielsweise zwei Messkanäle.
col1.metric(
    "Erkannte Messkanäle",
    len(sensors)
)

# Anzahl der unterschiedlichen Geräte.
#
# drop_duplicates() entfernt doppelte Kombinationen
# aus group_name und sensor_id.
#
# Dadurch wird ein Gerät mit mehreren Messkanälen
# trotzdem nur einmal gezählt.
col2.metric(
    "Erkannte Geräte",
    sensors[
        ["group_name", "sensor_id"]
    ].drop_duplicates().shape[0]
)


# ============================================================
# 8. ZEITSTEMPEL DER SENSOREN VERARBEITEN
# ============================================================

# Letzten Empfangszeitpunkt jedes Sensors
# in einen UTC-Zeitstempel umwandeln.
sensors["last_seen"] = pd.to_datetime(
    sensors["last_seen"],
    utc=True,
    errors="coerce"
)

# Zeitpunkt der ersten Registrierung
# ebenfalls in UTC umwandeln.
sensors["first_seen"] = pd.to_datetime(
    sensors["first_seen"],
    utc=True,
    errors="coerce"
)

# Aktuellen UTC-Zeitpunkt bestimmen.
now = pd.Timestamp.now(tz="UTC")

# Berechnen, wie viele Sekunden seit der letzten
# Messung jedes Sensors vergangen sind.
#
# Damit kann die Aktivität einzelner Messkanäle
# unabhängig vom gesamten Gerät beurteilt werden.
sensors["seconds_since_last_seen"] = (
    now - sensors["last_seen"]
).dt.total_seconds()


# ============================================================
# 9. TABELLE ALLER ERKANNTEN SENSOREN ANZEIGEN
# ============================================================

# Vollständige Sensorübersicht darstellen.
#
# Enthalten sind unter anderem:
#   - MQTT-Gruppe
#   - Gerätekennung
#   - Sensortyp
#   - Einheit
#   - Erster Empfang
#   - Letzter Empfang
#   - Zeit seit dem letzten Messwert
st.dataframe(
    sensors,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# 10. SENSOR FÜR DIE ANALYSE AUSWÄHLEN
# ============================================================

st.header("Messwerte analysieren")

# ------------------------------------------------------------
# 10.1 MQTT-Gruppe auswählen
# ------------------------------------------------------------

# Alle vorhandenen Gruppennamen auslesen
# und alphabetisch sortieren.
groups = sorted(
    sensors["group_name"].unique()
)

# Dropdown-Menü zur Auswahl der gewünschten Gruppe.
selected_group = st.selectbox(
    "Gruppe auswählen",
    groups
)

# Sensoren auf die ausgewählte Gruppe einschränken.
group_sensors = sensors[
    sensors["group_name"] == selected_group
]

# ------------------------------------------------------------
# 10.2 Gerät auswählen
# ------------------------------------------------------------

# Alle Geräte innerhalb der ausgewählten Gruppe ermitteln.
device_ids = sorted(
    group_sensors["sensor_id"].unique()
)

# Dropdown-Menü zur Auswahl des Geräts.
selected_device = st.selectbox(
    "Gerät auswählen",
    device_ids
)

# Sensoren auf das ausgewählte Gerät einschränken.
device_sensors = group_sensors[
    group_sensors["sensor_id"] == selected_device
]

# ------------------------------------------------------------
# 10.3 Messgröße auswählen
# ------------------------------------------------------------

# Verfügbare Messgrößen des ausgewählten Geräts ermitteln.
#
# Beispiele:
#   temperature
#   humidity
sensor_types = sorted(
    device_sensors["sensor_type"].unique()
)

# Dropdown-Menü zur Auswahl der Messgröße.
selected_type = st.selectbox(
    "Messgröße auswählen",
    sensor_types
)


# ============================================================
# 11. MESSWERTE AUS DER DATENBANK LADEN
# ============================================================

# Messwerte des ausgewählten Geräts und Sensortyps
# aus der SQLite-Datenbank laden.
df = load_measurements(
    selected_device,
    selected_type
)

# Prüfen, ob passende Messwerte vorhanden sind.
if df.empty:
    st.warning("Keine Messwerte vorhanden.")
    st.stop()

# ------------------------------------------------------------
# 11.1 Zeitstempel konvertieren
# ------------------------------------------------------------

# Zeitstempel in pandas-Datetime-Objekte umwandeln.
#
# utc=True stellt sicher, dass alle Zeitangaben
# mit derselben Zeitzone verarbeitet werden.
df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    utc=True,
    errors="coerce"
)

# ------------------------------------------------------------
# 11.2 Messwerte in Zahlen umwandeln
# ------------------------------------------------------------

# Sicherstellen, dass die Messwerte numerisch vorliegen.
#
# Fehlerhafte oder nicht interpretierbare Werte
# werden durch NaN ersetzt.
df["value"] = pd.to_numeric(
    df["value"],
    errors="coerce"
)

# ------------------------------------------------------------
# 11.3 Ungültige Datensätze entfernen
# ------------------------------------------------------------

# Zeilen ohne gültigen Zeitstempel oder Messwert
# aus dem DataFrame entfernen.
#
# Dadurch werden spätere Berechnungen und
# Diagramme nicht durch ungültige Daten beeinflusst.
df = df.dropna(
    subset=["timestamp", "value"]
)

# Prüfen, ob nach der Bereinigung noch
# gültige Messwerte vorhanden sind.
if df.empty:
    st.warning("Keine gültigen Messwerte vorhanden.")
    st.stop()

# ------------------------------------------------------------
# 11.4 Messwerte chronologisch sortieren
# ------------------------------------------------------------

# Aufsteigend nach Zeitstempel sortieren.
#
# Dadurch stehen die Messwerte in zeitlicher Reihenfolge
# für die statistische Auswertung und das Diagramm bereit.
df = df.sort_values("timestamp")

# Einheit des letzten Datensatzes verwenden.
#
# Beispiele:
#   °C für Temperatur
#   % für Luftfeuchtigkeit
unit = df["unit"].iloc[-1]


# ============================================================
# 12. AKTUELLE MESSWERTE UND STATISTIKEN
# ============================================================

st.subheader("Statistiken")

# Vier Spalten für die wichtigsten statistischen
# Kennzahlen der ausgewählten Messgröße erstellen.
col1, col2, col3, col4 = st.columns(4)

# ------------------------------------------------------------
# 12.1 Letzter Messwert
# ------------------------------------------------------------

# iloc[-1] liefert den letzten Datensatz
# aus dem chronologisch sortierten DataFrame.
#
# :.1f formatiert den Wert auf eine Nachkommastelle.
col1.metric(
    "Letzter Wert",
    f"{df['value'].iloc[-1]:.1f} {unit}"
)

# ------------------------------------------------------------
# 12.2 Durchschnitt
# ------------------------------------------------------------

# Arithmetischen Mittelwert über alle geladenen
# Messwerte der ausgewählten Messgröße berechnen.
col2.metric(
    "Durchschnitt",
    f"{df['value'].mean():.1f} {unit}"
)

# ------------------------------------------------------------
# 12.3 Minimum
# ------------------------------------------------------------

# Kleinsten gespeicherten Messwert bestimmen.
col3.metric(
    "Minimum",
    f"{df['value'].min():.1f} {unit}"
)

# ------------------------------------------------------------
# 12.4 Maximum
# ------------------------------------------------------------

# Größten gespeicherten Messwert bestimmen.
col4.metric(
    "Maximum",
    f"{df['value'].max():.1f} {unit}"
)


# ============================================================
# 13. ZEITVERLAUF DER MESSWERTE
# ============================================================

st.subheader("Zeitverlauf")

# Zeitstempel als DataFrame-Index verwenden.
#
# Dadurch erkennt Streamlit, dass die Messwerte
# entlang einer Zeitachse dargestellt werden sollen.
#
# Es wird ausschließlich die Spalte "value" geplottet.
chart_data = df.set_index("timestamp")[["value"]]

# Interaktives Liniendiagramm erstellen.
#
# X-Achse:
#     Zeitstempel der Messungen.
#
# Y-Achse:
#     Gemessener Sensorwert mit physikalischer Einheit.
#
# Durch die automatische Aktualisierung werden
# neu gespeicherte Messwerte regelmäßig nachgeladen.
st.line_chart(
    chart_data,
    y="value",
    x_label="Zeit",
    y_label=f"{selected_type} ({unit})"
)


# ============================================================
# 14. GESPEICHERTE MESSWERTE ALS TABELLE
# ============================================================

st.subheader("Gespeicherte Messwerte")

# Alle geladenen Messwerte tabellarisch anzeigen.
#
# Die neuesten Messwerte stehen oben.
#
# ascending=False:
#     Absteigende Sortierung nach Zeitstempel.
#
# hide_index=True:
#     pandas-Zeilenindex nicht anzeigen.
st.dataframe(
    df.sort_values(
        "timestamp",
        ascending=False
    ),
    use_container_width=True,
    hide_index=True
)


# ============================================================
# 15. FOOTER UND ZEITSTEMPEL
# ============================================================

# Am Ende des Dashboards die verwendete Datenquelle
# und den aktuellen UTC-Zeitpunkt anzeigen.
#
# Der Zeitstempel wird bei jeder Aktualisierung
# des Streamlit-Skripts neu erzeugt.
#
# Damit ist erkennbar, wann die Dashboard-Seite
# zuletzt ausgeführt wurde.
st.caption(
    "Datenquelle: SQLite | "
    "Stand: " + datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )
)
