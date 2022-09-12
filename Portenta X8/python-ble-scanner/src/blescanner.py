#!/usr/bin/env python3

import random, time, binascii, struct
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from bluepy.btle import Peripheral, UUID

#Nicla Sense Me details
nicla_sense_mac = "<YOUR NICLA SENSE MAC>"
#Monitored characteristics
nicla_sense_labels = ["temperature", "humidity", "pressure", "bsec", "co2", "gas"]
nicla_sense_uuids_values = [UUID(0x2A1C), UUID(0x2A6F), UUID(0x2AA3), UUID(0x2BCF), UUID(0x2BD0), UUID(0x27AD)]
nicla_sense_readings = [0,0,0,0,0,0]


#Nicla Vision details
nicla_vision_mac = "YOUR NICLA VISION MAC"
#Monitored characteristics
nicla_vision_labels = ["people"]
nicla_vision_uuids_values = [UUID(0x2A1C)]
nicla_vision_readings = [0]

#InfluxDb details
# You can generate an API token from the "API Tokens Tab" in the UI
token = "YOUR INFLUXDB TOKEN"
org = "arduino"
bucket = "x8-iot"


nicla_sense = Peripheral(nicla_sense_mac)
nicla_vision = Peripheral(nicla_vision_mac)


while True:
    #Getting the readings from the Nicla Vision
    i = 0
    for service in nicla_vision.getServices():
        for characteristic in service.getCharacteristics():
           
            print("Characteristic - id: %s\tname (if exists): %s\tavailable methods: %s" % (str(characteristic.uuid), str(characteristic), characteristic.propertiesToString()))
            if(characteristic.uuid in nicla_vision_uuids_values):
                ch = nicla_vision.getCharacteristics(uuid=characteristic.uuid)[0]
                print(ch)
                if (ch.supportsRead()):
                    val = binascii.b2a_hex(ch.read())
                    print(val)
                    val = binascii.unhexlify(val)
                    print(val)
                    val = struct.unpack('f', val)[0]
                    print(val)
                    nicla_vision_readings[i] = val
                    print(i)
                    print (str(val))
                    i += 1
                    print(i)
                    time.sleep(1)
    print (nicla_vision_labels)
    print (nicla_vision_uuids_values)
    print (nicla_vision_readings)
    #Writting them in the Portenta container in InfluxDB
    with InfluxDBClient(url="http://YOUR PORTENTA X8 IP:8086", token=token, org=org) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)

        point = Point("nicla_vision") \
        .field("location", random.shuffle(["ConferenceRoom", "MeetingRoom", "CoworkingSpace"])) \
        .field(nicla_vision_labels[0], nicla_vision_readings[0]) \
        .time(datetime.utcnow(), WritePrecision.NS)

        write_api.write(bucket, org, point)
        time.sleep(1)
    #Getting the readings from the Nicla Sense ME
    i = 0
    for service in nicla_sense.getServices():
        for characteristic in service.getCharacteristics():
           
            print("Characteristic - id: %s\tname (if exists): %s\tavailable methods: %s" % (str(characteristic.uuid), str(characteristic), characteristic.propertiesToString()))
            if(characteristic.uuid in nicla_sense_uuids_values):
                ch = nicla_sense.getCharacteristics(uuid=characteristic.uuid)[0]
                if (ch.supportsRead()):
                    val = binascii.b2a_hex(ch.read())
                    val = binascii.unhexlify(val)
                    val = struct.unpack('f', val)[0]
                    nicla_sense_readings[i] = val
                    print(i)
                    print (str(val))
                    i += 1
                    print(i)
                    time.sleep(1)
    print (nicla_sense_labels)
    print (nicla_sense_uuids_values)
    print (nicla_sense_readings)
    #Writting them in the Portenta container in InfluxDB
    with InfluxDBClient(url="http://YOUR PORTENTA X8 IP", token=token, org=org) as client:
        write_api = client.write_api(write_options=SYNCHRONOUS)

        point = Point("nicla_sense") \
        .field("location", random.shuffle(["ConferenceRoom", "MeetingRoom", "CoworkingSpace"])) \
        .field(nicla_sense_labels[0], nicla_sense_readings[0]) \
        .field(nicla_sense_labels[1], nicla_sense_readings[1]) \
        .field(nicla_sense_labels[2], nicla_sense_readings[2]) \
        .field(nicla_sense_labels[3], nicla_sense_readings[3]) \
        .field(nicla_sense_labels[4], nicla_sense_readings[4]) \
        .field(nicla_sense_labels[5], nicla_sense_readings[5]) \
        .time(datetime.utcnow(), WritePrecision.NS)

        write_api.write(bucket, org, point)
        time.sleep(1)
