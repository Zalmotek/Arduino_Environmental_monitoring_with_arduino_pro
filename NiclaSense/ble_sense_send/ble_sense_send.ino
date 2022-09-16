/*

  Arduino Nicla Sense ME WEB BLE Sense dashboard demo


  Hardware required: https://store.arduino.cc/nicla-sense-me

  1) Upload this sketch to the Arduino Nano BLE sense board

  2) Open the following web page in the Chrome browser:
  https://arduino.github.io/ArduinoAI/NiclaSenseME-dashboard/

  3) Click on the green button in the web page to connect the browser to the board over BLE


  Web dashboard by D. Pajak

  Device sketch based on example by Sandeep Mistry and Massimo Banzi
  Sketch and web dashboard copy-fixed to be used with the Nicla Sense ME by Pablo Marquínez

*/

#include "Nicla_System.h"
#include "Arduino_BHY2.h"
#include <ArduinoBLE.h>


BLEService service("FFE0");

BLEFloatCharacteristic temperatureCharacteristic("2A1C", BLERead);
BLEUnsignedIntCharacteristic humidityCharacteristic("2A6F", BLERead);
BLEFloatCharacteristic pressureCharacteristic("2AA3", BLERead);
BLEFloatCharacteristic bsecCharacteristic("2BCF", BLERead);
BLEIntCharacteristic  co2Characteristic("2BD0", BLERead);
BLEUnsignedIntCharacteristic gasCharacteristic("27AD", BLERead);

// String to calculate the local and device name
String name;

Sensor temperature(SENSOR_ID_TEMP);
Sensor humidity(SENSOR_ID_HUM);
Sensor pressure(SENSOR_ID_BARO);
SensorBSEC bsec(SENSOR_ID_BSEC);
Sensor gas(SENSOR_ID_GAS);

void setup() {
  Serial.begin(115200);

  Serial.println("Start");

  nicla::begin();
  nicla::leds.begin();
  nicla::leds.setColor(green);

  //Sensors intialization
  BHY2.begin();
  temperature.begin();
  humidity.begin();
  pressure.begin();
  bsec.begin();
  gas.begin();

  if (!BLE.begin()) {
    Serial.println("Failled to initialized BLE!");

    while (1)
      ;
  }

  String address = BLE.address();

  Serial.print("address = ");
  Serial.println(address);

  address.toUpperCase();

  name = "BLESense-Ctin";
  name += address[address.length() - 5];
  name += address[address.length() - 4];
  name += address[address.length() - 2];
  name += address[address.length() - 1];

  Serial.print("name = ");
  Serial.println(name);

  BLE.setLocalName(name.c_str());
  BLE.setDeviceName(name.c_str());
  BLE.setAdvertisedService(service);

  // Add all the previously defined Characteristics
  service.addCharacteristic(temperatureCharacteristic);
  service.addCharacteristic(humidityCharacteristic);
  service.addCharacteristic(pressureCharacteristic);
  service.addCharacteristic(bsecCharacteristic);
  service.addCharacteristic(co2Characteristic);
  service.addCharacteristic(gasCharacteristic);

  // Disconnect event handler
  BLE.setEventHandler(BLEDisconnected, blePeripheralDisconnectHandler);

  // Sensors event handlers
  temperatureCharacteristic.setEventHandler(BLERead, onTemperatureCharacteristicRead);
  humidityCharacteristic.setEventHandler(BLERead, onHumidityCharacteristicRead);
  pressureCharacteristic.setEventHandler(BLERead, onPressureCharacteristicRead);
  bsecCharacteristic.setEventHandler(BLERead, onBsecCharacteristicRead);
  co2Characteristic.setEventHandler(BLERead, onCo2CharacteristicRead);
  gasCharacteristic.setEventHandler(BLERead, onGasCharacteristicRead);

  BLE.addService(service);
  BLE.advertise();
}

void loop() {
  BLE.poll();
  BHY2.update();
  float temperatureValue = temperature.value();
  temperatureCharacteristic.writeValue(temperatureValue);
}

void blePeripheralDisconnectHandler(BLEDevice central) {
  nicla::leds.setColor(red);
}

void onTemperatureCharacteristicRead(BLEDevice central, BLECharacteristic characteristic) {
  float temperatureValue = temperature.value();
  temperatureCharacteristic.writeValue(temperatureValue);
  Serial.print("Temperature was read from remote: ");
  Serial.println(temperatureValue);
}

void onHumidityCharacteristicNotify(BLEDevice central, BLECharacteristic characteristic) {
  uint8_t humidityValue = humidity.value();
  humidityCharacteristic.writeValue(humidityValue);
  Serial.print("Humidity was read from remote: ");
  Serial.println(humidityValue);
}

void onGasCharacteristicRead(BLEDevice central, BLECharacteristic characteristic) {
  unsigned int g = gas.value();
  gasCharacteristic.writeValue(g);
  Serial.print("gas was read from remote: ");
  Serial.println(g );
}


void onHumidityCharacteristicRead(BLEDevice central, BLECharacteristic characteristic) {
  uint8_t humidityValue = humidity.value();
  humidityCharacteristic.writeValue(humidityValue);
  Serial.print("humidityValue was read from remote: ");
  Serial.println(humidityValue);
}

void onPressureCharacteristicRead(BLEDevice central, BLECharacteristic characteristic) {
  float pressureValue = pressure.value();
  pressureCharacteristic.writeValue(pressureValue);
  Serial.print("pressureValue was read from remote: ");
  Serial.println(pressureValue);
}

void onBsecCharacteristicRead(BLEDevice central, BLECharacteristic characteristic) {
  float airQuality = float(bsec.iaq());
  bsecCharacteristic.writeValue(airQuality);
  Serial.print("airQuality was read from remote: ");
  Serial.println(airQuality);
}

void onCo2CharacteristicRead(BLEDevice central, BLECharacteristic characteristic) {
  float co2 = bsec.co2_eq();
  co2Characteristic.writeValue(co2);
  Serial.print("co2 was read from remote: ");
  Serial.println(co2);
}
