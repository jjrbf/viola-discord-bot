import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from transformers import MarianMTModel, MarianTokenizer

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Set up bot
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")

@bot.command()
async def translate(ctx, *, text: str):
    try:
        model_name = "Helsinki-NLP/opus-mt-en-de"
        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)

        # Tokenize and translate
        inputs = tokenizer(text, return_tensors="pt", padding=True)
        translated = model.generate(**inputs)
        translation = tokenizer.decode(translated[0], skip_special_tokens=True)

        await ctx.send(f"Translation: {translation}")
    except Exception as e:
        await ctx.send(f"Error: {e}")

# Run the bot
bot.run(TOKEN)
