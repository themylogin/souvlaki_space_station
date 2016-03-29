# -*- coding: utf-8 -*-

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import textwrap
import time
import urllib2
import urlparse
from websocket import create_connection

from themylog.client import setup_logging_handler
from themyutils.restful_api.clients import RestfulApiPoller

setup_logging_handler("souvlaki_space_station_mpdscribble_instance_manager")

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="mpdscribble instance manager")
    parser.add_argument("--guests-api", required=True, help="Guests API URL")
    parser.add_argument("--mpd-host", required=True, help="MPD host")
    parser.add_argument("--mpdscribble-path", default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mpdscribble-sk")), help="mpdscribble path")
    args = parser.parse_args()

    mpdscribble_binary = os.path.join(args.mpdscribble_path, "src", "mpdscribble")
    mpdscribble_data_dir = os.path.join(args.mpdscribble_path, "data")

    while True:
        try:
            url = "%s/guests" % urlparse.urlunsplit(("ws",) + urlparse.urlsplit(args.guests_api)[1:])
            ws = create_connection(url)
            while True:
                data = json.loads(ws.recv())

                # Which scrobblers should be running?
                mpdscribble_commandlines = set()
                for guest in data["guests"]:
                    mpdscribble_config = os.path.join(mpdscribble_data_dir, guest["user"]["username"] + ".conf")
                    open(mpdscribble_config, "w").write(textwrap.dedent("""\
                        [mpdscribble]
                        host = """ + args.mpd_host + """
                        log = """ + mpdscribble_data_dir + """/""" + guest["user"]["username"] + """.log
                        verbose = 2

                        [last.fm]
                        url = http://post.audioscrobbler.com/
                        username = """ + guest["user"]["username"] + """
                        password = """ + guest["user"]["api_secret"] + """
                        api_key  = """ + guest["user"]["api_key"] + """
                        sk       = """ + guest["user"]["session_key"] + """
                        journal  = """ + mpdscribble_data_dir + """/""" + guest["user"]["username"] + """.journal
                        """))

                    mpdscribble_commandlines.add(mpdscribble_binary + " --conf " + mpdscribble_config)

                # Kill scrobblers that should not be running and don't run those that are already running
                for pid in [pid for pid in os.listdir("/proc") if pid.isdigit()]:
                    try:
                        cmd = open(os.path.join("/proc", pid, "cmdline"), "rb").read().replace("\0", " ").strip()
                    except IOError, e:
                        continue
                    if cmd.startswith(mpdscribble_binary):
                        if cmd not in mpdscribble_commandlines:
                            logger.info("Killing PID %s (%s) because it is not in guests list", pid, cmd)
                            os.kill(int(pid), signal.SIGTERM)
                        else:
                            logger.debug("Instance %s is already running", cmd)
                            mpdscribble_commandlines.remove(cmd)

                # Run absent scrobblers
                for cmd in mpdscribble_commandlines:
                    logger.info("Starting new instance: %s", cmd)
                    subprocess.call(cmd, shell=True)

        except Exception:
            logger.error("Error", exc_info=True)
            time.sleep(1)
