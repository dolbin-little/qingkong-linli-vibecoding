"""Optional read-only telemetry subscriber. No flight commands are published.
Configure GREENFLIGHT_MQTT_HOST/PORT/USERNAME/PASSWORD/TLS; disabled by default.
"""
import json
import os
import math
import sqlite3
import time
from backend.store import ROOT

def validate(payload):
    if not isinstance(payload,dict): raise ValueError('payload must be an object')
    required=('device_id','battery','x','y')
    if any(k not in payload for k in required): raise ValueError('missing telemetry fields')
    if not isinstance(payload['device_id'],str) or not 1<=len(payload['device_id'])<=60: raise ValueError('invalid device id')
    for key in ('battery','x','y'):
        if not isinstance(payload[key],(int,float)) or not math.isfinite(payload[key]): raise ValueError('invalid numeric value')
    if not 0<=payload['battery']<=100: raise ValueError('battery outside range')
    return {k:payload[k] for k in required}

def run():
    import paho.mqtt.client as mqtt
    host=os.environ.get('GREENFLIGHT_MQTT_HOST')
    if not host: raise SystemExit('Set GREENFLIGHT_MQTT_HOST to your test broker; no connection made.')
    db=sqlite3.connect(ROOT/'data'/'telemetry.db')
    db.execute('CREATE TABLE IF NOT EXISTS telemetry (at REAL, device_id TEXT, body TEXT)');db.close()
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='greenflight-observer')
    if os.environ.get('GREENFLIGHT_MQTT_USERNAME'):
        client.username_pw_set(os.environ['GREENFLIGHT_MQTT_USERNAME'],os.environ.get('GREENFLIGHT_MQTT_PASSWORD'))
    if os.environ.get('GREENFLIGHT_MQTT_TLS')=='1': client.tls_set()
    def on_connect(c,userdata,flags,reason,props):
        if reason==0: c.subscribe('greenflight/+/telemetry')
    def on_message(c,userdata,msg):
        if len(msg.payload)>8192:return
        try:
            value=validate(json.loads(msg.payload));device=msg.topic.split('/')[1]
            if device!=value['device_id']:return
            with sqlite3.connect(ROOT/'data'/'telemetry.db') as db:
                db.execute('INSERT INTO telemetry VALUES (?,?,?)',(time.time(),device,json.dumps(value)))
        except (ValueError,UnicodeDecodeError,KeyError):return
    client.on_connect=on_connect;client.on_message=on_message
    client.connect(host,int(os.environ.get('GREENFLIGHT_MQTT_PORT','1883')),60);client.loop_forever()

if __name__=='__main__':run()
