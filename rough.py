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
BET365_EVENTS_API_URL = "https://api.b365api.com/v3/events/inplay"
BET365_ODDS_API_URL = "https://api.b365api.com/v2/event/odds"
BET365_API_TOKEN = "81076-iwINiVUEOHAr7E"

# API Parameters
EVENTS_API_PARAMS = {
    'token': BET365_API_TOKEN,
    'sport_id': 1,
    # 'skip_esports': 1,
    # 'odds_market': '2,3,5,6'  # Asian Handicap and Over/Under
}
ODDS_API_PARAMS = {
    'token': BET365_API_TOKEN,
    'event_id': '9145038',
    'odds_market': '2,3,5,6'  # Asian Handicap and Over/Under
}

# try:
#     # response = requests.get(BET365_EVENTS_API_URL, params=EVENTS_API_PARAMS)
#     # response.raise_for_status()
#     # data = response.json()
#     # print(data)
#     odds_response = requests.get(BET365_ODDS_API_URL, params=ODDS_API_PARAMS)
#     odds_response.raise_for_status()
#     odds_data = odds_response.json()
#     print(odds_data)
# except RequestException as e:
#     logging.error(f"Error fetching live events: {e}")
#     # return []


a = [
    {"id": 7, "time": 7, "value": -0.5},
    {"id": 6, "time": 6, "value": -0.5},
    {"id": 5, "time": 5, "value": -0.5},
    {"id": 4, "time": 4, "value": -0.5},
    {"id": 3, "time": 3, "value": 0},
    {"id": 2, "time": 2, "value": 0.5},
    {"id": 1, "time": 1, "value": 0.5}
]

cleaned_a = [a[-1]]
last_value = a[-1].get("value", None)
for data in reversed(a[:-1]):
    if data.get("value", None) != last_value:
        cleaned_a.append(data)
        last_value = data.get("value", None)
print(cleaned_a)

# cleaned_a = []
# next_value = None
# for i in range(len(a))
#     if a[i]
#         cleaned_a.append(data)
#         last_value = data.get("value", None)
# print(cleaned_a)

event_details = {'id': '8443522', 'sport_id': '1', 'time': '1732439700', 'time_status': '1', 'league': {'id': '22', 'name': 'Czech Republic 3. Ligy', 'cc': 'cz'}, 'home': {'id': '295594', 'name': 'Hradec Kralove B', 'image_id': '607060', 'cc': 'cz'}, 'away': {'id': '297862', 'name': 'Mladá Boleslav B', 'image_id': '607062', 'cc': 'cz'}, 'o_away': {'id': '295595', 'name': 'Mlada Boleslav II', 'image_id': '607062', 'cc': 'cz'}, 'ss': '1-2', 'scores': {'1': {'home': '1', 'away': '1'}, '2': {'home': '1', 'away': '2'}}, 'bet365_id': '165003117', 'timer': {'tm': 92, 'ts': 39, 'tt': '1', 'ta': 4, 'md': 1}, 'stats': {'attacks': ['112', '92'], 'ball_safe': ['66', '64'], 'corners': ['4', '6'], 'corner_h': ['1', '4'], 'dangerous_attacks': ['56', '45'], 'goals': ['1', '2'], 'injuries': ['1', '0'], 'off_target': ['4', '2'], 'on_target': ['6', '3'], 'penalties': ['0', '0'], 'possession_rt': ['50', '50'], 'redcards': ['1', '0'], 'substitutions': ['3', '2'], 'yellowcards': ['1', '3'], 'yellowred_cards': ['0', '0']}}
event_names = {'8443522': {
    "name": ""
}}