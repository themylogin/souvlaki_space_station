import argparse
from flask import abort, Flask
from flask.ext import restful
import ipaddress
import re
import subprocess

from themylog.client import setup_logging_handler

setup_logging_handler("souvlaki_space_station_guests_devices_resolver")

app = Flask(__name__)
api = restful.Api(app)

class IP(restful.Resource):
    def get(self, ip):
        try:
            ip = str(ipaddress.ip_address(ip))
        except ValueError:
            abort(400)

        lines = subprocess.check_output(["arp", "-n", ip]).split("\n")
        if len(lines) == 3 and lines[1].startswith(ip):
            cols = re.split(r"\s+", lines[1])
            if len(cols) == 5:
                return cols[2]
            else:
                abort(500)
        else:
            abort(404)

api.add_resource(IP, "/ip/<ip>")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Guests Devices Resolver")
    parser.add_argument("--debug", action="store_true", help="Debug")
    parser.add_argument("--host", default="127.0.0.1", help="Host to listen")
    parser.add_argument("--port", default=46401, type=int, help="Port to listen")
    args = parser.parse_args()

    app.run(debug=args.debug, host=args.host, port=args.port, threaded=True)
