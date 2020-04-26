import datetime
import redis
import configparser
import os
import rapidjson as json
from typing import List

dt_mode = json.DM_ISO8601 | json.DM_NAIVE_IS_UTC

# Read config and parse constants
config = configparser.ConfigParser()
config.read('{}/config.ini'.format(os.getcwd()))

# Create redis instance
REDIS_HOST = config.get('redis', 'host')
REDIS_PORT = int(config.get('redis', 'port'))
REDIS_DB = int(config.get('redis', 'db'))

redisInst = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

def get_active_clients():
    clients = redisInst.hgetall("clientactivity")
    to_delete = []
    for c, raw_j in clients.items():
        last_active = json.loads(raw_j, datetime_mode=dt_mode)["last_active"]
        if (datetime.datetime.utcnow() - last_active.replace(tzinfo=None)).total_seconds() > 3600:
            to_delete.append(c)
    # Purge old clients
    if len(to_delete) > 0:
        redisInst.hdel("clientactivity", *to_delete)
    return len(redisInst.hgetall("clientactivity"))

def get_public_services():
    service = redisInst.get("services")
    loaded = json.loads(service)
    # Sort by work asc
    for i in loaded['public']:
        i['total'] = i['precache'] + i['ondemand']
    
    return sorted(loaded['public'], key = lambda i: i['total'], reverse=True) 

def get_clients():
    clients = redisInst.hgetall("clientstats")
    ret = []
    for address, raw_j in clients.items():
        j = json.loads(raw_j)
        if isinstance(j['total'], str):
            continue
        j['address'] = address
        ret.append(j)
    return sorted(ret, key = lambda i: i['total'], reverse=True)

def get_service_count():
    service = redisInst.get("services")
    loaded = json.loads(service)
    return len(loaded['public']) + len(loaded['private'])

def get_unlisted_count():
    service = redisInst.get("services")
    loaded = json.loads(service)
    return len(loaded['private'])

def get_pow_count_24hr():
    # Cache this
    cached = redisInst.get("pow24hcache")
    if cached is None:
        ret = len(list(redisInst.scan_iter(match='pow24h*')))
        redisInst.set("pow24hcache", str(ret), ex=300)
    else:
        ret = int(cached)
    return ret

def get_pow_count_48hr():
    # Cache this
    cached = redisInst.get("pow48hcache")
    if cached is None:
        ret = len(list(redisInst.scan_iter(match='pow48h*')))
        redisInst.set("pow48hcache", str(ret), ex=300)
    else:
        ret = int(cached)
    return ret

def get_avg_response() -> float:
    avg = redisInst.get("avgresponse")
    if avg is None:
        return 0
    avg = json.loads(avg,  datetime_mode=dt_mode)
    return avg["total_time"] / avg["count"]

def get_live_chart_prefill() -> List[float]:
    prefill = redisInst.lrange("live_chart_prefill", 0, 25)
    ret = [float(p) for p in prefill]
    return ret