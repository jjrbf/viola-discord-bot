import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from transformers import MarianMTModel, MarianTokenizer
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

# Ensure consistent language detection results
DetectorFactory.seed = 0

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
default_languages = {}  # Store default target languages for each user

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
async def setlanguage(ctx, target_lang: str):
    """Set the default target language for translations."""
    user_id = ctx.author.id
    default_languages[user_id] = target_lang
    await ctx.send(f"Default target language set to: {target_lang}")

@bot.command()
async def translate(ctx, source_lang: str = None, target_lang: str = None, *, text: str = None):
    """Translate a message with optional source and target languages."""
    user_id = ctx.author.id

    # Use user's default target language if no target language is provided
    if target_lang is None:
        target_lang = default_languages.get(user_id)
        if target_lang is None:
            await ctx.send("Please set a default target language using `!setlanguage <target_lang>` or specify a target language in the command.")
            return

    # If the command is a reply, get the original message
    if ctx.message.reference is not None:
        original_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        text = original_message.content  # Use the original message's content

    # If text is still None, inform the user
    if not text:
        await ctx.send("Please provide text to translate or reply to a message.")
        return

    try:
        # If no source language is provided, detect it
        if source_lang is None:
            source_lang = detect(text)
            await ctx.send(f"Detected source language: {source_lang}")

        # If the detected source language is the same as the target language
        if source_lang == target_lang:
            await ctx.send("The text is already in the target language.")
            return

        # Load the appropriate model
        if not load_model_and_tokenizer(source_lang, target_lang):
            await ctx.send(f"Translation model for {source_lang} -> {target_lang} could not be loaded.")
            return

        # Tokenize and translate
        inputs = current_tokenizer(text, return_tensors="pt", padding=True)
        translated = current_model.generate(**inputs)
        translation = current_tokenizer.decode(translated[0], skip_special_tokens=True)

        await ctx.send(f"Translation ({source_lang} -> {target_lang}): {translation}")
    except LangDetectException:
        await ctx.send("Could not detect the language of the input text. Please try again.")
    except Exception as e:
        await ctx.send(f"Error: {e}")

# Run the bot
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Failed to run bot: {e}")
