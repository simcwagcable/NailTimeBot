import os
from datetime import datetime, timedelta
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# --- Параметры ---
WORK_START = 8
WORK_END = 22
ADMIN_CHAT_ID = 755215773

# --- Подключение к базе ---
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()

# --- /start ---
def start(update: Update, context: CallbackContext):
    now = datetime.now()
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
        update.message.reply_text("Здравствуйте! Выберите действие:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        update.message.reply_text("Бот работает с 08:00 до 22:00.")

# --- Обработка кнопок ---
def button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id

    # --- Выбор услуги ---
    if query.data == "choose_service" and user_id != ADMIN_CHAT_ID:
        keyboard = [
            [InlineKeyboardButton("Маникюр", callback_data="service_manicure")],
            [InlineKeyboardButton("Педикюр", callback_data="service_pedicure")]
        ]
        query.edit_message_text("Выберите услугу:", reply_markup=InlineKeyboardMarkup(keyboard))

    # --- Выбор даты ---
    elif query.data.startswith("service_") and user_id != ADMIN_CHAT_ID:
        service = query.data.split("_")[1]
        context.user_data['service'] = service
        keyboard = []
        for day_offset in range(0, 30):
            day_date = datetime.now().date() + timedelta(days=day_offset)
            keyboard.append([InlineKeyboardButton(day_date.strftime("%Y-%m-%d"), callback_data=f"day_{day_date}")])
        query.edit_message_text(f"Вы выбрали {service}. Теперь выберите дату:", reply_markup=InlineKeyboardMarkup(keyboard))

    # --- Показ слотов ---
    elif query.data.startswith("day_") and user_id != ADMIN_CHAT_ID:
        day_str = query.data.split("_")[1]
        service = context.user_data.get('service')
        cursor.execute("SELECT id, time, status FROM slots WHERE date=%s AND service=%s ORDER BY time", (day_str, service))
        slots = cursor.fetchall()
        keyboard = []
        for slot in slots:
            slot_id, time, status = slot
            if status == 'free':
                keyboard.append([InlineKeyboardButton(time, callback_data=f"slot_{slot_id}")])
        if not keyboard:
            query.edit_message_text(f"На {day_str} нет свободных окон.")
        else:
            query.edit_message_text(f"Свободные окна на {day_str} ({service}):", reply_markup=InlineKeyboardMarkup(keyboard))

    # --- Запись на слот ---
    elif query.data.startswith("slot_") and user_id != ADMIN_CHAT_ID:
        slot_id = int(query.data.split("_")[1])
        cursor.execute("SELECT status, service FROM slots WHERE id=%s", (slot_id,))
        status, service = cursor.fetchone()
        if status != 'free':
            query.edit_message_text("Извините, это окно уже занято.")
            return
        cursor.execute("UPDATE slots SET status='booked', client_name=%s WHERE id=%s", (user_id, slot_id))
        conn.commit()
        query.edit_message_text(f"Вы успешно записаны на {service}!")
        context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"Новая запись от {user_id} на {service}, окно {slot_id}")

# --- Основная функция ---
def main():
    updater = Updater(os.getenv("BOT_TOKEN"), use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
