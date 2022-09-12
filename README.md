# Environmental monitoring with Arduino Pro

This project is a proof of concept for demonstrating the Environmental monitoring of offices by using the Arduino Pro Ecosystem.

For monitoring the environmental conditions we have chosen the Arduino Nicla Sense ME which is designed to easily analyze motion and the surrounding environment – hence the “M” and “E” in the name – it measures rotation, acceleration, pressure, humidity, temperature, air quality, and CO2 levels by introducing completely new Bosch Sensortec sensors on the market.

For monitoring the number of people in each room we have chosen the Arduino Nicla Vision which combines a powerful STM32H747AII6 Dual ARM® Cortex® M7/M4 IC processor with a 2MP color camera that supports TinyML, as well as a smart 6-axis motion sensor, integrated microphone, and distance sensor.

![InfluxDB Dashboard with the collected data](https://github.com/[madaerodog]/[Arduino_environmental_monitoring_with_arduino_pro
]/blob/[main]/dashboard.jpg?raw=true)

## Getting Started

These instructions will give you a copy of the project up and running on your local machine for development and testing purposes. 

### Prerequisites

Hardware requirements: 
- [Nicla Sense Me](https://www.arduino.cc/pro/hardware/product/nicla-sense-me)
- [Nicla Vision](https://www.arduino.cc/pro/hardware/product/nicla-vision)
- [Portenta X8](https://www.arduino.cc/pro/hardware/product/portenta-x8)


Software requirements: 
- [Arduino IDE](https://www.arduino.cc/en/software)
- [Open MV](https://openmv.io/pages/download)
- [EdgeImpulse free account](https://studio.edgeimpulse.com/signup)

### Installing

Nicla Sense ME:
- install the Arduino IDE and the Nicla Sense board in it by following this [article](https://docs.arduino.cc/tutorials/nicla-sense-me/getting-started)
- clone this repository and set the workspace in the Nicla Sense ME folder
- compile and upload the ble_sense_send sketch

Nicla Vision:
- install the Open MV environment, 

Portenta X8:
- boot the Portenta X8 by plugging a TypeC USB in it prefferably in a laptop so you also get the network connectivity for first time setup of the Wifi.
- clone the [IoT trinity](https://github.com/arduino/portenta-containers/tree/release/iot-trinity) container that will provide us with the InfluxDB timeseries database
- clone our modified container from this repo > Portenta X8 folder and use scp to transfer it on the Portenta (be sure to replace the Ble Macs accordingly with your hardware)
- start the IoT trinity container first then the python-ble-scanner secondly to capture the data from the ble Devices

## Authors
   [Zalmotek team](https://zalmotek.com/)

## Acknowledgments
  - The amazing Arduino Documentation and support!

