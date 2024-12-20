import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

last_known_mods = []

def scrape_mods():
    url = "https://www.farming-simulator.com/mods.php"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    mods = []
    for mod in soup.select(".mod-list-item"):
        name = mod.select_one(".mod-title").get_text(strip=True)
        image = mod.select_one("img")["src"]
        version = mod.select_one(".mod-version").get_text(strip=True)
        mods.append({"name": name, "image": image, "version": version})
    return mods

@tasks.loop(minutes=30)
async def check_mods():
    global last_known_mods
    channel = bot.get_channel(CHANNEL_ID)  # Ersetze CHANNEL_ID
    mods = scrape_mods()
    new_mods = [mod for mod in mods if mod not in last_known_mods]

    for mod in new_mods:
        embed = discord.Embed(title=mod["name"], description=f"Version: {mod['version']}", color=0x00ff00)
        embed.set_image(url=mod["image"])
        await channel.send(embed=embed)

    if new_mods:
        last_known_mods = mods

@bot.event
async def on_ready():
    print(f"Bot ist online als {bot.user}!")
    check_mods.start()

bot.run("DEIN_BOT_TOKEN")
