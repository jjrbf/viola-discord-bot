import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands
from transformers import MarianMTModel, MarianTokenizer
from langdetect import detect, LangDetectException

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Set up bot
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix="!", intents=intents)

# Caching for translation models
model_cache = {}

# Active live translation settings
active_translations = {}
error_threads = {}

# Default target languages for users
default_languages = {}

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
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# Slash command: Set language
@bot.tree.command(name="setlanguage", description="Set your default target language.")
async def setlanguage(interaction: discord.Interaction, target_lang: str):
    user_id = interaction.user.id
    default_languages[user_id] = target_lang
    await interaction.response.send_message(
        f"Default target language set to: {target_lang}", ephemeral=True
    )

@bot.tree.command(name="translate", description="Translate text with optional source and target languages.")
async def translate(interaction: discord.Interaction, text: str, source_lang: str = None, target_lang: str = None):
    """vioLa will translate a message for you."""
    user_id = interaction.user.id

    # Defer the response to allow more processing time
    await interaction.response.defer(ephemeral=True)

    # Use user's default target language if no target language is provided
    if target_lang is None:
        target_lang = default_languages.get(user_id)
        if target_lang is None:
            await interaction.followup.send(
                "Please set a default target language using `/setlanguage <target_lang>` or specify a target language."
            )
            return

    try:
        # If no source language is provided, detect it
        if source_lang is None:
            source_lang = detect(text)

        # If the detected source language is the same as the target language
        if source_lang == target_lang:
            await interaction.followup.send(
                "The text is already in the target language."
            )
            return

        # Get the model and tokenizer (using the cache)
        model, tokenizer = get_model_and_tokenizer(source_lang, target_lang)
        if model is None or tokenizer is None:
            await interaction.followup.send(
                f"Translation model for {source_lang} -> {target_lang} could not be loaded."
            )
            return

        # Tokenize and translate
        inputs = tokenizer(text, return_tensors="pt", padding=True)
        translated = model.generate(**inputs)
        translation = tokenizer.decode(translated[0], skip_special_tokens=True)

        await interaction.followup.send(
            f"Translation ({source_lang} -> {target_lang}): {translation}"
        )
    except LangDetectException:
        await interaction.followup.send(
            "Could not detect the language of the input text. Please try again."
        )
    except Exception as e:
        await interaction.followup.send(
            f"Error: {e}"
        )

# Slash command: /languagecodes
@bot.tree.command(name="languagecodes", description="View all supported language codes and their corresponding languages.")
async def languagecodes(interaction: discord.Interaction):
    formatted_codes = format_language_codes()
    await interaction.response.send_message(
        f"Supported Language Codes:\n{formatted_codes}",
        ephemeral=True
    )

# Command: Start live translation
@bot.command()
async def startlivetranslation(ctx, target_lang: str):
    """Start live translation mode in the current channel."""
    channel_id = ctx.channel.id
    active_translations[channel_id] = target_lang
    await ctx.send(f"Live translation mode activated. Messages will be translated to {target_lang}.")

# Command: Stop live translation
@bot.command()
async def stoplivetranslation(ctx):
    """Stop live translation mode in the current channel."""
    channel_id = ctx.channel.id
    if channel_id in active_translations:
        del active_translations[channel_id]
        await ctx.send("Live translation mode deactivated.")
    else:
        await ctx.send("Live translation mode is not active in this channel.")

# Event: Process live translations
@bot.event
async def on_message(message):
    """Listen for messages and translate them in live translation mode."""
    # Skip if the message is from the bot
    if message.author == bot.user:
        return

    # Process bot commands first
    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    # Check if the message is in a thread
    if isinstance(message.channel, discord.Thread):
        # Check if the thread's name starts with "Translation"
        if message.channel.name.startswith("Translation:") or message.channel.name.startswith("Error: Translation model for"):
            # If the message is a language code, retry translation
            if len(message.content) == 2:  # Language codes are typically 2 characters
                retry_language_code = message.content.lower()
                parent_message_id = message.channel.id
                try:
                    # Fetch the first message in the thread
                    async for thread_message in message.channel.history(limit=2, oldest_first=True):
                        # This should be the first message in the thread
                        if "Translating: " in thread_message.content:
                            first_message = thread_message.content.split("Translating: ")[1]
                    # Fetch the second message in the thread
                    async for thread_message in message.channel.history(limit=3, oldest_first=True):
                        # Check if the message contains an error message for translation failure
                        if "Translation model for" in thread_message.content:
                            # Extract the target language from the error message (e.g., "Translation model for so -> en")
                            target_lang = thread_message.content.split("->")[-1].strip().split()[0]
                            
                            # Proceed with retrying the translation with the extracted target language
                            await retry_translation(
                                thread=message.channel,
                                original_message=first_message,  # This is the first message in the thread
                                retry_language_code=retry_language_code,
                                target_lang=target_lang,  # Set the correct target language from the error
                            )
                            return
                except Exception as e:
                    await message.channel.send(f"Error handling retry: {e}")
                    return

    # Check if live translation is active for the channel
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
                error_msg = f"Translation model for {source_lang} -> {target_lang} could not be loaded."
                error_thread = await message.create_thread(name=f"Error: {error_msg}")
                await error_thread.send(f"Translating: {message.content}")
                await error_thread.send(f"{error_msg}\n\nReply to this message with a new source language (e.g., 'en').")
                error_threads[message.id] = error_thread
                return

            # Translate the message
            inputs = tokenizer(message.content, return_tensors="pt", padding=True)
            translated = model.generate(**inputs)
            translation = tokenizer.decode(translated[0], skip_special_tokens=True)

            # Create a thread for the translation
            thread_title = f"Translation: {source_lang} -> {target_lang}"
            translation_thread = await message.create_thread(name=thread_title, auto_archive_duration=60)

            # Ensure the bot is explicitly added as a thread member
            await translation_thread.add_user(bot.user)

            # Iterate over the list of thread members and remove all non-bot users
            for member in translation_thread.members:
                await message.channel.send(f"Member: {member}")
                if member.id != bot.user.id:  # Skip the bot itself
                    try:
                        await translation_thread.remove_user(member)
                    except Exception as e:
                        print(f"Failed to remove {member.name} from thread: {e}")

            await translation_thread.send(f"Translated message: {translation}")

        except LangDetectException:
            await message.channel.send("Could not detect the language of the input text. Skipping.")
        except Exception as e:
            await message.channel.send(f"Error during translation: {e}")

    # Ensure other bot commands are processed
    await bot.process_commands(message)

# Retry translation in error threads
async def retry_translation(thread, original_message, retry_language_code, target_lang):
    """
    Retry translation with a new source language code.
    """
    try:
        text_to_translate = original_message
        await thread.send(f"Text to translate: {original_message}")
        if not text_to_translate:
            await thread.send("Could not find text to translate.")
            return

        # Load the new model
        model_name = f"Helsinki-NLP/opus-mt-{retry_language_code}-{target_lang}"
        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)

        # Perform the translation
        inputs = tokenizer(text_to_translate, return_tensors="pt", padding=True)
        translated = model.generate(**inputs)
        translation = tokenizer.decode(translated[0], skip_special_tokens=True)

        # Rename the thread to include the updated source and target languages
        new_thread_name = f"Translation: {retry_language_code} -> {target_lang}"
        await thread.edit(name=new_thread_name)

        await thread.send(f"Retry Translation ({retry_language_code} -> {target_lang}): {translation}")
    except Exception as e:
        await thread.send(f"Retry failed with error: {e}")

# Event: Message edit for retrying translation
@bot.event
async def on_message_edit(before, after):
    """Handle editing of messages and retry translation if necessary."""
    if after.id in error_threads:
        error_thread = error_threads[after.id]
        # Check if the edited message is a valid retry attempt
        if after.content:
            try:
                # Retry translation
                source_lang = detect(after.content)
                target_lang = active_translations.get(after.channel.id, None)
                if target_lang:
                    model, tokenizer = get_model_and_tokenizer(source_lang, target_lang)
                    if model is None or tokenizer is None:
                        await error_thread.send(f"Model for {source_lang} -> {target_lang} could not be loaded. Try a different source language.")
                        return

                    # Translate and send the result
                    inputs = tokenizer(after.content, return_tensors="pt", padding=True)
                    translated = model.generate(**inputs)
                    translation = tokenizer.decode(translated[0], skip_special_tokens=True)
                    await error_thread.send(f"Translated message: {translation}")
                    # Remove the error thread as the retry succeeded
                    del error_threads[after.id]
            except Exception as e:
                await error_thread.send(f"Error retrying translation: {e}")

@bot.command()
async def translate(ctx, source_lang: str = None, target_lang: str = None, *, text: str = None):
    """Translate a message with optional source and target languages."""
    user_id = ctx.author.id

    # Use user's default target language if no target language is provided
    if target_lang is None:
        target_lang = default_languages.get(user_id)
        if target_lang is None:
            await ctx.send("Please set a default target language using !setlanguage <target_lang> or specify a target language in the command.")
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

# List of supported language codes and their respective languages for MarianMT
LANGUAGE_CODES = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "ru": "Russian",
    "zh": "Chinese (Simplified)",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "pt": "Portuguese",
    "nl": "Dutch",
    "sv": "Swedish",
    "pl": "Polish",
    "fi": "Finnish",
    "tr": "Turkish",
    "cs": "Czech",
    "hu": "Hungarian",
    "ro": "Romanian",
    "tl": "Tagalog",
    "th": "Thai",
    "id": "Indonesian",
    "hi": "Hindi",
}

def format_language_codes():
    """Format the language codes into a readable string."""
    return "\n".join([f"`{code}`: {language}" for code, language in LANGUAGE_CODES.items()])

# Bot command: !languagecodes
@bot.command(name="languagecodes")
async def languagecodes_command(ctx):
    formatted_codes = format_language_codes()
    await ctx.send(f"Supported Language Codes:\n{formatted_codes}")

# Run the bot
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Failed to run bot: {e}")
