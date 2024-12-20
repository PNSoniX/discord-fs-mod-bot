import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup
import os

# Setze die Channel-ID aus Umgebungsvariablen (oder direkt im Code, falls nötig)
CHANNEL_ID = int(os.getenv("CHANNEL_ID", 0))  # Wenn CHANNEL_ID nicht gesetzt, wird 0 verwendet

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

last_known_mods = []

def scrape_mods():
    url = "https://www.farming-simulator.com/mods.php"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    mods = []
    # Suche nach Mod-Elementen auf der Webseite
    for mod in soup.select(".mod-list-item"):
        name = mod.select_one(".mod-title").get_text(strip=True)
        image = mod.select_one("img")["src"]
        version = mod.select_one(".mod-version").get_text(strip=True)
        mods.append({"name": name, "image": image, "version": version})
    return mods

@tasks.loop(minutes=30)  # Alle 30 Minuten nach neuen Mods suchen
async def check_mods():
    global last_known_mods
    channel = bot.get_channel(CHANNEL_ID)
    
    # Scrape Mods von der Website
    mods = scrape_mods()
    new_mods = [mod for mod in mods if mod not in last_known_mods]

    # Wenn neue Mods gefunden wurden, sende sie in den Discord-Kanal
    for mod in new_mods:
        embed = discord.Embed(
            title=mod["name"],
            description=f"Version: {mod['version']}",
            color=0x00ff00
        )
        embed.set_image(url=mod["image"])
        await channel.send(embed=embed)

    if new_mods:
        last_known_mods = mods

@bot.event
async def on_ready():
    print(f"Bot ist online als {bot.user}!")
    check_mods.start()

# Token aus der Umgebungsvariablen oder direkt im Code setzen
bot.run(os.getenv("BOT_TOKEN"))  # Alternativ kannst du hier deinen Token direkt einfügen, z.B. bot.run('DEIN_BOT_TOKEN')
