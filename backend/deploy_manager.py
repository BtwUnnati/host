import asyncio, os, subprocess

async def deploy_repo(repo_url, user_id):
    folder = f"deploys/{user_id}"
    os.makedirs(folder, exist_ok=True)
    repo_name = repo_url.split("/")[-1].replace(".git", "")
    path = f"{folder}/{repo_name}"
    if os.path.exists(path):
        subprocess.run(["rm", "-rf", path])
    subprocess.run(["git", "clone", repo_url, path])

    req = f"{path}/requirements.txt"
    if os.path.exists(req):
        subprocess.run(["pip3", "install", "-r", req])

    env_file = f"{path}/.env"
    if not os.path.exists(env_file):
        with open(env_file, "w") as f:
            f.write("PORT=8080\n")

    subprocess.Popen(["python3", f"{path}/app.py"])
    return f"✅ App **{repo_name}** deployed successfully!"
