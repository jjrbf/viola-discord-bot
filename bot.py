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

# Load model and tokenizer for the specified language pair
current_model = None
current_tokenizer = None
default_languages = {}  # Store default languages for each user

@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")

def load_model_and_tokenizer(source_lang, target_lang):
    """Load the model and tokenizer for the specified language pair."""
    global current_model, current_tokenizer
    model_name = f"Helsinki-NLP/opus-mt-{source_lang}-{target_lang}"
    try:
        current_tokenizer = MarianTokenizer.from_pretrained(model_name)
        current_model = MarianMTModel.from_pretrained(model_name)
        print(f"Loaded model for {source_lang} to {target_lang}.")
        return True
    except Exception as e:
        print(f"Error loading model {model_name}: {e}")
        return False

@bot.command()
async def setlanguagepair(ctx, source_lang: str, target_lang: str):
    """Set the default language pair for translations."""
    user_id = ctx.author.id

    # Load model and tokenizer for the specified language pair
    if load_model_and_tokenizer(source_lang, target_lang):
        default_languages[user_id] = (source_lang, target_lang)
        await ctx.send(f"Default language pair set to: {source_lang} -> {target_lang}")
    else:
        await ctx.send("Failed to load model for the specified language pair.")

@bot.command()
async def translate(ctx, *, text: str = None):
    """Translate a message using the default language pair or user-specified languages."""
    user_id = ctx.author.id
    source_lang, target_lang = default_languages.get(user_id, (None, None))

    # If no default language is set, inform the user
    if source_lang is None or target_lang is None:
        await ctx.send("Please set a default language pair using `!setlanguagepair <source_lang> <target_lang>`.")
        return

    # If the command is a reply, get the original message
    if ctx.message.reference is not None:
        original_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        text = original_message.content  # Use the original message's content

    # If text is still None, inform the user
    if text is None:
        await ctx.send("Please provide text to translate or reply to a message.")
        return

    try:
        # If the model is not loaded, inform the user
        if current_model is None or current_tokenizer is None:
            await ctx.send("Translation model not loaded. Please set the language pair first.")
            return

        # Tokenize and translate
        inputs = current_tokenizer(text, return_tensors="pt", padding=True)
        translated = current_model.generate(**inputs)
        translation = current_tokenizer.decode(translated[0], skip_special_tokens=True)

        await ctx.send(f"Translation ({source_lang} -> {target_lang}): {translation}")
    except Exception as e:
        await ctx.send(f"Error: {e}")

# Run the bot
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Failed to run bot: {e}")
