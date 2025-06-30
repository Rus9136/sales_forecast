#!/usr/bin/env python3
"""
Автоматический запуск загрузки без интерактивных вопросов
"""
import subprocess
import sys

# Запускаем основной скрипт с автоматическим вводом 'y'
process = subprocess.Popen(
    [sys.executable, 'load_historical_sales_advanced.py'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

# Отслеживаем вывод и автоматически отвечаем на вопросы
for line in iter(process.stdout.readline, ''):
    print(line, end='')
    
    # Автоматически отвечаем 'y' на вопросы
    if '❓' in line and '(y/n):' in line:
        process.stdin.write('y\n')
        process.stdin.flush()
        print('y')  # Показываем что ответили

process.wait()