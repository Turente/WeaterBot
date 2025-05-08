import logging
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    CallbackContext,
)
import requests
from cachetools import TTLCache
import pytz

# Конфигурация
API_KEY = "апишка"
TELEGRAM_TOKEN = "токен"
DEFAULT_CITY = "Москва"
CACHE_TIME = 1800  # 30 минут кеширования
NOTIFICATION_TIME = time(hour=7, minute=0, tzinfo=pytz.timezone("Europe/Moscow"))

# Кеши
weather_cache = TTLCache(maxsize=100, ttl=CACHE_TIME)
forecast_cache = TTLCache(maxsize=50, ttl=3600)  # Кеш для прогнозов на 1 час

WEATHER_ICONS = {
    "01": ("☀️", "Ясно"),
    "02": ("⛅", "Небольшая облачность"),
    "03": ("☁️", "Облачно"),
    "04": ("☁️", "Пасмурно"),
    "09": ("🌧️", "Небольшой дождь"),
    "10": ("🌦️", "Дождь"),
    "11": ("⛈️", "Гроза"),
    "13": ("❄️", "Снег"),
    "50": ("🌫️", "Туман"),
}

def get_weather_icon(weather_code: str) -> tuple:
    """Возвращает эмодзи и описание по коду погоды"""
    code_prefix = weather_code[:2]
    return WEATHER_ICONS.get(code_prefix, ("🌤️", "Нет данных"))

def fetch_weather(city: str, is_forecast: bool = False) -> dict:
    """Запрашивает погоду с кешированием"""
    cache_key = f"{city}_forecast" if is_forecast else f"{city}_current"
    if cache_key in weather_cache:
        return weather_cache[cache_key]

    url = (
        f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={API_KEY}&units=metric&lang=ru"
        if is_forecast
        else f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric&lang=ru"
    )
    response = requests.get(url)
    data = response.json()

    if data.get("cod") not in [200, "200"]:
        raise Exception(f"Ошибка API: {data.get('message')}")

    weather_cache[cache_key] = data
    return data

def build_weather_message(current: dict, forecast: dict, city: str) -> str:
    """Формирует сообщение с текущей погодой"""
    current_weather = current["weather"][0]
    icon, description = get_weather_icon(current_weather["icon"])
    temp = current["main"]["temp"]
    feels_like = current["main"]["feels_like"]
    pop = forecast["list"][0].get("pop", 0) * 100

    # Используем время из данных погоды (текущее время сервера)
    timestamp = current.get('dt', datetime.now().timestamp())
    time_str = datetime.fromtimestamp(timestamp).strftime('%H:%M')

    msg = [
        f"⏱ <i>Обновлено: {time_str}</i>",
        f"{icon} <b>Погода в {city}</b>",
        f"• <i>{description}</i>",
        f"• Температура: <b>{temp}°C</b> (ощущается как {feels_like}°C)",
        f"• Ветер: {current['wind']['speed']} м/с",
        f"• Влажность: {current['main']['humidity']}%",
        f"• Вероятность осадков: {pop:.0f}%",
    ]
    return "\n".join(msg)

async def get_3day_forecast(city: str) -> str:
    """Получает и форматирует прогноз на 3 дня"""
    try:
        data = fetch_weather(city, is_forecast=True)

        if not data or not isinstance(data, dict) or 'list' not in data:
            return "⚠️ Не получилось загрузить прогноз"

        daily_forecasts = {}
        for forecast in data['list']:
            date = datetime.fromtimestamp(forecast['dt']).strftime('%Y-%m-%d')
            if date not in daily_forecasts:
                daily_forecasts[date] = []
            daily_forecasts[date].append(forecast)

        message = ["<b>🌦️ Прогноз на 3 дня:</b>"]
        day_names = ["Сегодня", "Завтра", "Послезавтра"]

        for i, (date, forecasts) in enumerate(list(daily_forecasts.items())[:3]):
            # Дневная температура (максимальная за день)
            day_temp = round(max(f['main']['temp'] for f in forecasts))

            # Ночная температура (только часы с 0 до 6)
            night_forecasts = [
                f['main']['temp']
                for f in forecasts
                if datetime.fromtimestamp(f['dt']).hour < 6
            ]

            # Если нет ночных прогнозов, используем минимальную за день
            night_temp = round(min(night_forecasts)) if night_forecasts else round(min(f['main']['temp'] for f in forecasts))

            weather = forecasts[0]['weather'][0]
            icon, desc = get_weather_icon(weather['icon'])
            pop = round(max(f.get('pop', 0) * 100 for f in forecasts))

            message.append(
                f"\n\n{icon} <b>{day_names[i]} ({date})</b>"
                f"\n• {desc}"
                f"\n• Температура: днем {day_temp}°C, ночью {night_temp}°C"
                f"\n• Вероятность осадков: {pop}%"
                f"\n• Ветер: {forecasts[0]['wind']['speed']} м/с"
            )

        return "\n".join(message)

    except Exception as e:
        logging.error(f"Forecast error: {str(e)}")
        return f"⚠️ Ошибка при формировании прогноза: {str(e)}"

async def send_daily_notification(context: CallbackContext) -> None:
    """Отправляет ежедневное уведомление"""
    try:
        current = fetch_weather(DEFAULT_CITY)
        forecast = fetch_weather(DEFAULT_CITY, is_forecast=True)
        message = build_weather_message(current, forecast, DEFAULT_CITY)
        await context.bot.send_message(context.job.chat_id, text=message, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка уведомления: {e}")

def get_weather_keyboard() -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с текущим временем для уникальности"""
    keyboard = [
        [InlineKeyboardButton(f"🔄 Обновить ({datetime.now().strftime('%H:%M')})",
                            callback_data="refresh")],
        [InlineKeyboardButton("🌦️ Прогноз на 3 дня", callback_data="forecast")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: CallbackContext) -> None:
    """Обработка команды /start"""
    chat_id = update.effective_chat.id
    context.user_data["city"] = DEFAULT_CITY

    context.job_queue.run_daily(
        send_daily_notification,
        time=NOTIFICATION_TIME,
        days=(0, 1, 2, 3, 4, 5, 6),
        chat_id=chat_id,
        name=str(chat_id),
    )

    await update.message.reply_text(
        f"Привет! Я буду присылать погоду в {DEFAULT_CITY} каждый день в 7:00.\n"
        "Используй /weather <город> для смены города.",
        reply_markup=get_weather_keyboard()
    )

async def weather(update: Update, context: CallbackContext) -> None:
    """Обработка команды /weather"""
    city = " ".join(context.args) if context.args else DEFAULT_CITY
    context.user_data["city"] = city

    try:
        current = fetch_weather(city)
        forecast = fetch_weather(city, is_forecast=True)
        message = build_weather_message(current, forecast, city)
    except Exception as e:
        message = f"⚠️ Ошибка: {e}"

    await update.message.reply_text(
        text=message,
        parse_mode="HTML",
        reply_markup=get_weather_keyboard()
    )

async def handle_button_click(update: Update, context: CallbackContext) -> None:
    """Обрабатывает все нажатия кнопок"""
    query = update.callback_query
    await query.answer()

    try:
        city = context.user_data.get('city', DEFAULT_CITY)

        if query.data == 'refresh':
            current = fetch_weather(city)
            forecast = fetch_weather(city, is_forecast=True)
            message = build_weather_message(current, forecast, city)
            keyboard = get_weather_keyboard()  # Обновляем клавиатуру

        elif query.data == 'forecast':
            await query.answer("⌛ Формирую прогноз...")
            message = await get_3day_forecast(city)
            keyboard = get_weather_keyboard()  # Обновляем клавиатуру

        await query.edit_message_text(
            text=message,
            parse_mode='HTML',
            reply_markup=keyboard  # Используем обновленную клавиатуру
        )

    except Exception as e:
        logging.error(f"Button handler error: {str(e)}")
        await query.answer("⚠️ Произошла ошибка")

def main() -> None:
    """Запуск бота"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Настройка JobQueue
    application.job_queue.scheduler.configure(timezone=pytz.timezone("Europe/Moscow"))

    # Обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("weather", weather))
    application.add_handler(CallbackQueryHandler(handle_button_click))

    application.run_polling()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
