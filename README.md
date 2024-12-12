# vioLa: a Language Translation Discord Bot

Created for IAT 360's final project. vioLa uses MarianMT to translate between languages. Also supports basic slang translations to make conversations ever so slightly relatable.
 
## Usage
- Invite vioLa to your Discord server through the link: https://discord.com/oauth2/authorize?client_id=1311949246630723645&permissions=397553118230&integration_type=0&scope=bot
- Make sure you give vioLa the permissions it wants!

## Commands & Functionalities
***< argument > = required | [ argument ] optional***
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
- When live translation is active, vioLa will listen into the conversation and translate it to the specified language.
- If you run into an error, you can retry with the correct source language by replying to the thread!
### **Retry Translations:**
- Respond to error threads with a language code to retry translations if the initial attempt fails.

## Disclaimers and Functionalities
### **Privacy:**
Here's how vioLa handles your data:
- **Data Handling**:  
  vioLa processes your messages temporarily in memory for translation purposes. vioLa does not store or permanently save your messages.
- **Sensitive Content**:  
  Please don't share sensitive, confidential, or personally identifiable information. While vioLa does not store data, your messages are processed in memory and could potentially appear in error logs.
- **Message Visibility**:  
  vioLa's translations and responses are visible in the channel or thread where they're posted unless explicitly set to be private (e.g., using slash commands). Use private commands for sensitive content.
### **Disclaimers:**
A few things to keep in mind:
- **Accuracy of Translations**:  
  vioLa is not perfect. vioLa's translations might not always be accurate or contextually correct. For important translations, double-check independently.
- **Slang Terms and Cultural Nuances**:  
  vioLa supports predefined slang translations to make chatting more fun. But these mappings might not always reflect accurate or universally accepted equivalents, so use them with discretion.
- **User Responsibility**:  
  By using vioLa, you acknowledge that translations and custom configurations are at your own risk. vioLa's creators aren't responsible for misinterpretations or misuse of translations.
- **Opt-Out Options**:  
  If you don't want your messages translated during live translation mode, let your server moderators know or avoid posting in channels where vioLa is active.
