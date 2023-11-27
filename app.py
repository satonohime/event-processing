import connexion
from connexion import NoContent
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import yaml
import json
import logging
import logging.config
import datetime
from flask_cors import CORS, cross_origin
import os

STATS_FILE = "/data/data.json"

if "TARGET_ENV" in os.environ and os.environ["TARGET_ENV"] == "test":
    print("In Test Environment")
    app_conf_file = "/config/app_conf.yml"
    log_conf_file = "/config/log_conf.yml"
else:
    print("In Dev Environment")
    app_conf_file = "app_conf.yml"
    log_conf_file = "log_conf.yml"

with open(app_conf_file, 'r') as f:
    app_config = yaml.safe_load(f.read())

# External Logging Configuration
with open(log_conf_file, 'r') as f:
    log_config = yaml.safe_load(f.read())
    logging.config.dictConfig(log_config)

logger = logging.getLogger('basicLogger')

logger.info("App Conf File: %s" % app_conf_file)
logger.info("Log Conf File: %s" % log_conf_file)

def get_stats():
    logger.info("Stats Request Started")
    stats = {}
    try:
        with open(STATS_FILE, "r") as file:
            data = json.load(file)
            stats["num_bookings"] = data["num_bookings"]
            stats["max_booking_duration"] = data["max_booking_duration"]
            stats["num_cancels"] = data["num_cancels"]
            stats["max_cancel_refund"] = data["max_cancel_refund"]
            stats["last_updated"] = data["last_updated"]
    except FileNotFoundError:
        logger.error("Statistics do not exist, creating file...")
        dict = {
            'num_bookings': 0,
            'max_booking_duration': 0,
            'num_cancels': 0,
            'max_cancel_refund': 0,
            'last_updated': datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        with open("/data/data.json", "w") as outfile:
            json.dump(dict, outfile)

    logger.debug(f'Contents: {stats}')
    logger.info('Processing completed')

    return stats, 200


def populate_stats():
    logger.info("Periodic Processing Started")
    stats = {}
    try:
        with open(STATS_FILE, "r") as file:
            data = json.load(file)
            stats["num_bookings"] = data["num_bookings"]
            stats["max_booking_duration"] = data["max_booking_duration"]
            stats["num_cancels"] = data["num_cancels"]
            stats["max_cancel_refund"] = data["max_cancel_refund"]
            stats["last_updated"] = data["last_updated"]
    except FileNotFoundError:
        stats["num_bookings"] = 0
        stats["max_booking_duration"] = 0
        stats["num_cancels"] = 0
        stats["max_cancel_refund"] = 0
        stats["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    logger.debug(stats)

    curr_DT = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        reqs_book = requests.get(f'{app_config["eventstore"]["url"]}/bookings/book?start_timestamp={stats["last_updated"]}&end_timestamp={curr_DT}', timeout=5)
    except:
        logger.error("Could not get bookings")
    try:
        reqs_cancel = requests.get(f'{app_config["eventstore"]["url"]}/bookings/cancel?start_timestamp={stats["last_updated"]}&end_timestamp={curr_DT}', timeout=5)
    except:
        logger.error("Could not get cancellations")
        
    if reqs_book.status_code == 200:
        json_list = reqs_book.json()
        stats["num_bookings"] = stats["num_bookings"] + len(json_list)
        max_duration = stats['max_booking_duration']
        for booking in json_list:
            if booking["duration"] > max_duration:
                max_duration = booking["duration"]
        stats["max_booking_duration"] = max_duration
    else:
        logger.error("Did not recieve 200 response code")

    if reqs_cancel.status_code == 200:
        json_list = reqs_cancel.json()
        stats["num_cancels"] = stats["num_cancels"] + len(json_list)
        max_refund = stats['max_cancel_refund']
        for cancel in json_list:
            if cancel["refund_price"] > max_refund:
                max_refund = cancel["refund_price"]
        stats["max_cancel_refund"] = max_refund
    else:
        logger.error("Did not recieve 200 response code")

    stats["last_updated"] = curr_DT

    with open(STATS_FILE, "w") as file:
        json_str = json.dumps(stats)
        file.write(json_str)

    logger.debug(
        f'Num Bookings: {stats["num_bookings"]} Max Booking Duration: {stats["max_booking_duration"]} Num Cancels: {stats["num_cancels"]} Max Refund Price: {stats["max_cancel_refund"]}'
    )

    logger.info("Processing Finished")

def health():
    return 200

def init_scheduler():
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(
        populate_stats, "interval", seconds=app_config["scheduler"]["period_sec"]
    )
    sched.start()


app = connexion.FlaskApp(__name__, specification_dir="")
if "TARGET_ENV" not in os.environ or os.environ["TARGET_ENV"] != "test":
    CORS(app.app)
    app.app.config['CORS_HEADERS'] = 'Content-Type'
app.add_api(
    "openapi.yml",
    base_path="/processing",
    strict_validation=True, 
    validate_responses=True)

if __name__ == "__main__":
    init_scheduler()
    app.run(port=8100)
