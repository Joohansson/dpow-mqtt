from gevent import monkey
monkey.patch_all()

from datetime import datetime
from flask import Flask, render_template

import configparser
import rapidjson as json
import logging
import os
import requests
import redis
import sys

import modules.redis_db as rdb

# Read config and parse constants
config = configparser.ConfigParser()
config.read('{}/config.ini'.format(os.getcwd()))

# Create redis instance
REDIS_HOST = config.get('redis', 'host')
REDIS_PORT = int(config.get('redis', 'port'))
REDIS_DB = int(config.get('redis', 'db'))

redisInst = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

logger = logging.getLogger("dpow_log")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(filename)s@%(funcName)s:%(lineno)s:%(message)s", "%Y-%m-%d %H:%M:%S %z")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

app = Flask(__name__)


@app.route("/upcheck")
def upcheck():
    post_url = "https://dpow-api.nanos.cc/upcheck/"
    response = requests.get(post_url)
    if response.text != 'up':
        return 'Offline'
    return 'up'


@app.route("/")
@app.route("/index")
def index():
    pow24, pow48 = rdb.get_pow_counts()
    # Get current POW count
    pow_count = pow24
    work_24hr = pow_count - (pow48 - pow_count)

    # Get total distributed
    total_paid_banano = redisInst.get("bpowdash:totalpaidban")
    total_paid_banano = float(total_paid_banano) if total_paid_banano is not None else 0.0

    # Get service info
    service_count=rdb.get_service_count()
    unlisted_services=rdb.get_unlisted_count()
    listed_services=service_count - unlisted_services

    return render_template('index.html', client_count=rdb.get_active_clients(),
                            service_count=service_count,
                            unlisted_count=unlisted_services,
                            listed_services=listed_services,
                            services=rdb.get_public_services(),
                            pow_count=pow_count,
                            work_24hr=work_24hr,
                            total_distributed=total_paid_banano,
                            live_chart_prefill=rdb.get_live_chart_prefill(),
                            clients=rdb.get_clients())

if __name__ == "__main__":
    app.run(host='0.0.0.0')
