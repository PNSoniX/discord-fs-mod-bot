import discord
from discord.ext import commands, tasks
import aiohttp
from bs4 import BeautifulSoup
import os
import json
from urllib.parse import urljoin

# Setze die Channel-ID aus Umgebungsvariablen (oder direkt im Code, falls nötig)
CHANNEL_ID = int(os.getenv("CHANNEL_ID", 0))  # Wenn CHANNEL_ID nicht gesetzt, wird 0 verwendet

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

last_known_mods = {"new": [], "updates": []}  # Struktur für bekannte neue Mods und Updates

# Lade die gespeicherten Mods, falls vorhanden
def load_last_known_mods():
    global last_known_mods
    if os.path.exists("last_known_mods.json"):
        with open("last_known_mods.json", "r") as file:
            last_known_mods = json.load(file)

# Speichere die aktuellen Mods
def save_last_known_mods():
    with open("last_known_mods.json", "w") as file:
        json.dump(last_known_mods, file)

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

# Scrape die Mods einer bestimmten Seite und suche nach "NEW!" oder "UPDATE!" Labels
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

                if label:  # Nur Mods mit den Labels "NEW!" oder "UPDATE!" hinzufügen
                    mods.append({
                        "name": name,
                        "image": image_url,
                        "creator": creator,
                        "link": mod_link,
                        "label": label  # Füge das Label hinzu
                    })

            print(f"Gefundene Mods auf Seite {page_num}: {len(mods)}")
            return mods

# Scrape Details der Mod-Seite
async def scrape_mod_details(mod_link):
    async with aiohttp.ClientSession() as session:
        async with session.get(mod_link) as response:
            if response.status != 200:
                return None

            text = await response.text()
            soup = BeautifulSoup(text, 'html.parser')

            # Beispiel für zusätzliche Mod-Daten:
            description = soup.select_one(".mod-description")  # Beispiel für Beschreibung
            mod_description = description.get_text(strip=True) if description else "Keine Beschreibung verfügbar"
            version = soup.select_one(".mod-version")  # Beispiel für Version
            mod_version = version.get_text(strip=True) if version else "Keine Version verfügbar"

            return {
                "description": mod_description,
                "version": mod_version
            }

# Hauptschleife, die regelmäßig nach neuen Mods sucht
@tasks.loop(minutes=30)  # Alle 30 Minuten nach neuen Mods suchen
async def check_mods():
    global last_known_mods
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
        mod_details = await scrape_mod_details(mod["link"])  # Detaillierte Mod-Info scrapen
        if mod_details:
            mod["description"] = mod_details["description"]
            mod["version"] = mod_details["version"]
        
        # Vergleiche Mods mit den bekannten Mods in last_known_mods
        mod_data = {"name": mod["name"], "version": mod["version"]}
        
        if mod["label"] == "UPDATE!" and mod_data not in last_known_mods["updates"]:
            # Füge Updates nur einmal hinzu, wenn Name und Version sich ändern
            new_mods.append(mod)
            last_known_mods["updates"].append(mod_data)
        
        elif mod["label"] == "NEW!" and mod_data not in last_known_mods["new"]:
            # Füge neue Mods nur hinzu, wenn Name und Version sich ändern
            new_mods.append(mod)
            last_known_mods["new"].append(mod_data)

    print(f"Neue Mods und Updates gefunden: {len(new_mods)}")

    # Wenn neue Mods oder Updates gefunden wurden, sende sie in den Discord-Kanal
    for mod in new_mods:
        embed = discord.Embed(
            title=mod["label"],  # Der Titel ist jetzt das Label ("NEW!" oder "UPDATE!")
            color=0x00ff00
        )

        # Name des Mods als fett formatierter Text im Beschreibungstext
        embed.description = f"**{mod['name']}**"  # Der Name des Mods wird fett dargestellt

        # Ersteller des Mods als Feld hinzufügen
        embed.add_field(name="Ersteller", value=mod['creator'], inline=False)

        # Beschreibung und Version des Mods hinzufügen (aus Detailseite)
        embed.add_field(name="Beschreibung", value=mod['description'], inline=False)
        embed.add_field(name="Version", value=mod['version'], inline=False)

        # ModHub-Link als Feld hinzufügen
        embed.add_field(name="Mehr Infos", value=f"[ModHub Link]({mod['link']})", inline=False)

        # Setze das Bild-URL im Embed, wenn vorhanden
        if mod["image"]:
            embed.set_image(url=mod["image"])

        await channel.send(embed=embed)

    if new_mods:
        save_last_known_mods()  # Speichere die Liste der bekannten Mods und Updates

# Event, das ausgeführt wird, wenn der Bot online ist
@bot.event
async def on_ready():
    print(f"Bot ist online als {bot.user}!")
    load_last_known_mods()  # Lade die gespeicherten Mods
    check_mods.start()

bot.run(os.getenv("BOT_TOKEN"))
