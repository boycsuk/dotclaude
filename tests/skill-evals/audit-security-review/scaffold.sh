#!/usr/bin/env bash
set -e
git init -q .
printf 'import sqlite3\n\ndef find_user(db, name):\n    return db.execute("SELECT * FROM users WHERE name = \x27" + name + "\x27").fetchall()\n' > users.py
printf 'from users import find_user\n\ndef handler(db, req):\n    return find_user(db, req.args["name"])\n' > app.py
git add . && git -c user.name=eval -c user.email=eval@example.com commit -qm "init"
