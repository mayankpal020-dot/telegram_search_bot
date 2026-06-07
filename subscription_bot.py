import json
import os
import time
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ========== CONFIGURATION ==========
# Read from environment variables (set on Render)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))  # Your Telegram user ID

DATA_FILE = "knowledge_base.json"
SUB_FILE = "subscribers.json"
# ===================================

# ---------- Load/save knowledge base ----------
def load_knowledge():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_knowledge(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

knowledge_base = load_knowledge()

# ---------- Load/save subscribers ----------
def load_subscribers():
    if os.path.exists(SUB_FILE):
        with open(SUB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_subscribers(data):
    with open(SUB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

subscribers = load_subscribers()  # Format: { "user_id": expiry_timestamp (0=forever) }

# ---------- Helper: check subscription ----------
def is_subscribed(user_id: int) -> bool:
    user_id_str = str(user_id)
    if user_id_str not in subscribers:
        return False
    expiry = subscribers[user_id_str]
    if expiry == 0:  # permanent
        return True
    if expiry > time.time():
        return True
    # expired, remove from list
    del subscribers[user_id_str]
    save_subscribers(subscribers)
    return False

# ---------- Admin commands for subscription ----------
async def subscribe_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /subscribe <user_id> [days]  (0 days = permanent)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /subscribe <user_id> [days]\nExample: /subscribe 123456789 30\nUse 0 for permanent.")
        return

    try:
        user_id = int(context.args[0])
        days = int(context.args[1]) if len(context.args) > 1 else 30
    except ValueError:
        await update.message.reply_text("❌ Invalid user_id or days. Use numbers only.")
        return

    if days == 0:
        expiry = 0
        expiry_text = "forever"
    else:
        expiry = time.time() + (days * 86400)
        expiry_text = datetime.fromtimestamp(expiry).strftime("%Y-%m-%d %H:%M:%S")

    subscribers[str(user_id)] = expiry
    save_subscribers(subscribers)
    await update.message.reply_text(f"✅ User {user_id} subscribed for {days if days>0 else 'permanent'} days.\nExpires: {expiry_text}")

async def unsubscribe_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/unsubscribe <user_id>"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /unsubscribe <user_id>")
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user_id.")
        return

    user_id_str = str(user_id)
    if user_id_str in subscribers:
        del subscribers[user_id_str]
        save_subscribers(subscribers)
        await update.message.reply_text(f"🗑️ User {user_id} unsubscribed.")
    else:
        await update.message.reply_text("User not found in subscription list.")

async def list_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all active subscribers (admin only)"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return

    if not subscribers:
        await update.message.reply_text("No active subscribers.")
        return

    now = time.time()
    active = []
    for uid, exp in subscribers.items():
        if exp == 0:
            active.append(f"{uid} (permanent)")
        elif exp > now:
            remain_days = int((exp - now) / 86400)
            active.append(f"{uid} ({remain_days} days left)")
        else:
            # expired, will be cleaned later
            pass

    if not active:
        await update.message.reply_text("No active subscribers (all expired).")
    else:
        await update.message.reply_text("📋 Active subscribers:\n" + "\n".join(active))

# ---------- User command: check own status ----------
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_subscribed(user_id):
        exp = subscribers.get(str(user_id), 0)
        if exp == 0:
            await update.message.reply_text("✅ You have a permanent subscription.")
        else:
            remain_days = int((exp - time.time()) / 86400)
            await update.message.reply_text(f"✅ You are subscribed. {remain_days} days remaining.")
    else:
        await update.message.reply_text("❌ You are not subscribed. Please contact the admin to get access.")

# ---------- Admin: knowledge base commands ----------
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /add keyword | answer")
        return

    full_text = " ".join(context.args)
    if " | " not in full_text:
        await update.message.reply_text("Separate keyword and answer with ' | '")
        return

    keyword, answer = full_text.split(" | ", 1)
    keyword = keyword.strip().lower()
    answer = answer.strip()

    knowledge_base[keyword] = answer
    save_knowledge(knowledge_base)
    await update.message.reply_text(f"✅ Saved: {keyword} → {answer}")

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /delete keyword")
        return

    keyword = " ".join(context.args).strip().lower()
    if keyword in knowledge_base:
        del knowledge_base[keyword]
        save_knowledge(knowledge_base)
        await update.message.reply_text(f"🗑️ Deleted: {keyword}")
    else:
        await update.message.reply_text("Keyword not found.")

async def list_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return

    if not knowledge_base:
        await update.message.reply_text("No saved answers yet.")
        return

    keywords = "\n".join(knowledge_base.keys())
    await update.message.reply_text(f"📚 All keywords:\n{keywords}")

# ---------- User search (requires subscription) ----------
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_subscribed(user_id):
        await update.message.reply_text("🔒 This bot requires a subscription. Please contact the admin to subscribe.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /ask <keyword>")
        return

    keyword = " ".join(context.args).strip().lower()
    if keyword in knowledge_base:
        await update.message.reply_text(knowledge_base[keyword])
    else:
        await update.message.reply_text(f"❌ No answer found for '{keyword}'.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """If user just sends a text (no command), treat as search but check subscription."""
    user_id = update.effective_user.id
    if not is_subscribed(user_id):
        await update.message.reply_text("🔒 Subscription required. Please use /status to check or contact admin.")
        return

    keyword = update.message.text.strip().lower()
    if keyword in knowledge_base:
        await update.message.reply_text(knowledge_base[keyword])
    else:
        await update.message.reply_text(f"I don't know about '{keyword}'. Try /ask or contact admin.")

# ---------- Start command ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 Subscription Search Bot\n\n"
        "To search: just type a keyword or use /ask <keyword>\n"
        "Check your subscription: /status\n\n"
        "If you are not subscribed, please contact the admin."
    )

# ---------- Main ----------
def main():
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
        return
    if ADMIN_ID == 0:
        print("Warning: ADMIN_ID not set. Admin commands will be disabled.")

    app = Application.builder().token(TOKEN).build()

    # Public commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Admin commands
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CommandHandler("list", list_all))
    app.add_handler(CommandHandler("subscribe", subscribe_user))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_user))
    app.add_handler(CommandHandler("subscriptions", list_subscribers))

    # Use webhook for Render (or fallback to polling if PORT not set)
    port = os.environ.get("PORT")
    if port:
        print(f"Starting bot with webhook on port {port}")
        app.run_webhook(listen="0.0.0.0", port=int(port))
    else:
        print("Starting bot with polling (local development)")
        app.run_polling()

if __name__ == "__main__":
    main()