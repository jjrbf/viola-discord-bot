import os
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands
from transformers import MarianMTModel, MarianTokenizer
from langdetect import detect, LangDetectException
import nltk
from nltk.tokenize import sent_tokenize
import json
import re

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Download the punkt tokenizer before starting the bot
nltk.download("punkt_tab")

# Load the JSON file
with open('common_phrases_translations.json', 'r', encoding='utf-8') as file:
    translations_slang = json.load(file)

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
    
def replace_slang(message, source_lang, target_lang):
    """
    Replace slang phrases in the message based on the provided source and target languages.
    """
    # Check if the source language exists in the translations dictionary
    pair = f"{source_lang}-{target_lang}"
    if pair in translations_slang:
        slang_dict = translations_slang[pair]

        # Replace slang phrases in the message (case insensitive)
        for slang, slang_translation in slang_dict.items():
            if slang.lower() in message.lower():
                if slang_translation:
                    # Use regex for case-insensitive replacement while preserving case
                    def replace_case_insensitive(match):
                        original = match.group(0)
                        # Preserve the case of the original slang
                        if original.isupper():
                            return slang_translation.upper()
                        elif original[0].isupper():
                            return slang_translation.capitalize()
                        else:
                            return slang_translation

                    # Replace all occurrences of the slang in the message
                    message = re.sub(re.escape(slang), replace_case_insensitive, message, flags=re.IGNORECASE)
    
    return message

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
            # Normalize Chinese language codes
            if source_lang in ["zh-cn", "zh-tw"]:
                source_lang = "zh"

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
                f"Translation model for {source_lang} -> {target_lang} could not be loaded or is unsupported. Try setting a source and target language manually."
            )
            return

        # Sentence segmentation
        sentences = sent_tokenize(text)
        translations = []

        for sentence in sentences:
            # Replace slang in the sentence
            updated_sentence = replace_slang(sentence, source_lang, target_lang)
            
            # Translate using MarianMT
            inputs = tokenizer(updated_sentence, return_tensors="pt", padding=True)
            translated = model.generate(**inputs)
            translated_sentence = tokenizer.decode(translated[0], skip_special_tokens=True)
            
            translations.append(translated_sentence)

        final_translation = " ".join(translations)

        await interaction.followup.send(
            f"Translation ({source_lang} -> {target_lang}): {final_translation}"
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
        if message.channel.name.startswith("Translation:") or message.channel.name.startswith("Error: Translation model for"):
            if len(message.content) == 2:  # Language codes are typically 2 characters
                retry_language_code = message.content.lower()
                try:
                    async for thread_message in message.channel.history(limit=2, oldest_first=True):
                        if "Translating: " in thread_message.content:
                            first_message = thread_message.content.split("Translating: ")[1]
                    async for thread_message in message.channel.history(limit=3, oldest_first=True):
                        if "Translation model for" in thread_message.content:
                            target_lang = thread_message.content.split("->")[-1].strip().split()[0]
                            await retry_translation(
                                thread=message.channel,
                                original_message=first_message,
                                retry_language_code=retry_language_code,
                                target_lang=target_lang,
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
            source_lang = detect(message.content)
            # Normalize Chinese language codes
            if source_lang in ["zh-cn", "zh-tw"]:
                source_lang = "zh"
            if source_lang == target_lang:
                return

            model, tokenizer = get_model_and_tokenizer(source_lang, target_lang)
            if model is None or tokenizer is None:
                error_msg = f"Translation model for {source_lang} -> {target_lang} could not be loaded or is unsupported."
                error_thread = await message.create_thread(name=f"Error: {error_msg}")
                await error_thread.send(f"Translating: {message.content}")
                await error_thread.send(f"{error_msg}\n\nReply to this message with a new source language (e.g., 'en').")
                error_threads[message.id] = error_thread
                return

            # Sentence segmentation and translation
            sentences = sent_tokenize(message.content)
            translations = []

            for sentence in sentences:
                # Replace slang in the sentence
                updated_sentence = replace_slang(sentence, source_lang, target_lang)
                
                # Translate using MarianMT
                inputs = tokenizer(updated_sentence, return_tensors="pt", padding=True)
                translated = model.generate(**inputs)
                translated_sentence = tokenizer.decode(translated[0], skip_special_tokens=True)
                
                translations.append(translated_sentence)

            final_translation = " ".join(translations)

            # Create a thread for the translation
            thread_title = f"Translation: {source_lang} -> {target_lang}"
            translation_thread = await message.create_thread(name=thread_title, auto_archive_duration=60)

            # Ensure the bot is explicitly added as a thread member
            await translation_thread.add_user(bot.user)

            # Iterate over the list of thread members and remove all non-bot users
            for member in translation_thread.members:
                if member.id != bot.user.id:  # Skip the bot itself
                    try:
                        await translation_thread.remove_user(member)
                    except Exception as e:
                        print(f"Failed to remove {member.name} from thread: {e}")

            await translation_thread.send(f"Translated message: {final_translation}")

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
                # Normalize Chinese language codes
                if source_lang in ["zh-cn", "zh-tw"]:
                    source_lang = "zh"
                target_lang = active_translations.get(after.channel.id, None)
                if target_lang:
                    model, tokenizer = get_model_and_tokenizer(source_lang, target_lang)
                    if model is None or tokenizer is None:
                        await error_thread.send(f"Model for {source_lang} -> {target_lang} could not be loaded or is unsupported. Try setting a source and target language manually.")
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
            await ctx.send("Please set a default target language using /setlanguage <target_lang> or specify a target language in the command.")
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
            # Normalize Chinese language codes
            if source_lang in ["zh-cn", "zh-tw"]:
                source_lang = "zh"
            await ctx.send(f"Detected source language: {source_lang}")

        # If the detected source language is the same as the target language
        if source_lang == target_lang:
            await ctx.send("The text is already in the target language.")
            return

        # Get the model and tokenizer (using the cache)
        model, tokenizer = get_model_and_tokenizer(source_lang, target_lang)
        if model is None or tokenizer is None:
            await ctx.send(f"Translation model for {source_lang} -> {target_lang} could not be loaded or is unsupported. Try setting a source and target language manually.")
            return

        # Sentence segmentation
        sentences = sent_tokenize(text)
        translations = []

        for sentence in sentences:
            # Replace slang in the sentence
            updated_sentence = replace_slang(sentence, source_lang, target_lang)
            
            # Translate using MarianMT
            inputs = tokenizer(updated_sentence, return_tensors="pt", padding=True)
            translated = model.generate(**inputs)
            translated_sentence = tokenizer.decode(translated[0], skip_special_tokens=True)
            
            translations.append(translated_sentence)

        final_translation = " ".join(translations)

        await ctx.send(f"Translation ({source_lang} -> {target_lang}): {final_translation}")
    except LangDetectException:
        await ctx.send("Could not detect the language of the input text. Please try again.")
    except Exception as e:
        await ctx.send(f"Error: {e}")

@bot.tree.command(name="slangterms", description="Show all supported slang terms for a specific language code.")
async def slangterms(interaction: discord.Interaction, language_code: str):
    """Display all slang terms for a specified language code privately."""
    found = False
    response = f"**Slang terms for `{language_code}`:**\n"

    for pair, slang_dict in translations_slang.items():
        source, target = pair.split("-")
        if source == language_code:
            if isinstance(slang_dict, dict):  # Check if it's a dictionary
                for slang, target_slang in slang_dict.items():
                    response += f"`[{slang}] -> [{target}]: {target_slang}`\n"
                found = True
            else:
                response += f"\nError: Unexpected structure for key `{pair}`. Value: {slang_dict}"
                print(f"Debug: slang_dict is not a dictionary for key `{pair}`. Value: {slang_dict}")
    
    if not found:
        response = f"No slang terms found for the language code: `{language_code}`."

    await interaction.response.send_message(response, ephemeral=True)


@bot.command(name="slangterms")
async def slangterms_command(ctx, language_code: str):
    """Display all slang terms for a specified language code publicly."""
    found = False
    response = f"**Slang terms for `{language_code}`:**\n"

    for pair, slang_dict in translations_slang.items():
        source, target = pair.split("-")
        if source == language_code:
            if isinstance(slang_dict, dict):  # Check if it's a dictionary
                for slang, target_slang in slang_dict.items():
                    response += f"`[{slang}] -> [{target}]: {target_slang}`\n"
                found = True
            else:
                response += f"\nError: Unexpected structure for key `{pair}`. Value: {slang_dict}"
                print(f"Debug: slang_dict is not a dictionary for key `{pair}`. Value: {slang_dict}")
    
    if not found:
        response = f"No slang terms found for the language code: `{language_code}`."

    await ctx.send(response)

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

# Help message content
HELP_MESSAGE = """
## **Hello, I'm **vioLa**, a translation Discord Bot!**

***<argument> = required | [argument] optional***
### **Slash Commands (outputs only to you!):**
1. `/setlanguage <target_lang>`: Set your default target language for translations.
2. `/translate <text> [source_lang] [target_lang]`: Translate a specific text with optional source and target languages. Omitting the `[source_lang]` method will detect the language for you, while omitting the `[target_lang]` will default it to your set language.
3. `/languagecodes`: View all supported language codes and their corresponding languages privately.
4. `/slangterms <language_code>`: Show all supported slang terms for a specific language code privately.
5. `/help`: Display this help message privately.
6. `/about`: Learn more about vioLa!
### **Bot Commands (outputs to the whole server!):**
1. `!translate <text> [source_lang] [target_lang]`: Same thing as above, but publicly! Reply to a message without the `<text>` to translate that message.
2. `!startlivetranslation <target_lang>`: Start live translation mode in the current channel. Messages will be translated to the specified target language.
3. `!stoplivetranslation`: Stop live translation mode in the current channel.
4. `!languagecodes`: View all supported language codes and their corresponding languages publicly.
5. `!slangterms <language_code>`: Show all supported slang terms for a specific language code publicly.
6. `!help`: Display this help message publicly.
### **Live Translation:**
- When live translation is active, I will listen into the conversation and translate it to the specified language.
- If you run into an error, you can retry with the correct source language by replying to the thread!
### **Retry Translations:**
- Respond to error threads with a language code to retry translations if the initial attempt fails.
"""

DISCLAIMER_MESSAGE = """
## Hi there! I'm **vioLa**, a translation Discord Bot!!
### **About Me:**
Here's some important information about how I work:
- **What I Do**:  
  I translate text messages between languages using AI models. I also support basic slang translations to make conversations ever so slightly relatable!
- **How I Work**:  
  I use pre-trained translation models (like MarianMT) to perform translations. These models are based on open-source datasets, ensuring fast and efficient translations. 
### **Privacy:**
Here's how I handle your data:
- **Data Handling**:  
  I process your messages temporarily in memory for translation purposes. I do not store or permanently save your messages.
- **Sensitive Content**:  
  Please don't share sensitive, confidential, or personally identifiable information. While I don't store data, your messages are processed in memory and could potentially appear in error logs.
- **Message Visibility**:  
  My translations and responses are visible in the channel or thread where they're posted unless explicitly set to be private (e.g., using slash commands). Use private commands for sensitive content.
### **Disclaimers:**
A few things to keep in mind:
- **Accuracy of Translations**:  
  I do my best, but I'm not perfect! My translations might not always be accurate or contextually correct. For important translations, double-check independently.
- **Slang Terms and Cultural Nuances**:  
  I support predefined slang translations to make chatting more fun! But these mappings might not always reflect accurate or universally accepted equivalents, so use them with discretion.
- **User Responsibility**:  
  By using me, you acknowledge that translations and custom configurations are at your own risk. My creators aren't responsible for misinterpretations or misuse of translations.
- **Opt-Out Options**:  
  If you don't want your messages translated during live translation mode, let your server moderators know or avoid posting in channels where I'm active.
## Acknowledgments  
This project uses the MarianMT model:  

MarianNMT Team. *Marian: Fast Neural Machine Translation in C++*. Licensed under the MIT License. Available at [https://marian-nmt.github.io](https://marian-nmt.github.io)  

Additionally, MarianMT relies on datasets from the OPUS project:  
Tiedemann, J. (2012). *Parallel Data, Tools, and Interfaces in OPUS*. In Proceedings of the 8th International Conference on Language Resources and Evaluation (LREC'2012), Istanbul, Turkey. Available at [https://opus.nlpl.eu](https://opus.nlpl.eu)  

"""
  
# Override the default help command
bot.remove_command('help')  # Remove the default help command
@bot.command(name="help", help="Displays a list of bot functionalities.")
async def custom_help(ctx):
    await ctx.send(HELP_MESSAGE)

# Slash command: /help
@bot.tree.command(name="help", description="Display the bot's functionalities and commands.")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(HELP_MESSAGE, ephemeral=True)

# Bot info command slash /about
@bot.tree.command(name="about", description="Displays more information about vioLa and its usage")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(DISCLAIMER_MESSAGE, ephemeral=True)

# Run the bot
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"Failed to run bot: {e}")
