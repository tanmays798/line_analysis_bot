import logging
import os
import json
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename='bot.log',
    filemode='a'
)

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Check if the user ID is in the admins list."""
    return str(user_id) in ADMINS


def load_blacklist():
    """Load the blacklist from the JSON file."""
    if not os.path.exists(BLACKLIST_FILE):
        return set()
    with open(BLACKLIST_FILE, "r") as file:
        return set(json.load(file))


def save_blacklist(blacklist):
    """Save the blacklist to the JSON file."""
    with open(BLACKLIST_FILE, "w") as file:
        json.dump(list(blacklist), file)


def add_to_blacklist(league_name: str):
    """Add a league name to the blacklist."""
    blacklist = load_blacklist()
    blacklist.add(league_name)
    save_blacklist(blacklist)


def get_blacklist():
    """Retrieve the blacklist."""
    return load_blacklist()


async def blacklist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /blacklist command."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("You do not have permission to use this command.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /blacklist <league_name>")
        return

    league_name = context.args[0]
    add_to_blacklist(league_name.lower())
    await update.message.reply_text(f"League '{league_name}' has been added to the blacklist.")


async def view_blacklist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /view_blacklist command to show all blacklisted leagues."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("You do not have permission to use this command.")
        return

    blacklist = get_blacklist()
    if not blacklist:
        await update.message.reply_text("The blacklist is empty.")
    else:
        blacklist_str = "\n".join(blacklist)
        await update.message.reply_text(f"Blacklisted leagues:\n{blacklist_str}")


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    await update.message.reply_text(
        "Welcome to the Blacklist Bot! Use /ban <league_name> to add a league to the blacklist and /view_blacklist to view the list.")


if __name__ == "__main__":
    load_dotenv()

    # File to store the blacklist
    BLACKLIST_FILE = os.getenv("BLACKLIST_FILE")

    # List of admin Telegram IDs
    ADMINS = os.getenv("ADMINS").split(',')  # Replace with actual admin IDs
    print(ADMINS, type(ADMINS))

    LOGGING_BOT = os.getenv("LOGGING_BOT")

    # Create the application
    app = ApplicationBuilder().token(LOGGING_BOT).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("ban", blacklist_handler))
    app.add_handler(CommandHandler("view_blacklist", view_blacklist_handler))

    # Run the bot
    logger.info("Bot is starting...")
    app.run_polling()
