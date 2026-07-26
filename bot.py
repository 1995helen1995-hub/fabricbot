import os
import base64
import logging
import asyncio
from datetime import date
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

DAILY_LIMIT = 30
MEDIA_GROUP_WAIT_SECONDS = 1.5

# В памяти: {user_id: (date, count)} — сбрасывается при каждом новом дне
user_usage = defaultdict(lambda: (date.today(), 0))

# Буфер для альбомов фото (несколько фото одним сообщением)
media_group_buffer = {}

WELCOME_TEXT = """👋 Привет, {name}!

Это чат-бот для определения типа обивочной ткани мебели по фото и подбора протокола чистки.

🤖 Как пользоваться:
1. Пришлите макрофото ткани прямо в этот чат
2. Бот ответит автоматически: тип ткани, состав, рекомендации по чистке и работе
3. Под ответом нажмите 👍 если верно или 👎 если ошибся — бот учится на отзывах

📸 Фото должно быть качественным:
• Макро, расстояние 5–10 см от ткани
• Перпендикулярно поверхности
• Дневной свет, без вспышки и бликов
• В кадре только ткань — без молний, швов, фурнитуры
• Если есть care tag (этикетка с составом) — отдельным фото, бот её прочитает и приоритизирует

📦 Можно прислать несколько ракурсов одной мебели одним сообщением — бот сделает комбинированный анализ.

⚠ Если бот не уверен (точность ниже 80%) — он предложит обсудить тип ткани с коллегами в чате.

🚫 Лимит: {limit} запросов в сутки на пользователя.

Удачи! 🧵"""

SYSTEM_PROMPT = """Ты — эксперт по химчистке мебели с 10-летним опытом. Тебе присылают одно или несколько фото ткани мебели (диван, кресло, стул и т.д.), твоя задача — определить тип ткани и дать протокол чистки.

Если фото несколько — рассматривай их как разные ракурсы одной и той же ткани и делай один общий (комбинированный) вывод. Если среди фото есть care tag (этикетка с составом) — приоритизируй информацию с неё над визуальным анализом и явно укажи, что состав подтверждён биркой.

ФОРМАТ ОТВЕТА (строго придерживайся структуры):

🧵 Тип: [название ткани]
🧪 Состав: [предположительный состав] (уверенность X%)

📖 [МАКСИМУМ 2 коротких предложения: главная особенность ткани + единственное самое важное слабое место. Без общих рассуждений про "средний сегмент", "жилую мебель" и т.п. — только конкретика, которая влияет на протокол чистки]

🧼 Чистка: [конкретный протокол — метод (сухая чистка/влажная), pH pre-spray, время выдержки, тип агитации/щётки, параметры экстрактора (давление PSI, температура °F), количество проходов, финальная нейтрализация, время сушки]

🔧 В работе: [что делать с типичными пятнами на этой ткани — конкретные средства из списка ниже]

⚠ [ограничения и предупреждения — что нельзя делать с этой тканью]

СПИСОК СРЕДСТВ И ПРИНЦИПОВ (используй только эти, не выдумывай другие):

Pre-spray (основная чистка):
- Prochem Powerburst — универсальный pre-spray, разводится 1:32, нельзя на натуральные ткани (высокий pH)
- Prochem Finefabric — для деликатных/натуральных тканей (лён, бамбук, вискоза, шерсть), разводится 1:16, без нагрева воды
- Chemspec Formula 90 — щелочной универсальный pre-spray, pH 10.3, глубокая чистка синтетики и сильнозагрязнённой мебели

Нейтрализация/ополаскивание:
- Chemspec All Fiber Textile Rinse — кислотный ополаскиватель, pH 3.6, обязателен после щелочного pre-spray

Ферментная обработка (органика):
- Chemspec Enz-All — ферментный порошок, pH 11.0, для органических пятен и запахов
- Enzol (принцип) — моча, пот/себум, еда, молоко/детская смесь, кровь, рвота, старые органические пятна. НЕЛЬЗЯ на шерсть, шёлк, вискозу без теста

Точечные пятновыводители:
- BridgePoint Avenger Pro — универсальный точечный
- Citrus Gel — жир, клей, жвачка, чернила
- Pro's Choice Stain Magic — сложные старые пятна (кровь, вино, белок), смешать 1:1
- BridgePoint Protein Spotter — белковые пятна, только холодная вода
- BridgePoint RedZoneReady — красные пятна (напитки, вино, красители)
- Chemspec Stain Exit — кофе и вино, pH 3.5
- Chemspec Ink Exit — чернила, pH 7.2
- Parker & Bailey Instant Stain Remover — универсальный запасной вариант

Запахи:
- Odorcide 210 — глубокое устранение запахов, разводится 1:16, не добавлять в бак экстрактора
- Chemspec Kill Odor Plus — запахи мочи и животных, pH 6.1

Кожа:
- HydraForce Leather Cleaner/Revitalizer/Protector — очистка → восстановление → защита

Пятна по категориям:
- Жир/масло/макияж/клей/жвачка → Citrus Gel, точечно, промакивать
- Белковое/органика → Enz-All / Protein Spotter, только холодная вода, выдержка 10-15 мин
- Старые органические пятна → Stain Magic 1:1 или Stain Exit, под плёнкой, 10-15 мин
- Красное вино/соки/кофе → RedZoneReady или Stain Exit
- Чернила/маркеры/помада → Citrus Gel, Ink Exit или Avenger Pro, от края к центру
- Запахи → Odorcide 210 или Kill Odor Plus, выдержка 30+ мин

Общие правила безопасности:
- Всегда тестировать средство на незаметном участке ткани перед применением
- Натуральные ткани (лён, шерсть, бамбук, вискоза, шёлк) — без нагрева экстрактора, только Finefabric
- Кровь — никогда не нагревать воду
- После щелочного pre-spray — обязательна нейтрализация All Fiber Textile Rinse

ПРАВИЛА АНАЛИЗА:
1. Смотри на плетение нитей, текстуру, блеск, ворсистость, наличие узлов
2. Если уверенность ниже 80% — добавь в конец: "⚠ Уверенность ниже 80% — рекомендуем обсудить тип ткани с коллегами в чате или прислать макрофото бирки состава (care tag)"
3. Никогда не выдумывай средства, которых нет в списке выше
4. Если на фото флакон химии — просто опиши, что это за средство и для чего оно
5. Если на фото не мебель/не химия — вежливо попроси прислать фото ткани крупным планом

ЖЁСТКИЕ ОГРАНИЧЕНИЯ ПО ФОРМАТУ (обязательно соблюдать, иначе ответ не поместится):
- НЕ используй markdown-таблицы (| столбец | столбец |) — они занимают слишком много места. Вместо таблицы с пятнами используй простой список: "• Название пятна → Средство, короткое действие"
- НЕ используй заголовки уровня ### и жирный текст на каждой строке — форматирование должно быть минимальным (эмодзи-заголовки разделов достаточно)
- Раздел "🔧 В работе" — максимум 5 самых частых типов пятен для этой ткани, каждый одной строкой
- Не пиши "общими словами" — каждое предложение должно нести конкретную практическую информацию (конкретное число, конкретное средство, конкретное действие), а не описательные рассуждения
- Общий объём всего ответа — не более 220 слов. Это жёсткий лимит, пиши компактно и по существу, без повторов
"""


def check_and_increment_limit(user_id: int) -> tuple[bool, int]:
    """Возвращает (разрешено ли, сколько запросов осталось после этого)."""
    today = date.today()
    last_date, count = user_usage[user_id]
    if last_date != today:
        count = 0
    if count >= DAILY_LIMIT:
        return False, 0
    count += 1
    user_usage[user_id] = (today, count)
    return True, DAILY_LIMIT - count


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "друг"
    await update.message.reply_text(WELCOME_TEXT.format(name=name, limit=DAILY_LIMIT))


def feedback_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👍 Верно", callback_data="feedback_good"),
                InlineKeyboardButton("👎 Ошибся", callback_data="feedback_bad"),
            ]
        ]
    )


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "feedback_good":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Спасибо за подтверждение! 👍")
    else:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "Спасибо, учтём! Если можете — пришлите макрофото бирки состава (care tag), это поможет точнее определить ткань в следующий раз. 👎"
        )
    logger.info(f"Фидбек от {query.from_user.id}: {query.data}")


async def analyze_images(image_bytes_list):
    content = []
    for photo_bytes in image_bytes_list:
        base64_image = base64.b64encode(photo_bytes).decode("utf-8")
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64_image,
                },
            }
        )
    content.append(
        {
            "type": "text",
            "text": "Проанализируй эту ткань (или эти фото одной ткани/бирки) и дай протокол чистки.",
        }
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


async def process_photos(chat_id: int, user_id: int, photos, context: ContextTypes.DEFAULT_TYPE):
    allowed, remaining = check_and_increment_limit(user_id)
    if not allowed:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🚫 Вы достигли лимита {DAILY_LIMIT} запросов в сутки. Попробуйте завтра.",
        )
        return

    status_msg = await context.bot.send_message(chat_id=chat_id, text="🔍 Анализирую ткань, секунду...")

    try:
        image_bytes_list = []
        for photo in photos:
            largest = photo[-1]
            photo_file = await largest.get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            image_bytes_list.append(bytes(photo_bytes))

        answer = await analyze_images(image_bytes_list)

        await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{answer}\n\n_Осталось запросов сегодня: {remaining}_",
            reply_markup=feedback_keyboard(),
            parse_mode="Markdown",
        )

    except Exception as e:
        logger.error(f"Ошибка при анализе фото: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Что-то пошло не так при анализе фото. Попробуйте отправить ещё раз.",
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    media_group_id = update.message.media_group_id

    if not media_group_id:
        await process_photos(chat_id, user_id, [update.message.photo], context)
        return

    key = (chat_id, media_group_id)
    if key not in media_group_buffer:
        media_group_buffer[key] = []
    media_group_buffer[key].append(update.message.photo)

    await asyncio.sleep(MEDIA_GROUP_WAIT_SECONDS)

    if media_group_buffer.get(key) and len(media_group_buffer[key]) > 0:
        photos = media_group_buffer.pop(key, None)
        if photos:
            await process_photos(chat_id, user_id, photos, context)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришлите, пожалуйста, фото ткани мебели крупным планом — я определю тип ткани и дам протокол чистки."
    )


def main():
    if not TELEGRAM_TOKEN or not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "Не заданы переменные окружения TELEGRAM_TOKEN и/или ANTHROPIC_API_KEY"
        )

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_feedback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Бот запущен и слушает сообщения...")
    app.run_polling()


if __name__ == "__main__":
    main()
