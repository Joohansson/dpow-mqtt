#!/home/dpow/dpow-mqtt/venv/bin/python3

from datetime import datetime

import configparser
import rapidjson as json
import logging
import os
import paho.mqtt.client as mqtt
import redis
import requests
import sys

dt_mode = json.DM_ISO8601 | json.DM_NAIVE_IS_UTC

# Read config and parse constants
config = configparser.ConfigParser()
config.read('{}/config.ini'.format(os.getcwd()))

logger = logging.getLogger("dpow_log")
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(filename)s@%(funcName)s:%(lineno)s:%(message)s", "%Y-%m-%d %H:%M:%S %z")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(formatter)
logger.addHandler(handler)

POW_USER = config.get('pow', 'username')
POW_PW = config.get('pow', 'password')
MQTT_IP = config.get('pow', 'mqtt_ip')
MQTT_PORT = int(config.get('pow', 'mqtt_port'))
REDIS_HOST = config.get('redis', 'host')
REDIS_PORT = int(config.get('redis', 'port'))
REDIS_DB = int(config.get('redis', 'db'))


def on_connect(client, userdata, flags, rc):
    """
    On connection to the MQTT server, automatically subscribe to merchant_order_requests topic
    """
    logger.info("{}: Connected to DPOW Server with result code {}".format(datetime.utcnow(), str(rc)))
    client.subscribe('work/#')
    client.subscribe('result/#')
    client.subscribe('statistics')
    client.subscribe('client/#')


def on_message(client, userdata, msg):
    """
    On messages from MQTT, handle the request.
    """
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
        topic = msg.topic
        topic = topic.split('/')
        if topic[0] == 'work':
            # We store the work request in a hashmap with the work hash as the key for reference when receiving the result.
            work_type = topic[1]
            message = msg.payload.decode().split(',')
            work_hash = message[0]
            work_difficulty = message[1]
            mapping = {'work_type': work_type, 'work_difficulty': work_difficulty, 'timestamp': str(datetime.utcnow())}
            r.hmset(work_hash, mapping)

        elif topic[0] == 'result':
            # When we receive the result, retrieve the hashmap associated with the work hash.
            message = msg.payload.decode().split(',')
            work_hash = message[0]
            work_value = message[1]
            work_client = message[2]

            # Set client activity
            r.hset("clientactivity", work_client, json.dumps({
                "last_active": datetime.utcnow()
            }, datetime_mode=dt_mode))

            hmreturn = r.hmget(work_hash, ['work_type', 'timestamp', 'work_difficulty'])
            # Multiple results are sent for 1 work hash, ignore if the result has already been logged.
            if hmreturn == [None, None, None]:
                return

            request_time = datetime.strptime(hmreturn[1].decode(), '%Y-%m-%d %H:%M:%S.%f')

            # Set PoW keys, 1 with expiry 2 days, one with expiry 1 days
            r.set(f"pow24h:{work_hash}", work_hash, ex=86400)
            r.set(f"pow48h:{work_hash}", work_hash, ex=172800)

            # Get time this request took
            time_diff_micro = (datetime.utcnow() - request_time).microseconds
            time_difference = round(time_diff_micro * (10 ** -6), 4)
            """
            avg = r.get("avgresponse")
            new = {}
            if avg is not None:
                avg = json.loads(avg)
                # Reset average after an hour
                if (datetime.utcnow() - avg['created']).total_seconds() > 3600:
                    r.delete("avgresponse")
                    new['created'] = datetime.utcnow()
                    new['count'] = 1
                    new['time_total'] = time_difference
                else:
                    new['count'] = avg['count'] + 1
                    new['time_total'] += avg['time_total'] + 1
            else:
                new = {
                    'created': datetime.utcnow(),
                    'count': 1,
                    'time_total': time_difference
                }
            r.set("avgresponse", json.dumps(new, datetime_mode=dt_mode))
            """
            # Set live chart data
            r.lpush("live_chart_prefill", str(time_difference))
            r.ltrim("live_chart_prefill", 0, 25)
            # Once logged successfully, delete the work hash from redis.
            r.delete(work_hash)

        elif topic[0] == 'statistics':
            stats = json.loads(msg.payload.decode())
            logger.info("Stats call received: {}".format(stats))
            # It just seems easier/faster to store the total paid aggregate in redis
            if 'total_paid_banano' in stats:
                r.set("bpowdash:totalpaidban", str(stats['total_paid_banano']))
            r.set("services", json.dumps(stats['services']))

        elif topic[0] == 'client':
            try:
                # Messages on client update their totals without us having to track.  Keeps in sync 
                # with the server.
                result = json.loads(msg.payload.decode())
                address = topic[1]
                if 'precache' in result:
                    precache = int(result['precache'])
                else:
                    precache = 0
                if 'ondemand' in result:
                    ondemand = int(result['ondemand'])
                else:
                    ondemand = 0

                r.hset("clientstats", address, json.dumps({
                    "total": ondemand+precache,
                    "precache": precache,
                    "ondemand": ondemand
                }))

            except Exception as e:
                logger.exception("error logging client info: {}".format(e))
                logger.info(msg.payload)
        else:
            try:
                logger.info("UNEXPECTED MESSAGE")
                logger.info("TOPIC: {}".format(topic[0].upper()))
                logger.info("message: {}".format(msg.payload))
            except Exception as e:
                logger.info("exception: {}".format(e))

    except Exception as e:
        logger.exception("Error: {}".format(e))

if __name__ == "__main__":
    c = mqtt.Client()

    c.on_connect = on_connect
    c.on_message = on_message

    c.username_pw_set(POW_USER, password=POW_PW)
    c.connect(MQTT_IP, MQTT_PORT)

    c.loop_forever()