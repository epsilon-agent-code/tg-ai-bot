"""
Скрипт для генерации STRING_SESSION
Запусти один раз, скопируй результат в .env
"""
from pyrogram import Client
import os
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

if not api_id or not api_hash:
    print("❌ Ошибка: API_ID и API_HASH должны быть в .env файле!")
    print("Сначала создай .env файл с твоими данными")
    exit()

print("🔧 Генерация STRING_SESSION...")
print("📱 Сейчас нужно будет ввести номер телефона и код из Telegram\n")

app = Client("temp_session", api_id=api_id, api_hash=api_hash)

async def main():
    async with app:
        session_string = await app.export_session_string()
        print("\n" + "="*60)
        print("✅ Твой STRING_SESSION:")
        print("="*60)
        print(session_string)
        print("="*60)
        print("\n📋 Скопируй эту строку и вставь в .env файл")
        print("   в переменную STRING_SESSION")
        print("\nПример:")
        print("STRING_SESSION=" + session_string)
        print("="*60)

if __name__ == "__main__":
    app.run(main())