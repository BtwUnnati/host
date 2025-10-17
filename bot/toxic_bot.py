import os, asyncio, subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from dotenv import load_dotenv
from db.models import init_db, add_app, get_user_apps
from backend.deploy_manager import deploy_repo

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

async def start(update: Update, ctx: CallbackContext):
    await update.message.reply_text(
        "🤖 Welcome to ToxicDeploy!\nSend /deploy <git_repo_url> to deploy your project."
    )

async def deploy(update: Update, ctx: CallbackContext):
    if not ctx.args:
        return await update.message.reply_text("Usage: /deploy <git_repo_url>")
    repo = ctx.args[0]
    msg = await update.message.reply_text("🚀 Deploying... please wait.")
    res = await deploy_repo(repo, update.effective_user.id)
    await msg.edit_text(res)

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("deploy", deploy))
    app.run_polling()

if __name__ == "__main__":
    main()
