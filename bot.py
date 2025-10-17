# bot.py
import os, asyncio, logging, uuid, time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from dotenv import load_dotenv
from models import SessionLocal, init_db, User, App, Order
from deploy_manager import deploy, stop_container
from sqlalchemy.exc import NoResultFound

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
FREE_MB = int(os.getenv("FREE_MB", "512"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_db()
db = SessionLocal()

# Helpers
def get_or_create_user(tg_id):
    u = db.query(User).filter_by(telegram_id=tg_id).first()
    if not u:
        u = User(telegram_id=tg_id, credits=0)
        db.add(u); db.commit(); db.refresh(u)
    return u

def user_total_allocated_mb(user):
    apps = db.query(App).filter_by(owner_id=user.id).all()
    return sum(a.mem_mb or 0 for a in apps)

def can_allocate(user, requested_mb):
    free = FREE_MB
    used = user_total_allocated_mb(user)
    available_free = max(0, free - used)
    if requested_mb <= available_free:
        return True, 0
    needed = requested_mb - available_free
    if user.credits >= needed:
        return True, needed
    return False, needed

# Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id)
    await update.message.reply_text(
        "Welcome to ToxicDeploy (alpha).\nUse /deploy <git_repo_url> [mem_mb] to deploy.\nUse /apps to list.\nUse /buycredits <amount_in_rupees> to create an order.\nAdmin: /approve <order_id> to approve."
    )

async def deploy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("Usage: /deploy <git_repo_url> [mem_mb]")
        return
    repo = context.args[0]
    mem = int(context.args[1]) if len(context.args) > 1 else 256
    ok, needed = can_allocate(user, mem)
    if not ok:
        await update.message.reply_text(f"You need {needed} more MB credits to allocate {mem} MB. Buy credits with /buycredits.")
        return
    msg = await update.message.reply_text(f"Deploying {repo} with {mem} MB...\nThis may take a few minutes.")
    # run deploy in background
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, asyncio.run, _deploy_bg(repo, update.effective_user.id, mem))
    # result is tuple (success, info)
    success, info = result
    if success:
        # register app in DB
        container = info.get("container") if isinstance(info, dict) else None
        app_entry = App(name=repo.split("/")[-1].replace(".git",""), repo=repo, owner_id=user.id, container_name=container or "", mem_mb=mem, status="running")
        db.add(app_entry); db.commit()
        await msg.edit_text(f"✅ Deployed. App registered as `{app_entry.name}`. Container: {container or 'process'}. Use /apps to view.")
        # if credits were needed (needed>0) deduct
        if needed>0:
            user.credits -= needed
            db.add(user); db.commit()
            await update.message.reply_text(f"{needed} MB credits consumed from your balance.")
    else:
        await msg.edit_text(f"❌ Deploy failed:\n{info}")

async def _deploy_bg(repo, user_id, mem):
    # wrapper to call deploy.sync function safely
    import asyncio
    try:
        ok, info = await deploy(repo, user_id, mem_mb=mem)
        return ok, info
    except Exception as e:
        return False, str(e)

async def apps_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id)
    apps = db.query(App).filter_by(owner_id=user.id).all()
    if not apps:
        await update.message.reply_text("You have no apps.")
        return
    txt = "Your apps:\n"
    for a in apps:
        txt += f"- {a.name} | mem: {a.mem_mb} MB | status: {a.status} | container: {a.container_name}\n"
    await update.message.reply_text(txt)

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /stop <app_name>")
        return
    user = get_or_create_user(update.effective_user.id)
    name = context.args[0]
    app = db.query(App).filter_by(owner_id=user.id, name=name).first()
    if not app:
        await update.message.reply_text("App not found.")
        return
    if app.container_name:
        stop_container(app.container_name)
    app.status = "stopped"
    db.add(app); db.commit()
    await update.message.reply_text(f"Stopped {name}.")

async def buycredits_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("Usage: /buycredits <amount_in_rupees>\nExample: /buycredits 100")
        return
    amount = int(context.args[0])
    # Pricing: decided mapping rupees -> MB credits. For simplicity: 1 rupee = 1 MB credit (you can change)
    credits = amount
    order_id = f"ORD{int(time.time())}{uuid.uuid4().hex[:6].upper()}"
    order = Order(order_id=order_id, user_id=user.id, amount=amount, credits=credits, status="pending")
    db.add(order); db.commit()
    await update.message.reply_text(
        f"Order created: `{order_id}`\nAmount: ₹{amount}\nCredits on approval: {credits} MB\n\nPay to your UPI: `your-upi-id@bank`\nAfter payment, admin will verify and approve. Admin can approve using:\n`/approve {order_id}`"
    )

async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Only admin can approve orders.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve <order_id>")
        return
    oid = context.args[0]
    order = db.query(Order).filter_by(order_id=oid).first()
    if not order:
        await update.message.reply_text("Order not found.")
        return
    if order.status != "pending":
        await update.message.reply_text(f"Order already {order.status}.")
        return
    # add credits to user
    user = db.query(User).filter_by(id=order.user_id).first()
    user.credits += order.credits
    order.status = "approved"
    db.add(user); db.add(order); db.commit()
    await update.message.reply_text(f"Order {oid} approved. {order.credits} MB added to user {user.telegram_id}.")

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id)
    used = user_total_allocated_mb(user)
    await update.message.reply_text(f"Credits: {user.credits} MB\nAllocated (apps): {used} MB\nFree allowance: {FREE_MB} MB")

async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_or_create_user(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("Usage: /logs <app_name>")
        return
    name = context.args[0]
    app = db.query(App).filter_by(owner_id=user.id, name=name).first()
    if not app:
        await update.message.reply_text("App not found.")
        return
    # If docker container, show docker logs -n 200
    if app.container_name:
        import subprocess
        p = subprocess.Popen(["docker", "logs", "--tail", "200", app.container_name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = p.communicate()[0].decode()
        await update.message.reply_text(f"Logs for {name}:\n<pre>{out[:4000]}</pre>", parse_mode="HTML")
    else:
        await update.message.reply_text("No container logs available for this app (it may be running as a process).")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/deploy <repo> [mem_mb]\n/apps\n/stop <app>\n/logs <app>\n/buycredits <amount>\n/balance\nAdmin: /approve <order_id>"
    )

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("deploy", deploy_cmd))
    app.add_handler(CommandHandler("apps", apps_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("buycredits", buycredits_cmd))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    logger.info("Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
