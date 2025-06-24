import os
import logging
import fitz  # PyMuPDF
import pandas as pd
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
from dotenv import load_dotenv

# Загрузка токена из .env
load_dotenv()
TOKEN = os.getenv("TOKEN")

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Хранилище расходов
expenses_by_thread = {}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📊 Отчёт", callback_data="report"),
            InlineKeyboardButton("📁 Экспорт", callback_data="export"),
        ],
        [InlineKeyboardButton("➕ Добавить трату", callback_data="add_expense")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привет! Я помогу вести учёт расходов по проектам. Выберите действие:",
        reply_markup=reply_markup,
    )

# Обработка кнопок
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    thread_id = query.message.message_thread_id

    if query.data == "report":
        await report(update, context)
    elif query.data == "export":
        await export(update, context)
    elif query.data == "add_expense":
        await query.message.reply_text(
            "Введите трату в формате:\n"
            "`–сумма описание`

"
            "*Пример:*
"
            "`–1200 аренда техники`",
            parse_mode='Markdown',
            message_thread_id=thread_id
        )

# Команда /report
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thread_id = update.effective_message.message_thread_id
    if thread_id not in expenses_by_thread or not expenses_by_thread[thread_id]:
        await update.message.reply_text("Нет данных о расходах.", message_thread_id=thread_id)
        return

    total = sum(exp[0] for exp in expenses_by_thread[thread_id])
    text = f"📊 Отчет по проекту (тема #{thread_id})\n\n"
    for amount, comment, dt in expenses_by_thread[thread_id]:
        text += f"• {dt.strftime('%d.%m.%Y')} — {amount:,.2f} ₽ — {comment}\n"
    text += f"\nИтого: {total:,.2f} ₽"
    await update.message.reply_text(text, message_thread_id=thread_id)

# Команда /export
async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thread_id = update.effective_message.message_thread_id
    if thread_id not in expenses_by_thread or not expenses_by_thread[thread_id]:
        await update.message.reply_text("Нет данных для экспорта.", message_thread_id=thread_id)
        return

    df = pd.DataFrame(expenses_by_thread[thread_id], columns=["Сумма", "Описание", "Дата"])
    filename = f"temp/report-thread-{thread_id}.xlsx"
    Path("temp").mkdir(exist_ok=True)
    df.to_excel(filename, index=False)

    with open(filename, "rb") as f:
        await update.message.reply_document(f, message_thread_id=thread_id)

# Обработка новых сообщений
async def handle_expense_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    thread_id = update.message.message_thread_id

    if not thread_id:
        return

    if message.startswith("-"):
        try:
            parts = message[1:].strip().split(" ", 1)
            amount = float(parts[0].replace("т", "000").replace(",", "."))
            comment = parts[1] if len(parts) > 1 else ""
            expenses_by_thread.setdefault(thread_id, []).append((amount, comment, datetime.now()))
            await update.message.reply_text(
                f"📌 Учтено: {amount:.2f} ₽ — {comment}",
                message_thread_id=thread_id
            )
        except Exception as e:
            await update.message.reply_text(f"⚠️Не понял расход: {e}", message_thread_id=thread_id)

# Основная функция
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("export", export))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_expense_message))
    print("✅ Бот запущен. Ожидает сообщения...")
    app.run_polling()

if __name__ == "__main__":
    main()