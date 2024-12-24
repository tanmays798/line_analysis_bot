import asyncio
import logging
import statistics
import os
from dotenv import load_dotenv
import requests
from typing import List, Dict
from telegram import Bot
from telegram.request import HTTPXRequest

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
            "SOFT": SOFT_ALERTS_CHANNEL,
            "MEDIUM": MEDIUM_ALERTS_CHANNEL,
            "HARD": HARD_ALERTS_CHANNEL
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

        # Remove data points with no odds data
        try:
            clean_odds_data = []
            for i in range(len(data)):
                if line_type == "1_2" or line_type == "1_5":
                    if data[i]['home_od'] == '-' or data[i]['away_od'] == '-':
                        continue
                    else:
                        clean_odds_data.append(data[i])
                elif line_type == "1_3" or line_type == "1_6":
                    if data[i]['over_od'] == '-' or data[i]['under_od'] == '-':
                        continue
                    else:
                        clean_odds_data.append(data[i])

            data = clean_odds_data

        except Exception as e:
            logging.error(f"In Cleaning Odds Data | {event_id} | {line_type} | {e}")

        # remove singular data points
        try:
            new_data = []
            # We ignore the first data point of the data set.
            for i in range(1, len(data) - 1):

                if statistics.fmean(map(get_float, data[i]['handicap'].split(','))) != statistics.fmean(
                        map(get_float, data[i - 1]['handicap'].split(','))) and statistics.fmean(
                    map(get_float, data[i]['handicap'].split(','))) != statistics.fmean(
                    map(get_float, data[i + 1]['handicap'].split(','))):
                    continue
                else:
                    new_data.append(data[i])

            # This is to handle the last data point in the data set
            if statistics.fmean(map(get_float, data[-1]['handicap'].split(','))) == statistics.fmean(
                    map(get_float, new_data[-1]['handicap'].split(','))):
                new_data.append(data[-1])
        except Exception as e:
            logging.error(f"In Removing Singular Points | {event_id} | {line_type} | {e}")
            pass

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
                                    await line_change_bot.sendMessage(
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
                                logging.info(f"Within alert - goal detection: {e}")
                                continue
                                # pass
                            if change_type_flag is not None:
                                if changes_data.get(change_type_flag, None) is None:
                                    home_team = self.live_event_details.get(event_id, {}).get('home_team', '')
                                    away_team = self.live_event_details.get(event_id, {}).get('away_team', '')
                                    change_msg = f"{change_type_flag} Change\n" \
                                                 f"⚽ {self.live_event_details.get(event_id, {}).get('league', '')}\n" \
                                                 f"⏱ {game_time}' " \
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

                                    await line_change_bot.sendMessage(text=change_msg,
                                                                      chat_id=self.alerts_channels.get(change_type_flag,
                                                                                                       LOGS_CHANNEL),
                                                                      parse_mode='HTML',
                                                                      disable_web_page_preview=True)
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

    async def process(self):

        # Fetch all live events
        live_events = self.fetch_live_events()

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

            try:
                game_time = event.get("timer", {}).get("tm", None)
                if int(game_time) < 2:
                    continue

                # Information to be captured and stored here - Id, Name, League, Time, Red Card, Penalties, Goals
                self.live_event_details[event["id"]] = self.live_event_details.get(event["id"], {})
                self.live_event_details[event["id"]] = {
                    "home_team": event.get("home", {}).get("name", None),
                    "away_team": event.get("away", {}).get("name", None),
                    "league": league_name,
                    "game_time": game_time,
                    "goals": event.get("stats", {}).get("goals", None),
                    "penalties": event.get("stats", {}).get("penalties", None),
                    "red_cards": event.get("stats", {}).get("redcards", None)
                }
            except Exception as e:
                logging.error(f"{event} | {e}")

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
                    logging.info(f"New Penalty Detected, skipping this data set.\n"
                                 f"{self.live_event_details.get(event_id, {}.get('home_team', None))}"
                                 f" v "
                                 f"{self.live_event_details.get(event_id, {}).get('away_team', None)}\n"
                                 f"{self.live_event_details.get(event_id, {}).get('game_time', None)}'")
                    await line_change_bot.sendMessage(text=f"New Penalty Detected, skipping this data set.\n"
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
                    logging.info(f"New New Red Card Detected, skipping this data set.\n"
                                 f"{self.live_event_details.get(event_id, {}.get('home_team', None))}"
                                 f" v "
                                 f"{self.live_event_details.get(event_id, {}).get('away_team', None)}\n"
                                 f"{self.live_event_details.get(event_id, {}).get('game_time', None)}'")
                    await line_change_bot.sendMessage(text=f"New Red Card Detected, skipping this data set.\n"
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
    t_request = HTTPXRequest(connection_pool_size=25)
    line_change_bot = Bot(token=LINE_CHANGE_BOT, request=t_request)
    SOFT_ALERTS_CHANNEL = os.getenv("SOFT_ALERTS_CHANNEL")
    MEDIUM_ALERTS_CHANNEL = os.getenv("MEDIUM_ALERTS_CHANNEL")
    HARD_ALERTS_CHANNEL = os.getenv("HARD_ALERTS_CHANNEL")
    LOGS_CHANNEL = os.getenv("LOGS_CHANNEL")


    async def main_loop():
        while True:
            logging.info("New Loop")
            try:
                # current_event_count, current_events = asyncio.run(detector.process())
                current_event_count, current_events = await detector.process()
                logging.info(f"Events Count: {current_event_count}")
                logging.info(f"Events List: {current_events}")
                detector.clean_events(current_events)
                # asyncio.run(asyncio.sleep(current_event_count + 1))
                await asyncio.sleep(current_event_count + 1)
            except Exception as e:
                logging.error(e)
                pass


    asyncio.run(main_loop())
