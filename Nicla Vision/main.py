# Edge Impulse - OpenMV Object Detection Example

import sensor, image, time, os, tf, math, uos, gc

from micropython import const

import uasyncio as asyncio
from aioble import server as aioble
from aioble import peripheral
import bluetooth

import random
import struct

sensor.reset()                         # Reset and initialize the sensor.
sensor.set_pixformat(sensor.RGB565)    # Set pixel format to RGB565 (or GRAYSCALE)
sensor.set_framesize(sensor.QVGA)      # Set frame size to QVGA (320x240)
sensor.set_windowing((240, 240))       # Set 240x240 window.
sensor.skip_frames(time=2000)          # Let the camera adjust.
sensor.set_transpose(False)
sensor.set_hmirror(True)
sensor.set_vflip(True)

net = None
labels = None
min_confidence = 0.5

try:
    # load the model, alloc the model file on the heap if we have at least 64K free after loading
    net = tf.load("trained.tflite", load_to_fb=uos.stat('trained.tflite')[6] > (gc.mem_free() - (64*1024)))
except Exception as e:
    raise Exception('Failed to load "trained.tflite", did you copy the .tflite and labels.txt file onto the mass-storage device? (' + str(e) + ')')

try:
    labels = [line.rstrip('\n') for line in open("labels.txt")]
except Exception as e:
    raise Exception('Failed to load "labels.txt", did you copy the .tflite and labels.txt file onto the mass-storage device? (' + str(e) + ')')

colors = [ # Add more colors if you are detecting more than 7 types of classes at once.
    (255,   0,   0),
    (  0, 255,   0),
    (255, 255,   0),
    (  0,   0, 255),
    (255,   0, 255),
    (  0, 255, 255),
    (255, 255, 255),
]

_GEN_ATTR_UUID = bluetooth.UUID(0x181A)
_GEN_ATTR_UNITLESS_UUID = bluetooth.UUID(0x2A1C)
_ADV_APPEARANCE_GENERIC_COMPUTER = const(768)

# How frequently to send advertising beacons.
_ADV_INTERVAL_MS = 500_000


# Register GATT server.
peoplecount_service = aioble.Service(_GEN_ATTR_UUID)
peoplecount_characteristic = aioble.Characteristic(
    peoplecount_service, _GEN_ATTR_UNITLESS_UUID, read=True, notify=False
)
aioble.register_services(peoplecount_service)


# Helper to encode the characteristic
def _encode_peoplecount(peoplecount):
    return struct.pack("<i", int(peoplecount))


# This would be periodically polling a hardware sensor.
async def sensor_task():
    t = 24.5
    while True:
        img = sensor.snapshot()

        # detect() returns all objects found in the image (splitted out per class already)
        # we skip class index 0, as that is the background, and then draw circles of the center
        # of our objects

        count = 0
        for i, detection_list in enumerate(net.detect(img, thresholds=[(math.ceil(min_confidence * 255), 255)])):
            if (i == 0): continue # background class
            if (len(detection_list) == 0): continue # no detections for this class?

            print("********** %s **********" % labels[i])
            for d in detection_list:
                [x, y, w, h] = d.rect()
                center_x = math.floor(x + (w / 2))
                center_y = math.floor(y + (h / 2))
                print('x %d\ty %d' % (center_x, center_y))
                img.draw_circle((center_x, center_y, 12), color=colors[i], thickness=2)
                count = count + 1

        peoplecount_characteristic.write(_encode_peoplecount(count))
        print(count)
        await asyncio.sleep_ms(5000)


# Serially wait for connections. Don't advertise while a central is
# connected.
async def peripheral_task():
    while True:
        async with await peripheral.advertise(
            _ADV_INTERVAL_MS,
            name="NICLA-VISION",
            services=[_GEN_ATTR_UUID],
            appearance=_ADV_APPEARANCE_GENERIC_COMPUTER,
        ) as connection:
            print("Connection from", connection.device)
            await connection.disconnected()


# Run both tasks.
async def mainBLE():
    t1 = asyncio.create_task(sensor_task())
    t2 = asyncio.create_task(peripheral_task())
    await asyncio.gather(t1, t2)

while (True):
    asyncio.run(mainBLE())

