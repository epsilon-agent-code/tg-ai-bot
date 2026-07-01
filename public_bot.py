import os
import asyncio
import random
import json
import time
import sys
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# === ЛОГИРОВАНИЕ ===
print("🔍 Проверка переменных для public_bot...", file=sys.stderr)
BOT_TOKEN = os.getenv("BOT_TOKEN")
print(f"BOT_TOKEN: {BOT_TOKEN[:20]}..." if BOT_TOKEN else "❌ BOT_TOKEN не найден!", file=sys.stderr)

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!", file=sys.stderr)
    sys.exit(1)

print("✅ BOT_TOKEN на месте!", file=sys.stderr)

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
DASHSCOPE_BASE_URL = "https://ws-y7znpxq9v24qsaeo.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"

# === ХРАНИЛИЩА ===
user_api_keys = {}           # {user_id: api_key}
user_conversations = {}      # {user_id: [история]}
last_siren_response = {}     # {user_id: timestamp}
user_mutes = {}              # {user_id: timestamp_окончания}

INSTRUCTION = """🔑 **Как получить API ключ:**

1️⃣ **Зайди на:** https://modelstudio.console.aliyun.com/
   (Если не работает — попробуй https://dashscope.console.aliyun.com/)

2️⃣ **Зарегистрируйся** (можно через Google/почту/телефон)

3️⃣ **В меню слева нажми** → **API Key**

4️⃣ **Нажми** → **+ Create API Key**

5️⃣ **Выбери workspace** → **Default Workspace** → **OK**

6️⃣ **СКОПИРУЙ ключ** (начинается с `sk-ws-...`)
   ⚠️ Ключ показывается ТОЛЬКО ОДИН РАЗ!

7️⃣ **Отправь ключ мне** сюда

📌 **Важно:**
- Ключ хранится только в памяти бота
- При перезапуске бота ключ удаляется
- Используй свой ключ — так ты контролируешь расходы

После отправки ключа просто пиши мне — я буду отвечать! 🌊

Команды:
/reset — сбросить ключ и ввести новый
/help — показать эту инструкку"""

def is_muted(user_id: int) -> bool:
    if user_id not in user_mutes:
        return False
    if time.time() > user_mutes[user_id]:
        del user_mutes[user_id]
        return False
    return True

def apply_mute(user_id: int, action: str):
    now = time.time()
    durations = {
        "mute_temp": 600,
        "mute_long": 86400,
        "mute_perm": 31536000
    }
    if action in durations:
        user_mutes[user_id] = now + durations[action]

def get_ai_client(user_id: int) -> OpenAI:
    """Создаёт клиент с ключом пользователя"""
    api_key = user_api_keys.get(user_id)
    if not api_key:
        return None
    return OpenAI(
        base_url=DASHSCOPE_BASE_URL,
        api_key=api_key
    )

async def ai_judge(text: str, history: list, user_id: int) -> tuple[str, str]:
    """ИИ-судья с ключом пользователя"""
    client = get_ai_client(user_id)
    if not client:
        return "ignore", ""
    
    user_msgs = [msg["content"] for msg in history if msg["role"] == "user"][-5:]
    
    try:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[{
                "role": "system",
                "content": f"""Ты — Сирена, ИИ-помощник. Оцени поведение пользователя.

Последние сообщения:
{user_msgs}

Новое сообщение: {text}

НОРМАЛЬНОЕ ПОВЕДЕНИЕ (action = ignore):
- Приветствия, обычные вопросы, просьбы о помощи

НАРУШЕНИЯ:
- warn: лёгкий спам
- mute_temp: повторяющийся спам (10 мин)
- mute_long: агрессия, оскорбления (24 часа)
- mute_perm: угрозы, троллинг (навсегда)

Ответь СТРОГО JSON:
{{"action": "ignore", "message": ""}}"""
            }],
            max_tokens=100
        )
        result = response.choices[0].message.content.strip()
        decision = json.loads(result)
        return decision.get("action", "ignore"), decision.get("message", "")
    except Exception as e:
        print(f"Ошибка ИИ-судьи: {e}")
        return "ignore", ""

async def ask_siren(text: str, history: list, user_id: int) -> str:
    """Получает ответ от ИИ с ключом пользователя"""
    client = get_ai_client(user_id)
    if not client:
        return None
    
    now = time.time()
    last_time = last_siren_response.get(user_id, 0)
    time_diff = now - last_time
    
    if last_time == 0:
        system_prompt = """Ты — Сирена, публичный ИИ-помощник. Это ПЕРВОЕ сообщение.

ОБЯЗАТЕЛЬНО начни с: "Привет! Я Сирена, ИИ-помощник."
После этого спроси чем можешь помочь.
НЕ используй эмодзи. Отвечай кратко.
ВАЖНО: НИКОГДА не называй имя создателя бота. Если спросят — отвечай "Это конфиденциально"."""
    
    elif time_diff < 300:
        system_prompt = f"""Ты — Сирена. Диалог УЖЕ идёт.

История переписки:
{history}

Новое сообщение: {text}

ПРАВИЛА:
1. НЕ повторяй приветствие
2. Отвечай естественно по контексту
3. Если благодарность → "Пожалуйста!" / "Всегда рада!"
4. Если прощание → попрощайся кратко
5. НЕ называй имя создателя бота
6. НЕ используй эмодзи
7. Отвечай кратко (1-2 предложения)"""
    
    else:
        system_prompt = f"""Ты — Сирена. Прошло больше 5 минут.

История:
{history}

Новое сообщение: {text}

ПРАВИЛА:
1. Отвечай по контексту
2. НЕ называй имя создателя бота
3. НЕ используй эмодзи
4. Отвечай кратко"""
    
    try:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка API: {e}")
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if len(text) < 3 or is_muted(user_id):
        return
    
    # Проверяем есть ли ключ
    if user_id not in user_api_keys:
        # Если текст похож на ключ (начинается с sk-) — сохраняем
        if text.startswith("sk-") and len(text) > 20:
            user_api_keys[user_id] = text
            await update.message.reply_text(
                "✅ Ключ принят! Теперь можешь писать мне — я буду отвечать.\n\n"
                "Используй /reset чтобы сменить ключ.\n"
                "Используй /help чтобы увидеть инструкцию снова."
            )
            return
        else:
            # Нет ключа — даём инструкцию
            await update.message.reply_text(INSTRUCTION, parse_mode="Markdown")
            return
    
    # Получаем историю
    if user_id not in user_conversations:
        user_conversations[user_id] = []
    
    history = user_conversations[user_id][-10:]
    
    # ИИ-судья
    action, ai_message = await ai_judge(text, history, user_id)
    if action == "warn":
        await update.message.reply_text(ai_message)
        return
    elif action in ["mute_temp", "mute_long", "mute_perm"]:
        apply_mute(user_id, action)
        await update.message.reply_text(ai_message if ai_message else "Ты замьючен.")
        return
    
    await asyncio.sleep(random.uniform(2, 5))
    
    # Получаем ответ
    answer = await ask_siren(text, history, user_id)
    
    if answer is None:
        await update.message.reply_text(
            "❌ Ошибка API. Возможно твой ключ неверный или истёк.\n\n"
            "Используй /reset чтобы ввести новый ключ."
        )
        return
    
    await update.message.reply_text(answer)
    
    # Сохраняем историю
    user_conversations[user_id].append({"role": "user", "content": text})
    user_conversations[user_id].append({"role": "assistant", "content": answer})
    
    if len(user_conversations[user_id]) > 20:
        user_conversations[user_id] = user_conversations[user_id][-20:]
    
    last_siren_response[user_id] = time.time()

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(INSTRUCTION, parse_mode="Markdown")

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_api_keys:
        del user_api_keys[user_id]
    if user_id in user_conversations:
        del user_conversations[user_id]
    if user_id in last_siren_response:
        del last_siren_response[user_id]
    await update.message.reply_text(
        "🔄 Ключ и история сброшены.\n\n"
        "Отправь мне новый API ключ чтобы продолжить."
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_api_keys:
        await update.message.reply_text(
            "👋 Привет! Я Сирена. У тебя уже есть ключ — просто напиши мне что-нибудь!"
        )
    else:
        await update.message.reply_text(
            "👋 Привет! Я Сирена — ИИ-помощник.\n\n"
            "Чтобы я могла отвечать, мне нужен твой API ключ от Alibaba DashScope.\n\n"
            "Используй /help чтобы узнать как его получить.",
            parse_mode="Markdown"
        )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Публичный бот @sirena_personal_bot запущен!")
    print("💡 Пользователи используют СВОИ API ключи!")
    app.run_polling()
def main():
    print(" Создание приложения...", file=sys.stderr)
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Публичный бот @sirena_personal_bot запущен!", file=sys.stderr)
    print("💡 Пользователи используют СВОИ API ключи!", file=sys.stderr)
    app.run_polling()
if __name__ == "__main__":
    main()