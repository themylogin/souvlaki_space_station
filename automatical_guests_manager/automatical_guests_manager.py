import argparse
import datetime
import dateutil.parser
import dateutil.tz
import json
import logging
import os
import sys
import time
import urllib
import urllib2

from themylog.client import setup_logging_handler
from themyutils.restful_api.clients import RestfulApiPoller

setup_logging_handler("souvlaki_space_station_automatical_guests_manager", exception_level="warning")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Automatical Guests Manager")
    parser.add_argument("--api", required=True, help="Guests API URL")
    parser.add_argument("--watcher", required=True, help="Guests Devices Watcher URL")
    args = parser.parse_args()

    for data in RestfulApiPoller(args.watcher + "/devices"):
        logging.debug("Following devices are present: %s", json.dumps(data["devices"]))

        while True:
            try:
                users_should_be_online = {}
                for device in data["devices"]:
                    try:
                        user = json.loads(urllib2.urlopen(args.api + "/users/by-device/%s" % device).read())
                        logging.debug("Device %s belongs to %s", device, user["username"])

                        if len(user["visits"]):
                            last_visit_left_data = user["visits"][-1]["left"]["data"]
                            if "no_auto_return_until" in last_visit_left_data:
                                no_auto_return_until = dateutil.parser.parse(last_visit_left_data["no_auto_return_until"])
                                if no_auto_return_until.tzinfo:
                                    no_auto_return_until = no_auto_return_until.astimezone(dateutil.tz.tzlocal()).replace(tzinfo=None)
                                logging.debug("User %s has no_auto_return_until %s", user["username"], no_auto_return_until)
                                if no_auto_return_until > datetime.datetime.now():
                                    logging.debug("Skipping user because of no_auto_return_until")
                                    continue

                        users_should_be_online[user["id"]] = {"device": device}                        
                    except urllib2.HTTPError as e:
                        if e.code == 404:
                            logging.debug("Device %s belongs to no one", device)
                        else:
                            raise

                for guest in json.loads(urllib2.urlopen(args.api + "/guests").read())["guests"]:
                    """
                    if "device" in guest["came"]["data"]:
                        if guest["user"]["id"] not in users_should_be_online:
                            logging.info("DELETE user %s because he came with device %s and now none of his devices are present", guest["user"]["username"], guest["came"]["data"]["device"])

                            request = urllib2.Request(args.api + "/guests/%d" % guest["user"]["id"], urllib.urlencode({
                                "device": guest["came"]["data"]["device"]
                            }))
                            request.get_method = lambda: "DELETE"
                            urllib2.urlopen(request).read()
                    """

                    if guest["user"]["id"] in users_should_be_online:
                        logging.info("User %s is already online", guest["user"]["username"])
                        del users_should_be_online[guest["user"]["id"]]

                for user_id, came_data in users_should_be_online.items():
                    logging.info("POST user %d", user_id)
                    urllib2.urlopen(urllib2.Request(args.api + "/guests/%d" % user_id, urllib.urlencode(came_data))).read()

                break

            except Exception as e:
                logging.exception("Failed to communicate with Guests API")
                time.sleep(5)
