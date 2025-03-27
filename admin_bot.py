import logging
import os
import json
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

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

def remove_from_blacklist(league_name: str):
    """Remove a league name from the blacklist."""
    blacklist = load_blacklist()
    if league_name in blacklist:
        blacklist.remove(league_name)
        save_blacklist(blacklist)
        return True
    return False

def clear_blacklist():
    """Clear all entries from the blacklist."""
    save_blacklist(set())

async def clear_blacklist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /clear_blacklist command."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("You do not have permission to use this command.")
        return

    clear_blacklist()
    await update.message.reply_text("The blacklist has been cleared.")


async def unban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /unban command to remove a league from the blacklist."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("You do not have permission to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /unban <league_name>")
        return

    league_name_input = " ".join(context.args).strip()
    league_name_input = " ".join(league_name_input.split())  # normalize spaces
    league_name = league_name_input.lower()


    removed = remove_from_blacklist(league_name)
    if removed:
        await update.message.reply_text(f"League '{league_name_input}' has been removed from the blacklist.")
    else:
        await update.message.reply_text(f"League '{league_name_input}' is not in the blacklist.")


async def blacklist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /blacklist command."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("You do not have permission to use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /ban <league_name>")
        return

    league_name_input = " ".join(context.args).strip()
    league_name = league_name_input.lower()
    
    add_to_blacklist(league_name)
    await update.message.reply_text(f"League '{league_name_input}' has been added to the blacklist.")



async def view_blacklist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /view_blacklist command to show all blacklisted leagues."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("You do not have permission to use this command.")
        return

    blacklist = get_blacklist()
    if not blacklist:
        await update.message.reply_text("The blacklist is empty.")
        return
    
    keyboard = [
        [InlineKeyboardButton(f"Unban '{league}'", callback_data=f"confirm_unban:{league}")]
        for league in sorted(blacklist)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Blacklisted leagues:", reply_markup=reply_markup)

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks (e.g. unban league)."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.edit_message_text("You do not have permission to do this.")
        return

    data = query.data

    if data.startswith("confirm_unban:"):
        league = data.split("confirm_unban:")[1]
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, unban", callback_data=f"do_unban:{league}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_unban")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Are you sure you want to unban *{league}*?",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

    elif data.startswith("do_unban:"):
        league = data.split("do_unban:")[1]
        removed = remove_from_blacklist(league)
        if removed:
            await query.edit_message_text(f"✅ '{league}' has been removed from the blacklist.")
        else:
            await query.edit_message_text(f"❌ '{league}' was not found in the blacklist.")

    elif data == "cancel_unban":
        await query.edit_message_text("❌ Unban cancelled.")



async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    await update.message.reply_text(
        "Welcome to the Blacklist Bot! Use:\n"
        "/ban <league_name> - add a league to the blacklist\n"
        "/unban <league_name> - remove a league from the blacklist\n"
        "/view_blacklist - see all blacklisted leagues\n"
        "/clear_blacklist - wipe the blacklist (admin only)"
    )


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
    app.add_handler(CommandHandler("blacklist", blacklist_handler))
    app.add_handler(CommandHandler("view_blacklist", view_blacklist_handler))
    app.add_handler(CommandHandler("unban", unban_handler))
    app.add_handler(CommandHandler("clear_blacklist", clear_blacklist_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))



    # Run the bot
    logger.info("Bot is starting...")
    app.run_polling()
