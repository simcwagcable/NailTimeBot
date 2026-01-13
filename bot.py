import os
from datetime import datetime, timedelta
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)
import pytz

# --- Параметры ---
WORK_START = 8
WORK_END = 22
ADMIN_CHAT_ID = 755215773
TIMEZONE = "Europe/Moscow"

# --- Проверка переменных окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан! Проверьте переменные окружения.")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задан! Проверьте переменные окружения.")

# --- Подключение к базе ---
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    if WORK_START <= now.hour < WORK_END:
        if update.message.from_user.id == ADMIN_CHAT_ID:
            keyboard = [
                [InlineKeyboardButton("Добавить шаблон", callback_data="admin_add_template")],
                [InlineKeyboardButton("Посмотреть записи", callback_data="admin_view_slots")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("Записаться", callback_data="choose_service")],
                [InlineKeyboardButton("Мои записи", callback_data="my_slots")]
            ]
        await update.message.reply_text(
            "Здравствуйте! Выберите действие:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("Бот работает с 08:00 до 22:00 по Москве.")

# --- Обработка кнопок ---
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # --- Выбор услуги ---
    if query.data == "choose_service" and user_id != ADMIN_CHAT_ID:
        keyboard = [
            [InlineKeyboardButton("Маникюр", callback_data="service_manicure")],
            [InlineKeyboardButton("Педикюр", callback_data="service_pedicure")]
        ]
        await query.edit_message_text("Выберите услугу:", reply_markup=InlineKeyboardMarkup(keyboard))

    # --- Выбор даты ---
    elif query.data.startswith("service_") and user_id != ADMIN_CHAT_ID:
        service = query.data.split("_")[1]
        context.user_data['service'] = service
        keyboard = []
        for day_offset in range(0, 30):
            day_date = datetime.now(pytz.timezone(TIMEZONE)).date() + timedelta(days=day_offset)
            keyboard.append([InlineKeyboardButton(day_date.strftime("%Y-%m-%d"), callback_data=f"day_{day_date}")])
        await query.edit_message_text(f"Вы выбрали {service}. Теперь выберите дату:", reply_markup=InlineKeyboardMarkup(keyboard))

    # --- Показ слотов ---
    elif query.data.startswith("day_") and user_id != ADMIN_CHAT_ID:
        day_str = query.data.split("_")[1]
        service = context.user_data.get('service')
        cursor.execute(
            "SELECT id, time, status FROM slots WHERE date=%s AND service=%s ORDER BY time",
            (day_str, service)
        )
        slots = cursor.fetchall()
        keyboard = []
        for slot in slots:
            slot_id, time, status = slot
            if status == 'free':
                keyboard.append([InlineKeyboardButton(time, callback_data=f"slot_{slot_id}")])
        if not keyboard:
            await query.edit_message_text(f"На {day_str} нет свободных окон.")
        else:
            await query.edit_message_text(
                f"Свободные окна на {day_str} ({service}):",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    # --- Запись на слот ---
    elif query.data.startswith("slot_") and user_id != ADMIN_CHAT_ID:
        slot_id = int(query.data.split("_")[1])
        cursor.execute("SELECT status, service FROM slots WHERE id=%s", (slot_id,))
        row = cursor.fetchone()
        if not row:
            await query.edit_message_text("Ошибка: слот не найден.")
            return
        status, service = row
        if status != 'free':
            await query.edit_message_text("Извините, это окно уже занято.")
            return
        cursor.execute(
            "UPDATE slots SET status='booked', client_name=%s WHERE id=%s",
            (user_id, slot_id)
        )
        conn.commit()
        await query.edit_message_text(f"Вы успешно записаны на {service}!")
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"Новая запись от {user_id} на {service}, слот {slot_id}"
        )

# --- Основная функция ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    print("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
