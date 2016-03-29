# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, unicode_literals

import argparse
from datetime import datetime, timedelta
import json
import logging
import pika
import requests
import time
import urlparse
from websocket import create_connection

from themylog.client import setup_logging_handler
from themyutils.threading import start_daemon_thread

setup_logging_handler("souvlaki_space_station_guests_announcer")

logger = logging.getLogger(__name__)


class GuestsWatcher(object):
    def __init__(self, guests_api, smarthome_api):
        self.guests_api = guests_api
        self.smarthome_api = smarthome_api

        self.guests = []
        self.expected_guests = []

        self.first_start = True
        self.last_front_door_closed_at = datetime.min

    def watch(self):
        while True:
            try:
                url = "%s/guests" % urlparse.urlunsplit(("ws",) + urlparse.urlsplit(self.guests_api)[1:])
                ws = create_connection(url)
                while True:
                    data = ws.recv()
                    self.process(json.loads(data))
            except Exception:
                logger.error("GuestsWatcher.watch error", exc_info=True)
                time.sleep(1)

    def process(self, data):
        bye_guests = set(self.guests + self.expected_guests)
        for guest in data["guests"]:
            title = guest["user"]["title"]

            if title in bye_guests:
                bye_guests.discard(title)
            else:
                if (not self.first_start and
                    len(guest["user"]["visits"]) > 0 and
                    "no_welcome_postpone" not in guest["came"]["data"] and
                    datetime.now() - self.last_front_door_closed_at > timedelta(minutes=5)):
                    self.expected_guests.append(title)
                else:
                    self.say("В умном доме гость. Привет, %s!" % title)
                    self.guests.append(title)

        for title in bye_guests:
            self.say("Пока, %s!" % title)
            self.guests = [g for g in self.guests if g != title]
            self.expected_guests = [g for g in self.expected_guests if g != title]

        self.first_start = False

    def on_front_door_closed(self):
        self.last_front_door_closed_at = datetime.now()

        for title in self.expected_guests:
            self.say("В умном доме гость. Привет, %s!" % title)
            self.guests.append(title)
            self.expected_guests = [g for g in self.expected_guests if g != title]

    def say(self, phrase):
        requests.post("%s/control" % self.smarthome_api, data=json.dumps({"command": "call_method",
                                                                          "args": {"object": "hall_speech_synthesizer",
                                                                                   "method": "say",
                                                                                   "args": {"phrase": phrase}}}))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="guests announcer")
    parser.add_argument("--guests-api", required=True, help="Guests API URL")
    parser.add_argument("--smarthome-api", required=True, help="Smarthome API URL")
    args = parser.parse_args()

    guests_watcher = GuestsWatcher(args.guests_api, args.smarthome_api)
    start_daemon_thread(guests_watcher.watch)

    while True:
        try:
            mq_connection = pika.BlockingConnection(pika.ConnectionParameters(host="localhost"))
            mq_channel = mq_connection.channel()

            mq_channel.exchange_declare(exchange="themylog", type="topic")

            result = mq_channel.queue_declare(exclusive=True)
            queue_name = result.method.queue

            mq_channel.queue_bind(exchange="themylog", queue=queue_name, routing_key=b"smarthome.front_door.closed")
            mq_channel.basic_consume(lambda *args, **kwargs: guests_watcher.on_front_door_closed, queue=queue_name, no_ack=True)

            mq_channel.start_consuming()
        except Exception as e:
            logger.error("AMQP Error", exc_info=True)
            time.sleep(1)
