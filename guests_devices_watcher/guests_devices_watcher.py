import argparse
from collections import defaultdict
from flask import abort, Flask, request
from flask.ext import restful
import json
import logging
import os
import paramiko
from Queue import Queue
import re
import select
import subprocess
import threading
import time

from themylog.client import setup_logging_handler

setup_logging_handler("souvlaki_space_station_guests_devices_watcher")
logging.getLogger("paramiko.transport").setLevel(logging.INFO)

###

devices = {
    "version": 1,
    "devices": set(),
}

def main(host, port):
    logger = logging.getLogger("main_thread")

    while True:
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(host, port=port, username="root", timeout=30)

            while True:
                stdin, stdout, stderr = client.exec_command("iw dev wlan0 station dump")

                changed = False
                old_devices = set(devices["devices"])
                new_devices = set(re.findall("Station (" + ":".join(["[0-9a-f]{2}"] * 6) + ")", stdout.read()))
                for removed_device in old_devices - new_devices:
                    logging.info("Removing device %s", removed_device)
                    devices["devices"].remove(removed_device)
                    changed = True
                for new_device in new_devices - old_devices:
                    logging.info("Creating device %s", new_device)
                    devices["devices"].add(new_device)
                    changed = True

                if changed:
                    logging.debug("Device list was changed")
                    devices["version"] += 1

                time.sleep(10)

        except (KeyboardInterrupt, SystemExit):
            raise

        except Exception:
            logger.exception("Exception")
            time.sleep(5)

###

app = Flask(__name__)
api = restful.Api(app)

class Devices(restful.Resource):
    def get(self):
        range_header = request.headers.get("Range", None)
        if range_header is not None:
            try:
                client_version = int(range_header.split("-")[0])
            except:
                abort(400)

            while client_version == devices["version"]:
                time.sleep(1)

        return self.response()

    def response(self):
        return {
            "version": devices["version"],
            "devices": list(devices["devices"]),
        }

api.add_resource(Devices, "/devices")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Guests Devices Watcher")
    parser.add_argument("--debug", action="store_true", help="Debug")
    parser.add_argument("--host", default="127.0.0.1", help="Host to listen")
    parser.add_argument("--port", default=46402, type=int, help="Port to listen")
    parser.add_argument("--ssh-host", required=True, help="SSH host")
    parser.add_argument("--ssh-port", default=22, type=int, help="SSH port")
    args = parser.parse_args()

    main_thread = threading.Thread(target=lambda: main(args.ssh_host, args.ssh_port))
    main_thread.daemon = True
    main_thread.start()

    app.run(debug=args.debug, host=args.host, port=args.port, threaded=True)
