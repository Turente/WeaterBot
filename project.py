import logging
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, JobQueue
import requests
from cachetools import TTLCache
import pytz

# Конфигурация
API_KEY = "ваш_api_ключ_openweathermap"
TELEGRAM_TOKEN = "ваш_токен_бота"
DEFAULT_CITY = "Москва"  # Город по умолчанию
CACHE_TIME = 1800  # 30 минут кеширования
NOTIFICATION_TIME = time(hour=7, minute=0, tzinfo=pytz.timezone("Europe/Moscow"))  # 7:00 по Москве

# Кеш для хранения данных
weather_cache = TTLCache(maxsize=100, ttl=CACHE_TIME)

# Соответствие кодов погоды эмодзи и описаниям
WEATHER_ICONS = {
    "01": ("☀️", "Ясно"),
    "02": ("⛅", "Небольшая облачность"),
    "03": ("☁️", "Облачно"),
    "04": ("☁️", "Пасмурно"),
    "09": ("🌧️", "Небольшой дождь"),
    "10": ("🌦️", "Дождь"),
    "11": ("⛈️", "Гроза"),
    "13": ("❄️", "Снег"),
    "50": ("🌫️", "Туман")
}

def get_weather_icon(weather_code: str) -> tuple:
    """Возвращает эмодзи и описание по коду погоды."""
    code_prefix = weather_code[:2]
    return WEATHER_ICONS.get(code_prefix, ("🌤️", "Нет данных"))

def fetch_weather(city: str, is_forecast: bool = False) -> dict:
    """Запрашивает погоду с кешированием."""
    cache_key = f"{city}_forecast" if is_forecast else f"{city}_current"
    if cache_key in weather_cache:
        return weather_cache[cache_key]

    url = (
        f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={API_KEY}&units=metric&lang=ru"
        if is_forecast
        else f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric&lang=ru"
    )
    response = requests.get(url)
    data = response.json()

    if data.get("cod") not in [200, "200"]:
        raise Exception(f"Ошибка API: {data.get('message')}")

    weather_cache[cache_key] = data
    return data

def build_weather_message(current: dict, forecast: dict, city: str) -> str:
    """Форматирует сообщение для Telegram."""
    current_weather = current["weather"][0]
    icon, description = get_weather_icon(current_weather["icon"])
    temp = current["main"]["temp"]
    feels_like = current["main"]["feels_like"]
    pop = forecast["list"][0].get("pop", 0) * 100  # Вероятность осадков (0-100%)

    msg = [
        f"{icon} <b>Погода в {city}</b>",
        f"• <i>{description}</i>",
        f"• Температура: <b>{temp}°C</b> (ощущается как {feels_like}°C)",
        f"• Ветер: {current['wind']['speed']} м/с",
        f"• Влажность: {current['main']['humidity']}%",
        f"• Вероятность осадков: {pop:.0f}%",
        "\n<b>Прогноз на сегодня:</b>"
    ]

    today = datetime.now().strftime("%Y-%m-%d")
    today_forecast = [f for f in forecast["list"] if datetime.fromtimestamp(f["dt"]).strftime("%Y-%m-%d") == today]
    
    if today_forecast:
        day_temp = max(f["main"]["temp"] for f in today_forecast)
        night_temp = min(f["main"]["temp"] for f in today_forecast if datetime.fromtimestamp(f["dt"]).hour < 6)
        pop_day = max(f.get("pop", 0) * 100 for f in today_forecast)
        
        msg.append(
            f"\n• День: <b>{day_temp}°C</b>, Ночь: <b>{night_temp}°C</b>"
            f"\n• Дождь: {pop_day:.0f}%"
        )

    return "\n".join(msg)

def send_daily_notification(context: CallbackContext) -> None:
    """Отправляет уведомление о погоде в 7:00."""
    job = context.job
    try:
        current = fetch_weather(DEFAULT_CITY)
        forecast = fetch_weather(DEFAULT_CITY, is_forecast=True)
        message = build_weather_message(current, forecast, DEFAULT_CITY)
        context.bot.send_message(job.context, text=message, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления: {e}")

def start(update: Update, context: CallbackContext) -> None:
    """Обработка команды /start."""
    chat_id = update.effective_chat.id
    context.user_data["city"] = DEFAULT_CITY
    
    # Добавляем задачу на ежедневное уведомление
    context.job_queue.run_daily(
        send_daily_notification,
        time=NOTIFICATION_TIME,
        days=(0, 1, 2, 3, 4, 5, 6),
        context=chat_id,
        name=str(chat_id)
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")],
        [InlineKeyboardButton("🌦️ Прогноз на 3 дня", callback_data="forecast")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"Привет! Я буду присылать погоду в {DEFAULT_CITY} каждый день в 7:00.\n"
        "Используй /weather <город> для смены города.",
        reply_markup=reply_markup
    )

def weather(update: Update, context: CallbackContext) -> None:
    """Обработка команды /weather."""
    city = " ".join(context.args) if context.args else DEFAULT_CITY
    context.user_data["city"] = city
    
    try:
        current = fetch_weather(city)
        forecast = fetch_weather(city, is_forecast=True)
        message = build_weather_message(current, forecast, city)
    except Exception as e:
        message = f"⚠️ Ошибка: {e}"

    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")],
        [InlineKeyboardButton("🌦️ Прогноз на 3 дня", callback_data="forecast")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(text=message, parse_mode="HTML", reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext) -> None:
    """Обработка нажатий кнопок."""
    query = update.callback_query
    query.answer()
    city = context.user_data.get("city", DEFAULT_CITY)

    if query.data == "refresh":
        try:
            current = fetch_weather(city)
            forecast = fetch_weather(city, is_forecast=True)
            message = build_weather_message(current, forecast, city)
        except Exception as e:
            message = f"⚠️ Ошибка: {e}"
        query.edit_message_text(text=message, parse_mode="HTML")

def main() -> None:
    """Запуск бота."""
    updater = Updater(TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher
    job_queue = updater.job_queue

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("weather", weather))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()