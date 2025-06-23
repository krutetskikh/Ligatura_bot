
from telegram import Update, InputFile, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters
import fitz
import re
import os
import pandas as pd
from datetime import datetime
from collections import defaultdict

expenses_by_thread = defaultdict(list)

def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text()
    return text

def extract_sum_with_fallback(text):
    lines = text.lower().splitlines()
    for line in lines:
        if any(word in line for word in ["сумма", "итого", "к оплате", "на сумму"]):
            line = re.sub(r'(?<=\d)-(?=\d)', '.', line)
            numbers = re.findall(r'(\d[\d\s]*[.,]?\d{0,2})', line)
            for raw in numbers:
                cleaned = raw.replace(' ', '').replace(',', '.')
                try:
                    return float(cleaned)
                except:
                    continue
    match = re.search(r'(\d{2,6}-\d{2})', text)
    if match:
        return float(match.group(1).replace('-', '.'))
    return None

def classify_document(text):
    t = text.lower()
    if "платежное поручение" in t or "платёжное поручение" in t:
        return "payment"
    elif "счет на оплату" in t or ("инн" in t and "услуги" in t):
        return "invoice"
    elif "фн" in t or "итого" in t or "ккт" in t:
        return "receipt"
    else:
        return "unknown"

def extract_description(text):
    lines = text.splitlines()
    key_lines = [
        line.strip() for line in lines
        if any(word in line.lower() for word in ["оплата", "услуги", "по счету", "мероприятие", "поставка"])
        and len(line.strip()) > 20
    ]
    if key_lines:
        return max(key_lines, key=len)
    return ""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        keyboard = [["📊 Отчет", "📁 Экспорт"], ["➕ Добавить трату"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Привет! Я помогу вести учёт расходов по проектам. Выберите действие:",
            reply_markup=reply_markup
        )
    else:
        keyboard = [[
            InlineKeyboardButton("📊 Отчет", callback_data="report"),
            InlineKeyboardButton("📁 Экспорт", callback_data="export"),
            InlineKeyboardButton("➕ Добавить трату", callback_data="add_expense")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Привет! Я помогу вести учёт расходов по проектам. Выберите действие:",
            reply_markup=reply_markup,
            message_thread_id=update.message.message_thread_id
        )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    thread_id = update.message.message_thread_id or 0
    file = await context.bot.get_file(document.file_id)
    os.makedirs("temp", exist_ok=True)
    file_path = f"temp/{document.file_name}"
    await file.download_to_drive(file_path)

    if document.file_name.lower().endswith(".pdf"):
        text = extract_text_from_pdf(file_path)
        doc_type = classify_document(text)
        amount = extract_sum_with_fallback(text)
        description = extract_description(text)

        if doc_type in ["payment", "receipt"] and amount:
            expenses_by_thread[thread_id].append((amount, description or "расход", datetime.now()))
            await update.message.reply_text(
                f"✅ Документ обработан как *{doc_type}*\n"
                f"💸 Сумма: {amount:.2f} ₽\n"
                f"📝 Назначение: {description or '—'}\n"
                f"📊 Учтено в теме #{thread_id}",
                parse_mode='Markdown',
                message_thread_id=thread_id
            )
        else:
            await update.message.reply_text(
                f"⚠️ Не удалось автоматически учесть документ.\n"
                f"Тип: {doc_type}, сумма: {amount}, описание: {description or '—'}",
                message_thread_id=thread_id
            )

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thread_id = update.message.message_thread_id or 0
    expenses = expenses_by_thread.get(thread_id, [])
    if not expenses:
        await update.message.reply_text("Нет расходов в этой теме.", message_thread_id=thread_id)
        return
    total = sum(x[0] for x in expenses)
    lines = [f"{x[0]:,.2f} ₽ — {x[1]}" for x in expenses]
    """
    await update.message.reply_text(text, message_thread_id=thread_id)

async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thread_id = update.message.message_thread_id or 0
    expenses = expenses_by_thread.get(thread_id, [])
    if not expenses or not isinstance(expenses[0], tuple):
        await update.message.reply_text("Нет расходов для экспорта.", message_thread_id=thread_id)
        return
    df = pd.DataFrame(expenses, columns=["Сумма", "Назначение", "Дата"])
    filename = f"report-thread-{thread_id}.xlsx"
    filepath = os.path.join("temp", filename)
    df.to_excel(filepath, index=False)
    with open(filepath, "rb") as f:
        await update.message.reply_document(
            document=InputFile(f, filename=filename),
            caption=f"📁 Экспорт по теме #{thread_id}",
            message_thread_id=thread_id
        )

async def handle_expense_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    thread_id = update.message.message_thread_id or 0
    if message == "📊 Отчет":
        await report(update, context)
        return
    elif message == "📁 Экспорт":
        await export(update, context)
        return
    elif message == "➕ Добавить трату":
    await update.message.reply_text(
        """Введите трату в формате:
`-сумма описание`

Пример:
`-1200 аренда техники`""",
        parse_mode='Markdown'
    )
        return
    if message.startswith("-"):
        try:
            parts = message[1:].strip().split(" ", 1)
            amount = float(parts[0].replace("т", "000").replace(",", "."))
            comment = parts[1] if len(parts) > 1 else ""
            expenses_by_thread[thread_id].append((amount, comment, datetime.now()))
            await update.message.reply_text(
                f"💸 Учтено: {amount:.2f} ₽ — {comment}",
                message_thread_id=thread_id
            )
        except Exception as e:
            await update.message.reply_text(f"⚠️ Не понял расход: {e}", message_thread_id=thread_id)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    message = query.message
    thread_id = message.message_thread_id or 0

    if query.data == "report":
        expenses = expenses_by_thread.get(thread_id, [])
        if not expenses:
            await message.reply_text("Нет расходов в этой теме.", message_thread_id=thread_id)
            return
        total = sum(x[0] for x in expenses)
        lines = [f"{x[0]:,.2f} ₽ — {x[1]}" for x in expenses]
        Всего потрачено: {total:,.2f} ₽

" + "
".join(lines)
        """
text = f"""📊 Отчет по проекту (тема #{thread_id})\nВсего потрачено: {total:,.2f} ₽\n\n{chr(10).join(lines)}"""
await message.reply_text(text, message_thread_id=thread_id)

    elif query.data == "export":
        expenses = expenses_by_thread.get(thread_id, [])
        if not expenses or not isinstance(expenses[0], tuple):
            await message.reply_text("Нет расходов для экспорта.", message_thread_id=thread_id)
            return
        df = pd.DataFrame(expenses, columns=["Сумма", "Назначение", "Дата"])
        filename = f"report-thread-{thread_id}.xlsx"
        filepath = os.path.join("temp", filename)
        df.to_excel(filepath, index=False)
        with open(filepath, "rb") as f:
            await message.reply_document(
                document=InputFile(f, filename=filename),
                caption=f"📁 Экспорт по теме #{thread_id}",
                message_thread_id=thread_id
            )

    elif query.data == "add_expense":
    await message.reply_text(
        """Введите трату в формате:
`-сумма описание`

Пример:
`-1200 аренда техники`""",
        parse_mode='Markdown',
        message_thread_id=thread_id
    )

def main():
    app = ApplicationBuilder().token("8026620280:AAFWnFLucuTEwRyDZ8kucNuPuiOT8M0B03o").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("export", export))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_expense_message))
    print("✅ Бот запущен. Ожидает сообщения...")
    app.run_polling()

if __name__ == "__main__":
    main()
