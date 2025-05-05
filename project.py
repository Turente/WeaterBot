import requests
from datetime import datetime, timedelta

API_KEY = "Ваш_API"  # Замените на ваш ключ
CITY = "Москва"  # Или любой другой город

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

def get_current_weather(api_key: str, city: str) -> dict:
    """Запрос текущей погоды."""
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric&lang=ru"
    response = requests.get(url)
    data = response.json()
    if data.get("cod") != 200:
        raise Exception(f"Ошибка API: {data.get('message')}")
    return data

def get_forecast(api_key: str, city: str) -> dict:
    """Запрос прогноза."""
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={api_key}&units=metric&lang=ru"
    response = requests.get(url)
    data = response.json()
    if data.get("cod") != "200":
        raise Exception(f"Ошибка API: {data.get('message')}")
    return data

def format_weather_message(current: dict, forecast: dict, city: str) -> str:
    """Форматирует данные для Telegram."""
    # Текущая погода
    current_weather = current["weather"][0]
    icon, description = get_weather_icon(current_weather["icon"])
    temp = current["main"]["temp"]
    feels_like = current["main"]["feels_like"]
    
    msg = [
        f"{icon} <b>Погода в {city}</b>",
        f"• <i>{description}</i>",
        f"• Температура: <b>{temp}°C</b> (ощущается как {feels_like}°C)",
        f"• Ветер: {current['wind']['speed']} м/с",
        f"• Влажность: {current['main']['humidity']}%",
        "\n<b>Прогноз на 3 дня:</b>"
    ]

    # Прогноз
    daily_forecasts = {}
    for item in forecast["list"]:
        date = datetime.fromtimestamp(item["dt"]).strftime("%Y-%m-%d")
        if date not in daily_forecasts:
            daily_forecasts[date] = []
        daily_forecasts[date].append(item)

    for i, (date, items) in enumerate(daily_forecasts.items()):
        if i >= 3:
            break
        day_temp = max(f["main"]["temp"] for f in items)
        night_temp = min(f["main"]["temp"] for f in items if datetime.fromtimestamp(f["dt"]).hour < 6)
        weather = items[0]["weather"][0]
        icon, desc = get_weather_icon(weather["icon"])
        
        msg.append(
            f"\n{icon} <b>{datetime.strptime(date, '%Y-%m-%d').strftime('%d.%m')}</b>: "
            f"{desc}\n"
            f"• День: <b>{day_temp}°C</b>, Ночь: <b>{night_temp}°C</b>"
        )

    return "\n".join(msg)

if __name__ == "__main__":
    try:
        current = get_current_weather(API_KEY, CITY)
        forecast = get_forecast(API_KEY, CITY)
        print(format_weather_message(current, forecast, CITY))
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")