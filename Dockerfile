FROM python:3.11-slim

# Setze das Arbeitsverzeichnis
WORKDIR /app

# Kopiere die requirements.txt zuerst, um die Layer-Caching zu nutzen
COPY requirements.txt .

# Installiere die Abhängigkeiten
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere den Bot-Code in den Container
COPY bot.py .

# Setze den Befehl zum Starten des Bots
CMD ["python", "bot.py"]
