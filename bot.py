import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from transformers import MarianMTModel, MarianTokenizer
from langdetect import detect, LangDetectException

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Set up bot
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix="!", intents=intents)

# Cache for storing models and tokenizers
model_cache = {}
default_languages = {}
active_translations = {}  # Track active translation modes by channel

def get_model_and_tokenizer(source_lang, target_lang):
    """Retrieve the model and tokenizer from the cache or load them if not cached."""
    global model_cache
    model_key = f"{source_lang}-{target_lang}"

    if model_key in model_cache:
        return model_cache[model_key]

    model_name = f"Helsinki-NLP/opus-mt-{source_lang}-{target_lang}"
    try:
        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)
        model_cache[model_key] = (model, tokenizer)
        print(f"Loaded and cached model for {source_lang} -> {target_lang}.")
        return model, tokenizer
    except Exception as e:
        print(f"Error loading model {model_name}: {e}")
        return None, None

@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")

@bot.command()
async def startlivetranslation(ctx, target_lang: str):
    """Start live translation mode in the current channel."""
    channel_id = ctx.channel.id
    active_translations[channel_id] = target_lang
    await ctx.send(f"Live translation mode activated. Messages will be translated to {target_lang}.")

@bot.command()
async def stoplivetranslation(ctx):
    """Stop live translation mode in the current channel."""
    channel_id = ctx.channel.id
    if channel_id in active_translations:
        del active_translations[channel_id]
        await ctx.send("Live translation mode deactivated.")
    else:
        await ctx.send("Live translation mode is not active in this channel.")

@bot.event
async def on_message(message):
    """Listen for messages and translate them in live translation mode."""
    if message.author == bot.user:
        return

    channel_id = message.channel.id
    if channel_id in active_translations:
        target_lang = active_translations[channel_id]

        try:
            # Detect the source language
            source_lang = detect(message.content)
            if source_lang == target_lang:
                return  # Skip if the source and target languages are the same

            # Get the model and tokenizer
            model, tokenizer = get_model_and_tokenizer(source_lang, target_lang)
            if model is None or tokenizer is None:
                await message.channel.send(f"Translation model for {source_lang} -> {target_lang} could not be loaded.")
                return

            # Translate the message
            inputs = tokenizer(message.content, return_tensors="pt", padding=True)
            translated = model.generate(**inputs)
            translation = tokenizer.decode(translated[0], skip_special_tokens=True)

            # Create a thread with the translation
            thread_title = f"Translation: {source_lang} -> {target_lang}"
            translation_thread = await message.create_thread(name=thread_title)
            await translation_thread.send(f"Translated message: {translation}")
        except LangDetectException:
            await message.channel.send("Could not detect the language of the input text. Skipping.")
        except Exception as e:
            await message.channel.send(f"Error during translation: {e}")

    # Ensure other bot commands are processed
    await bot.process_commands(message)

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

        # Get the model and tokenizer (using the cache)
        model, tokenizer = get_model_and_tokenizer(source_lang, target_lang)
        if model is None or tokenizer is None:
            await ctx.send(f"Translation model for {source_lang} -> {target_lang} could not be loaded.")
            return

        # Tokenize and translate
        inputs = tokenizer(text, return_tensors="pt", padding=True)
        translated = model.generate(**inputs)
        translation = tokenizer.decode(translated[0], skip_special_tokens=True)

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
