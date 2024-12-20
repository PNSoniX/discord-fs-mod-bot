import discord
from discord.ext import commands, tasks
import aiohttp
from bs4 import BeautifulSoup
import os
import json
from urllib.parse import urljoin
import hashlib

# Setze die Channel-ID aus Umgebungsvariablen (oder direkt im Code, falls nötig)
CHANNEL_ID = int(os.getenv("CHANNEL_ID", 0))  # Wenn CHANNEL_ID nicht gesetzt, wird 0 verwendet

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Hier wird die Mod-Datenbank als JSON-Datei gespeichert
DATABASE_FILE = "mods_database.json"

# Lade die gespeicherten Mods aus der Datenbank, falls vorhanden
def load_mods_database():
    if os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "r") as file:
            return json.load(file)
    return {}

# Speichere die Mods in die Datenbank
def save_mods_database(mods):
    with open(DATABASE_FILE, "w") as file:
        json.dump(mods, file)

# Berechne einen einzigartigen Hash für jede Mod, basierend auf dem Link
def generate_mod_hash(mod_link):
    return hashlib.md5(mod_link.encode()).hexdigest()

# Bestimme die maximale Seitenzahl
async def get_total_pages():
    url = "https://www.farming-simulator.com/mods.php?title=fs2025&filter=latest&page=1"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                return 1  # Wenn die Seite nicht verfügbar ist, gehe von einer Seite aus

            text = await response.text()
            soup = BeautifulSoup(text, 'html.parser')

            # Suche nach dem Hinweis auf die Anzahl der Seiten
            pagination = soup.select_one('.pagination')  # Navigationsbereich für Seiten
            if pagination:
                # Finde die letzte Seitenzahl in der Paginierung
                pages = pagination.find_all('a')
                last_page = pages[-2].get_text()  # Die letzte Zahl ist die maximale Seitenzahl
                return int(last_page)

            return 1  # Falls keine Paginierung gefunden wurde, gehe von 1 Seite aus

# Scrape die Mods einer bestimmten Seite
async def scrape_mods(page_num=1):
    url = f"https://www.farming-simulator.com/mods.php?title=fs2025&filter=latest&page={page_num}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                return []

            text = await response.text()
            soup = BeautifulSoup(text, 'html.parser')

            mods = []

            # Suche nach Mod-Elementen auf der Webseite
            for mod in soup.select(".mod-item"):
                name = mod.select_one(".mod-item__content h4").get_text(strip=True)  # Mod-Name aus h4
                relative_image_url = mod.select_one(".mod-item__img img")["src"]  # Mod-Bild (relativ)
                image_url = urljoin(url, relative_image_url)  # Kombiniert die Basis-URL mit der relativen URL
                creator = mod.select_one(".mod-item__content p span").get_text(strip=True) if mod.select_one(".mod-item__content p span") else "Unbekannt"
                mod_link = urljoin(url, mod.select_one("a")["href"])  # Link zum ModHub
                
                # Überprüfe, ob das "NEW!" oder "UPDATE!" Label vorhanden ist
                label = ""
                if mod.select_one(".mod-label-new"):
                    label = "NEW!"
                elif mod.select_one(".mod-label-update"):
                    label = "UPDATE!"

                mods.append({
                    "name": name,
                    "image": image_url,
                    "creator": creator,
                    "link": mod_link,
                    "label": label  # Füge das Label hinzu
                })

            print(f"Gefundene Mods auf Seite {page_num}: {len(mods)}")
            return mods

# Scrape die Mod-Details von der Detailseite des Mods
async def scrape_mod_details(mod_url):
    async with aiohttp.ClientSession() as session:
        async with session.get(mod_url) as response:
            if response.status != 200:
                return None  # Rückgabe von None, wenn ein Fehler auftritt

            text = await response.text()
            soup = BeautifulSoup(text, 'html.parser')

            # Suche nach den relevanten Informationen
            author = soup.select_one("div.table-row:contains('Autor') .table-cell a")
            version = soup.select_one("div.table-row:contains('Version') .table-cell")
            release_date = soup.select_one("div.table-row:contains('Veröffentlichung') .table-cell")

            # Extrahiere die Daten, wenn sie vorhanden sind
            author_name = author.get_text(strip=True) if author else "Unbekannt"
            version_number = version.get_text(strip=True) if version else "Unbekannt"
            release_date_text = release_date.get_text(strip=True) if release_date else "Unbekannt"

            # Rückgabe als Dictionary
            return {
                "author": author_name,
                "version": version_number,
                "release_date": release_date_text
            }

# Hauptschleife, die regelmäßig nach neuen Mods sucht
@tasks.loop(minutes=30)  # Alle 30 Minuten nach neuen Mods suchen
async def check_mods():
    mods_database = load_mods_database()
    channel = bot.get_channel(CHANNEL_ID)

    if channel is None:
        print("Fehler: Kanal konnte nicht gefunden werden!")
        return

    # Bestimme die maximale Seitenzahl dynamisch
    total_pages = await get_total_pages()
    print(f"Maximale Seitenzahl: {total_pages}")

    mods = []
    for page_num in range(1, total_pages + 1):
        page_mods = await scrape_mods(page_num)
        if not page_mods:
            break  # Keine weiteren Mods auf dieser Seite, also breche ab
        mods.extend(page_mods)

    new_mods = []
    
    # Filtere Mods, die entweder "UPDATE!"-Label haben oder noch nicht bekannt sind
    for mod in mods:
        mod_hash = generate_mod_hash(mod["link"])

        # Wenn das Label "UPDATE!" ist, überprüfen wir die Versionsnummer
        if mod["label"] == "UPDATE!":
            mod_details = await scrape_mod_details(mod["link"])
            if mod_details:
                # Wenn der Mod bereits bekannt ist, vergleichen wir die Version
                if mod_hash in mods_database:
                    stored_version = mods_database[mod_hash].get("version", "")
                    if stored_version != mod_details["version"]:
                        new_mods.append({**mod, **mod_details})  # Füge die Mod-Daten und Details hinzu
                else:
                    new_mods.append({**mod, **mod_details})  # Wenn die Mod noch nicht in der DB ist, hinzufügen
        elif mod_hash not in mods_database:
            new_mods.append(mod)  # Wenn der Mod noch nicht bekannt ist, füge ihn hinzu

    print(f"Neue Mods gefunden: {len(new_mods)}")  # Ausgabe, um zu sehen, ob neue Mods gefunden wurden

    # Wenn neue Mods gefunden wurden, sende sie in den Discord-Kanal
    for mod in new_mods:
        creator = mod.get("creator", "Unbekannt")
        version = mod.get("version", "Unbekannt")
        release_date = mod.get("release_date", "Unbekannt")

        embed = discord.Embed(
            title=f"{mod['label']} - {mod['name']}",
            description=f"Ersteller: {creator}\nVersion: {version}\nVeröffentlichung: {release_date}",
            color=discord.Color.blue()
        )
        embed.set_image(url=mod["image"])
        embed.add_field(name="Mod-Link", value=mod["link"], inline=False)
        
        # Poste die Mod im Discord-Kanal
        await channel.send(embed=embed)

        # Speichere den Mod in der Datenbank
        mods_database[generate_mod_hash(mod["link"])] = {
            "name": mod["name"],
            "creator": creator,
            "version": version,
            "release_date": release_date
        }

    save_mods_database(mods_database)  # Speichere die Datenbank

@bot.event
async def on_ready():
    print(f"Bot ist eingeloggt als {bot.user}")
    check_mods.start()  # Starte den Bot und beginne mit dem Scraping

bot.run("DEIN_BOT_TOKEN")  # Ersetze DEIN_BOT_TOKEN mit deinem tatsächlichen Token
