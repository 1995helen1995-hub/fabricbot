import os
import base64
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Ты — эксперт по химчистке мебели с 10-летним опытом. Тебе присылают фото ткани мебели (диван, кресло, стул и т.д.), твоя задача — определить тип ткани и дать протокол чистки.

ФОРМАТ ОТВЕТА (строго придерживайся структуры):

🧵 Тип: [название ткани]
🧪 Состав: [предположительный состав] (уверенность X%)

📖 [2-3 предложения о ткани: насколько она распространена, какие у неё особенности, слабые места, к чему чувствительна]

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
2. Если уверенность ниже 80% — добавь: "⚠ Уверенность ниже 80% — рекомендуем прислать макрофото бирки состава (care tag) или уточнить у мастера"
3. Никогда не выдумывай средства, которых нет в списке выше
4. Если на фото флакон химии — просто опиши, что это за средство и для чего оно
5. Если на фото не мебель/не химия — вежливо попроси прислать фото ткани крупным планом
"""


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text="🔍 Анализирую ткань, секунду...")

    try:
        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        base64_image = base64.b64encode(photo_bytes).decode("utf-8")

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image,
                            },
                        },
                        {"type": "text", "text": "Проанализируй эту ткань и дай протокол чистки."},
                    ],
                }
            ],
        )

        answer = "".join(block.text for block in response.content if block.type == "text")
        await context.bot.send_message(chat_id=chat_id, text=answer)

    except Exception as e:
        logger.error(f"Ошибка при анализе фото: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Что-то пошло не так при анализе фото. Попробуйте отправить ещё раз.",
        )


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
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Бот запущен и слушает сообщения...")
    app.run_polling()


if __name__ == "__main__":
    main()
