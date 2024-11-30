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
async def translate(ctx, source_lang: str, target_lang: str, *, text: str):
    try:
        # Construct model name based on source and target languages
        model_name = f"Helsinki-NLP/opus-mt-{source_lang}-{target_lang}"
        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)

        # Tokenize the input text
        inputs = tokenizer(text, return_tensors="pt", padding=True)
        
        # Generate translation
        translated = model.generate(**inputs)
        translation = tokenizer.decode(translated[0], skip_special_tokens=True)

        await ctx.send(f"Translated ({source_lang} -> {target_lang}): {translation}")
    except Exception as e:
        await ctx.send(f"Error: {e}. Please make sure the language pair is supported.")

# Run the bot
bot.run(TOKEN)
