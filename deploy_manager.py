# 
import os, subprocess, shutil, uuid, time
from pathlib import Path

APP_ROOT = os.getenv("APP_ROOT", "/opt/toxicdeploy/deploys")
DEFAULT_PORT = int(os.getenv("DEFAULT_CONTAINER_PORT", "8000"))

os.makedirs(APP_ROOT, exist_ok=True)

def safe_container_name(user_id, repo_name):
    rid = repo_name.replace(".", "-").replace("/", "-")
    return f"td_{user_id}_{rid}_{uuid.uuid4().hex[:6]}"

def run_cmd(cmd, cwd=None, stream_output=False):
    print("CMD:", " ".join(cmd))
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = []
    if stream_output:
        for line in p.stdout:
            print(line, end="")
            out.append(line)
    else:
        out = p.communicate()[0]
    return_code = p.wait()
    return return_code, "".join(out) if isinstance(out, list) else out

async def deploy(repo_url, user_id, mem_mb=256):
    """
    Steps:
    - clone repo into APP_ROOT/<user_id>/<repo_name>
    - detect Dockerfile -> build image and run container with memory limit
    - else if requirements.txt -> install into virtualenv and run python app.py or uvicorn
    - return status message and container_name or path
    """
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    user_dir = Path(APP_ROOT) / str(user_id)
    app_dir = user_dir / repo_name
    # clean if exists
    if app_dir.exists():
        shutil.rmtree(app_dir)
    user_dir.mkdir(parents=True, exist_ok=True)

    # Clone
    code, out = run_cmd(["git", "clone", repo_url, str(app_dir)])
    if code != 0:
        return False, f"Git clone failed:\n{out}"

    # Create .env if missing
    env_file = app_dir / ".env"
    if not env_file.exists():
        env_file.write_text(f"PORT={DEFAULT_PORT}\n")

    container_name = safe_container_name(user_id, repo_name)

    # If Dockerfile present
    if (app_dir / "Dockerfile").exists():
        image_tag = f"{container_name}:latest"
        code, out = run_cmd(["docker", "build", "-t", image_tag, "."], cwd=str(app_dir), stream_output=True)
        if code != 0:
            return False, f"Docker build failed:\n{out}"
        # run container with memory limit
        # publish container port to random host port using -p 0:PORT is not supported via CLI; choose to map host port dynamically
        run_cmd(["docker", "rm", "-f", container_name], cwd=None)
        # create run command
        mem_flag = f"--memory={mem_mb}m"
        code, out = run_cmd([
            "docker", "run", "-d", "--name", container_name, mem_flag, image_tag
        ])
        if code != 0:
            return False, f"Docker run failed:\n{out}"
        # get container id
        return True, {"type":"docker", "container": container_name}
    else:
        # fallback: try to detect python app
        # install requirements in venv and run using gunicorn/uvicorn as background process inside screen (simple)
        venv_dir = app_dir / ".venv"
        run_cmd(["python3", "-m", "venv", str(venv_dir)])
        pip = str(venv_dir / "bin" / "pip")
        python = str(venv_dir / "bin" / "python")
        if (app_dir / "requirements.txt").exists():
            run_cmd([pip, "install", "-r", "requirements.txt"], cwd=str(app_dir), stream_output=True)
        # try to find entrypoint
        # prefer app.py or main.py
        if (app_dir / "app.py").exists():
            entry = "app.py"
            # run in background using nohup
            # ensure PORT from .env is used; we will export
            env_vars = {}
            for line in (app_dir / ".env").read_text().splitlines():
                if "=" in line:
                    k,v = line.split("=",1)
                    env_vars[k]=v
            cmd = f"cd {app_dir} && nohup {python} {entry} > app.log 2>&1 & echo $!"
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out, err = proc.communicate()
            return True, {"type":"process", "pid": out.strip(), "path": str(app_dir)}
        else:
            return False, "No Dockerfile and no app.py found. Please provide a Dockerfile or app.py entrypoint."

def stop_container(container_name):
    run_cmd(["docker", "rm", "-f", container_name])
    return True
