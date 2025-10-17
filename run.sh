#!/usr/bin/env bash
export $(grep -v '^#' .env | xargs)
nohup python3 bot.py > bot.log 2>&1 &
echo "Bot started, logs -> bot.log"
