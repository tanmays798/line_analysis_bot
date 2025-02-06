import asyncio
import datetime
import logging
import statistics
import os
from dotenv import load_dotenv
import requests
from typing import List, Dict
from telegram import Bot
from telegram.request import HTTPXRequest
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Set the minimum logging level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Log format
    datefmt='%Y-%m-%d %H:%M:%S',  # Date-time format
    filename='bot.log',  # Optional: Log to a file
    filemode='a'  # Append mode for file
)


class LineChangeDetector:
    def __init__(self, events_api_url: str, odds_api_url: str, betsapi_token: str):
        self.events_api_url = events_api_url
        self.odds_api_url = odds_api_url
        self.betsapi_token = betsapi_token
        self.last_processed_ids = {}  # Track the last processed ID for each event
        self.live_event_details = {}
        self.line_types = {
            "1_2": "Asian Handicap",
            "1_3": "Goal Line",
            "1_5": "1st Half Asian Handicap",
            "1_6": "1st Half Goal Line"
        }
        self.alerts_channels = {
            "SOFT": os.getenv("SOFT_ALERTS_CHANNEL"),
            "MEDIUM": os.getenv("MEDIUM_ALERTS_CHANNEL"),
            "HARD": os.getenv("HARD_ALERTS_CHANNEL")
        }

    def clean_events(self, event_list: list):
        for event_id in list(self.live_event_details.keys()):
            if event_id not in event_list:
                del self.live_event_details[event_id]
        for event_id in list(self.last_processed_ids.keys()):
            if event_id not in event_list:
                del self.last_processed_ids[event_id]

    def fetch_live_events(self) -> List[Dict]:
        params = {
            'token': self.betsapi_token,
            'sport_id': 1,
        }
        response = requests.get(url=BET365_EVENTS_API_URL,
                                params=params)
        response.raise_for_status()
        events_data = response.json()
        return events_data.get("results", [])

    def fetch_event_odds(self, event_id: str) -> dict:
        params = {
            'token': self.betsapi_token,
            'event_id': event_id,
            'odds_market': '2,3,5,6'  # Only the four types of lines we need
        }
        odds_response = requests.get(BET365_ODDS_API_URL, params=params)
        odds_response.raise_for_status()
        odds_data = odds_response.json()
        return odds_data.get("results", {}).get("odds", {})

    async def detect_changes(self, event_id: str, line_type: str, data: list):
        if not data:
            return []

        # for line_type in lines:
        changes = []
        recent_data = []

        def get_float(x):
            return float(x)

        def check_open_odds(line_type_var, event_data_var):
            """Will return -1 for dash data and 1 for valid data"""
            if line_type_var == "1_2" or line_type_var == "1_5":
                if event_data_var['home_od'] == '-' or event_data_var['away_od'] == '-':
                    return -1
            elif line_type_var == "1_3" or line_type_var == "1_6":
                return -1
            else:
                return 1

        # Filter data up to the last processed ID for this event
        last_processed_id = self.last_processed_ids.get(event_id, {}).get(line_type, {}).get("id", None)
        if last_processed_id is None:
            try:
                self.last_processed_ids[event_id] = self.last_processed_ids.get(event_id, {})
                self.last_processed_ids[event_id][line_type] = {
                    "id": data[0]["id"],
                    "value": statistics.fmean(map(get_float, data[0]['handicap'].split(',')))
                    # This is to handle cases where values are like "1.0,1.5" where actual value is 1.25
                }
            except Exception as e:
                logging.error(f"{event_id} | {line_type} | {e}")

            return []

        try:
            new_data = []
            # We ignore the last data point of the data set as it would be discarded naturally in this logic
            # This loop is in descending order from latest data point to start data point
            for i in range(1, len(data) - 1):
                if statistics.fmean(map(get_float, data[i]['handicap'].split(','))) != statistics.fmean(
                        map(get_float, data[i - 1]['handicap'].split(','))):
                    continue
                elif check_open_odds(line_type, data[i]) == -1:
                    continue
                elif check_open_odds(line_type, data[i - 1]) == -1:
                    continue
                else:
                    new_data.append(data[i - 1])

        except Exception as e:
            logging.error(f"In new logic for valid points | {event_id} | {line_type} | {e}")
            pass

        # Remove data points with no odds data now to avoid false alerts
        # This is not needed after putting the above logic block but still keeping for safety
        try:
            clean_odds_data = []

            for event_data in new_data:
                if line_type == "1_2" or line_type == "1_5":
                    if event_data['home_od'] == '-' or event_data['away_od'] == '-':
                        continue
                    else:
                        clean_odds_data.append(event_data)
                elif line_type == "1_3" or line_type == "1_6":
                    if event_data['over_od'] == '-' or event_data['under_od'] == '-':
                        continue
                    else:
                        clean_odds_data.append(event_data)

            temp_data = list(clean_odds_data)
            new_data = temp_data

        except Exception as e:
            logging.error(f"In Cleaning Odds Data | {event_id} | {line_type} | {e}")

        # Clean data by removing consecutive duplicate values
        try:
            cleaned_data = [new_data[-1]]
            last_value = statistics.fmean(
                map(get_float, (new_data[-1]['handicap'].replace("+", '')).split(',')))

            for data_value in reversed(new_data[:-1]):
                if statistics.fmean(
                        map(get_float, data_value['handicap'].split(','))) != last_value:
                    cleaned_data.append(data_value)
                    last_value = statistics.fmean(
                        map(get_float, data_value['handicap'].split(',')))
                # adding the below to use latest value appearance rather than the first value appearance
                # Refresh concept
                else:
                    cleaned_data[-1] = data_value

            # for entry in reversed(cleaned_data):
            # for entry in reversed(new_data):
            for entry in new_data:
                # if entry['id'] == last_processed_id:
                if entry['id'] <= last_processed_id:
                    break

                # Again this to skip the false positive cases where odds are '-'
                if line_type == "1_2" or line_type == "1_5":
                    if entry['home_od'] == '-' or entry['away_od'] == '-':
                        continue
                elif line_type == "1_3" or line_type == "1_6":
                    if entry['over_od'] == '-' or entry['under_od'] == '-':
                        continue
                recent_data.append(entry)

            if not recent_data:
                # print("no recent data")
                return []

        except Exception as e:
            logging.error(f"In Cleaning Duplicates | {event_id} | {line_type} | {e}")

        last_processed_value = self.last_processed_ids.get(event_id, {}).get(line_type, {}).get("value", None)

        for entry in reversed(recent_data):

            # the following is to bypass the data points
            # which were within the 150 seconds range from a penalty or red card
            current_data_time = entry.get("add_time", None)
            buffer_stop = self.live_event_details.get(event_id, {}).get("buffer_stop", None)
            if current_data_time is not None and buffer_stop is not None:
                if current_data_time < buffer_stop:
                    continue

            changes_data = {}
            entry_value = statistics.fmean(
                map(get_float, entry['handicap'].split(',')))
            if entry_value != last_processed_value:

                # This is to capture game time from odds api rather than events api
                # to get specific game data which the alert is for.
                try:
                    game_time = entry['time_str']
                except:
                    game_time = self.live_event_details.get(event_id, {}).get('game_time', '')

                if game_time is None:
                    game_time = "Prelive"
                else:
                    game_time = f"{game_time}'"

                # This is to capture goals data from odds api rather than inplay events api and to avoid processing
                # fake alerts in case of goals.
                last_processed_goals = self.last_processed_ids.get(event_id, {}).get("goals", None)
                try:
                    current_goals_data = entry.get('ss', '-')
                    if current_goals_data is None:
                        current_goals = last_processed_goals
                    else:
                        current_goals = current_goals_data.split('-')
                except Exception as e:
                    logging.error(f"In Goals Data | {event_id} | {line_type} | {e}")
                    continue

                if current_goals != last_processed_goals:
                    # logging.info(f"Goal detected within running data | "
                    #              f"last processed goals - {last_processed_goals} | "
                    #              f"Current goals - {current_goals} | "
                    #              f"Current Data - {game_time}' {entry}")

                    continue

                for line_data in reversed(cleaned_data):
                    # This to skip the false positive cases where odds are '-'
                    if line_type == "1_2" or line_type == "1_5":
                        if line_data['home_od'] == '-' or line_data['away_od'] == '-':
                            continue
                    elif line_type == "1_3" or line_type == "1_6":
                        if line_data['over_od'] == '-' or line_data['under_od'] == '-':
                            continue

                    # the following is to bypass the data points
                    # which were within the 150 seconds range from a penalty or red card
                    line_data_time = line_data.get("add_time", None)
                    if line_data_time is not None and buffer_stop is not None:
                        if line_data_time < buffer_stop:
                            continue

                    time_difference = int(entry['add_time']) - int(line_data['add_time'])
                    if time_difference <= 0:
                        continue
                    elif time_difference > 150:
                        break
                    current_handicap = statistics.fmean(map(get_float, entry['handicap'].split(',')))
                    next_handicap = statistics.fmean(map(get_float, line_data['handicap'].split(',')))
                    handicap_change = abs(current_handicap - next_handicap)

                    try:
                        change_type_flag = None
                        if time_difference <= 150:

                            print(event_id, line_type, "Handicap Change: ", handicap_change, time_difference)
                            if 0.5 <= handicap_change < 0.75:
                                change_type_flag = "SOFT"
                            elif 0.75 <= handicap_change < 1.0:
                                change_type_flag = "MEDIUM"
                            elif handicap_change >= 1.0:
                                change_type_flag = "HARD"
                            else:
                                continue
                            print(change_type_flag)
                            try:
                                if entry['ss'] != line_data['ss']:
                                    home_team = self.live_event_details.get(event_id, {}).get('home_team', '')
                                    away_team = self.live_event_details.get(event_id, {}).get('away_team', '')
                                    await logging_bot.sendMessage(
                                        text=f"{home_team} v {away_team} - {change_type_flag} -\n"
                                             f"{next_handicap} -> {current_handicap}\n"
                                             f"Goal detected within running data while alert "
                                             f"detection\n"
                                             f"{line_data['ss']} | {entry['ss']} \n"
                                             f"Current Data - {game_time}' {entry}\n"
                                             f"https://betsapi.com/rs/bet365/" \
                                             f"{event_id}/{home_team.replace(' ', '-')}-v-{away_team.replace(' ', '-')}"
                                        ,
                                        chat_id=LOGS_CHANNEL,
                                        disable_web_page_preview=True)
                                    logging.info(f"Goal detected within running data while alert detection | "
                                                 f"{event_id} |"
                                                 f"{line_data['ss']} | {entry['ss']} |"
                                                 f"Current Data - {game_time}' {entry}")
                                    continue
                            except Exception as e:
                                logging.error(f"Within alert - goal detection: {e}")
                                continue
                                # pass
                            if change_type_flag is not None:
                                if changes_data.get(change_type_flag, None) is None:

                                    home_team = self.live_event_details.get(event_id, {}).get('home_team', '')
                                    away_team = self.live_event_details.get(event_id, {}).get('away_team', '')
                                    if game_time != "Prelive":
                                        change_msg = f"⚽ {self.live_event_details.get(event_id, {}).get('league', '')}\n" \
                                                     f'⏱ {game_time} ' \
                                                     f"{home_team} " \
                                                     f"{'-'.join(self.live_event_details.get(event_id, {}).get('goals', []))} " \
                                                     f"{away_team}\n" \
                                                     f"<b>{self.line_types[line_type]}</b> " \
                                                     f"from <b>{next_handicap}</b> -> <b>{current_handicap}</b> " \
                                                     f"in {time_difference}s \n" \
                                                     f"https://betsapi.com/rs/bet365/" \
                                                     f"{event_id}/{home_team.replace(' ', '-')}" \
                                                     f"-v-" \
                                                     f"{away_team.replace(' ', '-')}"
                                    else:
                                        change_msg = f"Prelive🔜\n" \
                                                     f"⚽ {self.live_event_details.get(event_id, {}).get('league', '')}\n" \
                                                     f'⏱ ' \
                                                     f"{home_team} " \
                                                     f"{'-'.join(self.live_event_details.get(event_id, {}).get('goals', []))} " \
                                                     f"{away_team}\n" \
                                                     f"<b>{self.line_types[line_type]}</b> " \
                                                     f"from <b>{next_handicap}</b> -> <b>{current_handicap}</b> " \
                                                     f"in {time_difference}s \n" \
                                                     f"https://betsapi.com/rs/bet365/" \
                                                     f"{event_id}/{home_team.replace(' ', '-')}" \
                                                     f"-v-" \
                                                     f"{away_team.replace(' ', '-')}"


                                    changes_data[change_type_flag] = True

                                    # The following is the range filter based on previous alert data

                                    try:
                                        previous_alert_data = self.live_event_details.get(event_id, {}).get(
                                            f"last_{change_type_flag}_alert", None)
                                        if previous_alert_data is not None:
                                            current_direction = 1 if current_handicap - next_handicap > 0 else -1
                                            if current_direction == previous_alert_data[2]:
                                                if current_direction == 1:
                                                    if previous_alert_data[0] <= next_handicap < previous_alert_data[1]:
                                                        logging.info(f"Alert Stopped at Range Filter | "
                                                                     f"from <b>{next_handicap}</b>->"
                                                                     f"<b>{current_handicap}</b> | "
                                                                     f"{previous_alert_data}")
                                                        log_message = f"Alert Stopped at Range Filter \n\n" \
                                                                      f"Previous Data : {previous_alert_data} \n\n" \
                                                                      f"{change_msg}"
                                                        await logging_bot.sendMessage(text=log_message,
                                                                                      chat_id=LOGS_CHANNEL,
                                                                                      parse_mode='HTML',
                                                                                      disable_web_page_preview=True
                                                                                      )

                                                        continue

                                                if current_direction == -1:
                                                    if previous_alert_data[0] >= next_handicap > previous_alert_data[1]:
                                                        logging.info(f"Alert Stopped at Range Filter | "
                                                                     f"from <b>{next_handicap}</b>->"
                                                                     f"<b>{current_handicap}</b> | "
                                                                     f"{previous_alert_data}")
                                                        log_message = f"Alert Stopped at Range Filter \n\n" \
                                                                      f"Previous Data : {previous_alert_data} \n\n" \
                                                                      f"{change_msg}"
                                                        await logging_bot.sendMessage(text=log_message,
                                                                                      chat_id=LOGS_CHANNEL,
                                                                                      parse_mode='HTML',
                                                                                      disable_web_page_preview=True
                                                                                      )
                                                        continue

                                    except Exception as e:
                                        logging.error(f"In Range Filter | {e} | \n{change_msg}")

                                    await line_change_bot.sendMessage(text=change_msg,
                                                                      chat_id=self.alerts_channels.get(change_type_flag,
                                                                                                       LOGS_CHANNEL),
                                                                      parse_mode='HTML',
                                                                      disable_web_page_preview=True)

                                    # This is to update the last alert details to maintain range filter
                                    self.live_event_details[event_id][
                                        f"last_{change_type_flag}_alert"] = (next_handicap,
                                                                             current_handicap,
                                                                             1 if current_handicap - next_handicap > 0
                                                                             else -1)

                                    changes.append({
                                        "event_id": event_id,
                                        "change_type": change_type_flag,
                                        "handicap_change": handicap_change,
                                        "time_difference": time_difference,
                                        "from": entry,
                                        "to": line_data
                                    })
                                    logging.info(
                                        f"Alert Sent | "
                                        f"{change_type_flag}| {entry} | {line_data} | {cleaned_data} | {recent_data}")
                    except Exception as e:
                        logging.error(f"In Detecting Change | {event_id} | {line_type} | {e}")

                self.last_processed_ids[event_id]["goals"] = current_goals
            last_processed_value = entry_value
            self.last_processed_ids[event_id][line_type] = {
                "id": entry.get("id", None),
                "value": last_processed_value
            }

        return changes

    def get_blacklist(self):
        """Retrieve the blacklist."""
        return self.load_blacklist()


    def load_blacklist(self):
        """Load the blacklist from the JSON file."""
        if not os.path.exists(BLACKLIST_FILE):
            return set()
        with open(BLACKLIST_FILE, "r") as file:
            return set(json.load(file))


    async def process(self):

        # Fetch all live events
        live_events = self.fetch_live_events()

        # Fetch blacklisted leagues
        blacklist = self.get_blacklist()

        if not live_events:
            logging.info("No live events found.")
            return 0, []

        event_count = 0
        all_events = []
        for event in live_events:

            event_id = event.get("id")
            if not event_id:
                continue

            all_events.append(event_id)

            league_name = event.get("league", {}).get("name", None)

            # This is added to remove Escoccer games from processing.
            if 'esoccer' in league_name.lower():
                continue

            # This is to skip processing for blacklisted leagues
            if league_name.lower() in blacklist:
                continue

            # Moving away from 2` filter to considering pre - live data too
            try:
                game_time = event.get("timer", {}).get("tm", None)
                # if int(game_time) < 2 :
                if game_time is None:
                    game_time = 'Prelive'
            except Exception as e:
                logging.error(f"In Getting Game Time | {event} | e")
                game_time = None

            try:
                # Information to be captured and stored here - Id, Name, League, Time, Red Card, Penalties, Goals
                self.live_event_details[event["id"]] = self.live_event_details.get(event["id"], {})
                self.live_event_details[event["id"]]["home_team"] = event.get("home", {}).get("name", None)
                self.live_event_details[event["id"]]["away_team"] = event.get("away", {}).get("name", None)
                self.live_event_details[event["id"]]["league"] = league_name
                self.live_event_details[event["id"]]["game_time"] = game_time
                self.live_event_details[event["id"]]["goals"] = event.get("stats", {}).get("goals", None)
                self.live_event_details[event["id"]]["penalties"] = event.get("stats", {}).get("penalties", None)
                self.live_event_details[event["id"]]["red_cards"] = event.get("stats", {}).get("redcards", None)

            except Exception as e:
                logging.error(f"In Updating Live Event Details | {event} | {e}")

            # This is to avoid processing this event if there was a penalty or red card 150 seconds before now.
            buffer_stop = self.live_event_details.get(event_id, {}).get("buffer_stop", None)
            current_time = event.get("time", None)
            # logging.info(f"{current_time} | {buffer_stop} | {event}")
            if buffer_stop is not None and current_time is not None:
                if int(current_time) < int(buffer_stop):
                    continue

            event_count += 1

            # Store last goals, penalties, red cards data
            last_processed_goals = self.last_processed_ids.get(event_id, {}).get("goals", None)
            last_processed_penalties = self.last_processed_ids.get(event_id, {}).get("penalties", None)
            last_processed_red_cards = self.last_processed_ids.get(event_id, {}).get("red_cards", None)

            self.last_processed_ids[event_id] = self.last_processed_ids.get(event_id, {})

            # Don't process changes in the cases of Goals, Penalties and Red Cards to avoid false alerts.
            continue_flag = False
            if last_processed_goals != self.live_event_details.get(event_id, {}).get("goals", None):
                # if last_processed_goals is None:
                self.last_processed_ids[event_id]["goals"] = self.live_event_details.get(event_id, {}).get(
                    "goals", None)
                # if last_processed_goals is not None and self.live_event_details.get(event_id, {}).get(
                #         "goals", None) is not None:
                #     print("goal")
                # await logger_bot.sendMessage(text="New Goal Detected at new api hit, skipping this data set.",
                #                              chat_id=only_logs_channel)
                continue_flag = True
            if last_processed_penalties != self.live_event_details.get(event_id, {}).get("penalties", None):
                self.last_processed_ids[event_id]["penalties"] = self.live_event_details.get(event_id, {}).get(
                    "penalties", None)
                if last_processed_penalties is not None and self.live_event_details.get(event_id, {}).get(
                        "penalties", None) is not None:
                    # this is to avoid processing a event 150 sec from a penalty detection
                    penalty_time = event.get('time', None)
                    self.live_event_details[event_id]["buffer_stop"] = int(
                        penalty_time) + 150 if penalty_time is not None else None
                    logging.info(f"New Penalty Detected, skipping this data set.\n"
                                 f"{self.live_event_details.get(event_id, {}.get('home_team', None))}"
                                 f" v "
                                 f"{self.live_event_details.get(event_id, {}).get('away_team', None)}\n"
                                 f"{self.live_event_details.get(event_id, {}).get('game_time', None)}'")
                    await logging_bot.sendMessage(text=f"New Penalty Detected, skipping this data set "
                                                       f"adn the event for next 150 seconds.\n"
                                                       f"{self.live_event_details.get(event_id, {}.get('home_team', None))}"
                                                       f" v "
                                                       f"{self.live_event_details.get(event_id, {}).get('away_team', None)}\n"
                                                       f"{self.live_event_details.get(event_id, {}).get('game_time', None)}'",
                                                  chat_id=LOGS_CHANNEL)
                continue_flag = True
            if last_processed_red_cards != self.live_event_details.get(event_id, {}).get("red_cards", None):
                self.last_processed_ids[event_id]["red_cards"] = self.live_event_details.get(event_id, {}).get(
                    "red_cards", None)
                if last_processed_red_cards is not None and self.live_event_details.get(event_id, {}).get(
                        "red_cards", None) is not None:
                    # This is to stop processing a event 150 secs from red_card_detection
                    red_card_time = event.get('time', None)
                    self.live_event_details[event_id]["buffer_stop"] = int(
                        red_card_time) + 150 if red_card_time is not None else None
                    logging.info(f"New New Red Card Detected, skipping this data set.\n"
                                 f"{self.live_event_details.get(event_id, {}.get('home_team', None))}"
                                 f" v "
                                 f"{self.live_event_details.get(event_id, {}).get('away_team', None)}\n"
                                 f"{self.live_event_details.get(event_id, {}).get('game_time', None)}'")
                    await logging_bot.sendMessage(text=f"New Red Card Detected, skipping this data set "
                                                       f"and this event for next 150 seconds.\n"
                                                       f"{self.live_event_details.get(event_id, {}.get('home_team', None))}"
                                                       f" v "
                                                       f"{self.live_event_details.get(event_id, {}).get('away_team', None)}\n"
                                                       f"{self.live_event_details.get(event_id, {}).get('game_time', None)}'",
                                                  chat_id=LOGS_CHANNEL)
                continue_flag = True

            if continue_flag is True:
                continue

            # Fetch odds data for the event
            odds_data = self.fetch_event_odds(event_id)

            # Detect changes for the event
            for line_type in self.line_types.keys():
                try:
                    changes = await self.detect_changes(event_id, line_type, odds_data.get(line_type, []))
                except Exception as e:
                    logging.error(f"{event} | {line_type} | {e}")

        return event_count, all_events


# Usage
if __name__ == "__main__":
    load_dotenv()

    BET365_EVENTS_API_URL = os.getenv("BET365_EVENTS_API_URL")
    BET365_ODDS_API_URL = os.getenv("BET365_ODDS_API_URL")
    BET365_API_TOKEN = os.getenv("BET365_API_TOKEN")
    detector = LineChangeDetector(events_api_url=BET365_EVENTS_API_URL,
                                  odds_api_url=BET365_ODDS_API_URL,
                                  betsapi_token=BET365_API_TOKEN)

    LINE_CHANGE_BOT = os.getenv("LINE_CHANGE_BOT")
    LOGGING_BOT = os.getenv("LOGGING_BOT")
    t_request = HTTPXRequest(connection_pool_size=25)
    line_change_bot = Bot(token=LINE_CHANGE_BOT, request=t_request)
    logging_bot = Bot(token=LOGGING_BOT, request=t_request)
    LOGS_CHANNEL = os.getenv("LOGS_CHANNEL")
    BLACKLIST_FILE = os.getenv("BLACKLIST_FILE")


    async def main_loop():
        while True:
            logging.info("New Loop")
            try:
                current_event_count, current_events = await detector.process()
                logging.info(f"Events Count: {current_event_count}")
                logging.info(f"Events List: {current_events}")
                detector.clean_events(current_events)
                # The following delay between api calls is added to prevent rate limit of 3600 requests / hour
                # await asyncio.sleep(current_event_count + 1)
                # The following delay between api calls is added to prevent rate limit of 1,99,999 requests / hour
                await asyncio.sleep(current_event_count // 54 + 1)

            except Exception as e:
                logging.error(e)
                pass


    asyncio.run(main_loop())
