#!/usr/bin/env bash
set -e
git init -q .
printf 'def total(xs):\n    return sum(xs)\n' > calc.py
git add . && git -c user.name=eval -c user.email=eval@example.com commit -qm "init"
printf 'def total(xs):\n    return sum(x for x in xs if x > 0)\n' > calc.py
