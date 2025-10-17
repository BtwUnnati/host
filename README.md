1) Prepare VPS (Ubuntu example)
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git docker.io

2) Clone project onto VPS and set up
git clone <paste-repo-url-or-copy-files>
cd toxicdeploy

3) Configure .env
cp .env.example .env
# edit .env: BOT_TOKEN, ADMIN_ID, APP_ROOT, DB_PATH etc

4) Install Python deps
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

5) Create DB
python3 - <<PY
from models import init_db
init_db()
print('DB created')
PY

6) Run bot
./run.sh

7) Usage (Telegram)
/start -> register
/deploy https://github.com/your/repo.git 256
/apps
/buycredits 100   # creates an order (1 rupee = 1 MB credit in this example)
/approve ORD...   # admin approves and credits user
/balance
/logs <appname>
