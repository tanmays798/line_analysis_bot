import requests
import telegram
import asyncio
from time import time
from datetime import datetime
import logging
import os
from fractions import Fraction
from requests.exceptions import RequestException

# Configure logging to output to both console and the TempLogs.txt file
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
    ]
)

# Configuration
BET365_API_URL = "https://api.b365api.com/v1/bet365/inplay"
BET365_API_TOKEN = "81076-iwINiVUEOHAr7E"
TELEGRAM_CHAT_IDS = {
    "soft": "-1002465682648",
    "medium": "-1002350124606",
    "hard": "-1002256818924"
}

# API Parameters
API_PARAMS = {
    'token': BET365_API_TOKEN,
    'sport_id': 1,
    'skip_esports': 1,
    'odds_market': '2,3,5,6'  # Asian Handicap and Over/Under
}

# Notification settings
LINE_CHANGE_THRESHOLD = 120  # 120 seconds for notification
ODDS_MARKETS = ['1_2', '1_3', '1_5', '1_6']  # Half-time/Full-time Asian Handicap & Over/Under

# Global state
last_lines = {}
last_triggered_severity = {}  # Initialize for tracking previous severity triggers

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


# Function to send notification to a specific Telegram channel
async def send_telegram_message(channel, message):
    try:
        bot = telegram.Bot(token="6665435772:AAFOBr9WHnexUFgBSZ7ecDLFry6I1sH4CAg")
        logging.debug(f"Sending message to {channel}: {message}")
        await bot.send_message(chat_id=TELEGRAM_CHAT_IDS[channel], text=message)
    except telegram.error.TelegramError as e:
        logging.error(f"Failed to send message to {channel} channel: {e}")


def extract_relevant_odds(odds_data):
    relevant_odds = {}
    for market_id, market_entries in odds_data.items():
        if market_id in ODDS_MARKETS:
            for entry in market_entries:
                if entry.get("handicap") or entry.get("goal_line"):
                    key = f"{entry.get('market_name', 'Unknown Market')} - {entry.get('handicap', entry.get('goal_line', ''))}"
                    relevant_odds[key] = entry.get('odds')
    return relevant_odds


async def get_live_events():
    try:
        response = requests.get(BET365_API_URL, params=API_PARAMS, timeout=10)
        response.raise_for_status()
        data = response.json()
        return [
            {
                "id": event['id'],
                "name": f"{event.get('league', 'Unknown League')} - {event.get('name', 'Unknown Event')}",
                "status": event.get('status'),
                "odds": extract_relevant_odds(event['odds'])
            }
            for event in data.get('results', []) if 'odds' in event
        ]
    except RequestException as e:
        logging.error(f"Error fetching live events: {e}")
        return []


def convert_odds_to_float(odds_str):
    try:
        return float(Fraction(odds_str))
    except (ValueError, TypeError) as e:
        logging.error(f"Could not convert odds '{odds_str}' to float: {e}")
        return None


async def check_line_changes(event):
    global last_lines, last_triggered_severity
    event_id = event['id']
    event_timestamp = time()

    if event_id not in last_lines:
        last_lines[event_id] = {
            key: {"value": convert_odds_to_float(value), "timestamp": event_timestamp}
            for key, value in event['odds'].items() if convert_odds_to_float(value) is not None
        }
        last_triggered_severity[event_id] = {"soft": False, "medium": False, "hard": False}
        return

    for key, current_value_str in event['odds'].items():
        current_value = convert_odds_to_float(current_value_str)
        if key in last_lines[event_id] and current_value is not None:
            previous_value = last_lines[event_id][key]['value']
            line_change = abs(current_value - previous_value)
            if line_change >= 0.5:
                severity = "soft" if line_change == 0.5 else "medium" if line_change == 0.75 else "hard"
                if not last_triggered_severity[event_id][severity]:
                    # await send_telegram_message(
                    #     severity,
                    #     f"⚽️ {event['name']}: {key} changed from {previous_value} to {current_value} (Δ: {line_change})"
                    # )
                    last_triggered_severity[event_id][severity] = True

    last_lines[event_id] = {
        key: {"value": convert_odds_to_float(value), "timestamp": event_timestamp}
        for key, value in event['odds'].items() if convert_odds_to_float(value) is not None
    }


async def cleanup_ended_events():
    ended_statuses = {3, 8, 9, 99}
    for event_id in list(last_lines.keys()):
        if last_lines[event_id].get('status') in ended_statuses:
            last_lines.pop(event_id, None)
            last_triggered_severity.pop(event_id, None)
            logging.debug(f"Removed ended event: {event_id}")


async def main():
    while True:
        try:
            live_events = await get_live_events()
            for event in live_events:
                await check_line_changes(event)
            await cleanup_ended_events()
            await asyncio.sleep(10)
        except KeyboardInterrupt:
            logging.info("Script interrupted by user. Exiting...")
            break
        except Exception as e:
            logging.error(f"Unexpected error: {str(e)}")
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
