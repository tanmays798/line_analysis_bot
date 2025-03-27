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

#for use of pagination
ITEMS_PER_PAGE = 10


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
        await update.message.reply_text("Usage: /blacklist <league_name>")
        return

    league_name_input = " ".join(context.args).strip()
    league_name = league_name_input.lower()
    
    add_to_blacklist(league_name)
    await update.message.reply_text(f"League '{league_name_input}' has been added to the blacklist.")



async def view_blacklist_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1):
    """Show a paginated view of the blacklist with inline unban buttons."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("You do not have permission to use this command.")
        return

    blacklist = sorted(get_blacklist())
    total_items = len(blacklist)
    total_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    if page < 1 or page > total_pages:
        await update.message.reply_text("Invalid page number.")
        return

    start = (page - 1) * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_items = blacklist[start:end]

    keyboard = []
    for league in page_items:
        keyboard.append([
            InlineKeyboardButton(f"🏷️ {league}", callback_data="noop"),
            InlineKeyboardButton("❌ Unban", callback_data=f"confirm_unban:{league}")
        ])

    # Pagination buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⏮ Prev", callback_data=f"page:{page - 1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("⏭ Next", callback_data=f"page:{page + 1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Blacklisted leagues (page {page}/{total_pages}):",
        reply_markup=reply_markup
    )

async def view_blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["blacklist_page"] = 1
    await view_blacklist_handler(update, context, page=1)


# Optional: handle noop to silently ignore disabled buttons
# (league name buttons are clickable but do nothing)
async def noop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


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

        # Figure out which page we were on by saving it in context (optional fallback to 1)
        page = context.user_data.get("blacklist_page", 1)

        if removed:
            # Delete the old message and send a refreshed one
            try:
                await query.delete_message()
            except:
                pass  # Just in case it's already gone
            await view_blacklist_handler(update, context, page=page)
        else:
            await query.edit_message_text(f"❌ '{league}' was not found in the blacklist.")


    elif data.startswith("page:"):
        try:
            page_num = int(data.split("page:")[1])
            context.user_data["blacklist_page"] = page_num  # Save it
            await view_blacklist_handler(update, context, page=page_num)
        except ValueError:
            await query.edit_message_text("Invalid page number.")


    elif data == "cancel_unban":
        await query.edit_message_text("❌ Unban cancelled.")



async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    await update.message.reply_text(
        "Welcome to the Blacklist Bot! Use:\n"
        "/blacklist <league_name> - add a league to the blacklist\n"
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
    app.add_handler(CommandHandler("view_blacklist", view_blacklist_command))
    app.add_handler(CommandHandler("unban", unban_handler))
    app.add_handler(CommandHandler("clear_blacklist", clear_blacklist_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(CallbackQueryHandler(noop_handler, pattern="^noop$"))



    # Run the bot
    logger.info("Bot is starting...")
    app.run_polling()
