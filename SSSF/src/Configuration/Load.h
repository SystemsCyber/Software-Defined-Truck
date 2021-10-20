#ifndef LOAD_H_
#define LOAD_H_

#include <Arduino.h>
#include <ArduinoJson.h>
#include <SD.h>
#include <SPI.h>
#include <array>

class Load
{
private:
    DynamicJsonDocument exConfigWithIP;
    DynamicJsonDocument exConfigWithFQDN;
    DynamicJsonDocument exECU1;
    DynamicJsonDocument exECU2;

public:
    // MAC address of WIZnet Device. Hostname is "WIZnet" + last three bytes of the MAC.
    uint8_t mac[6];
    DynamicJsonDocument config;

    Load();
    void init();

private:
    File initializeSD(const char *filename);
    File fileExists(const char *filename);
    File openFile(const char *filename);
    void deserializeConfiguration(File file);
    String readMACAddress();
    void readLowLevelData(uint8_t word, uint8_t loc);
};

#endif /* LOAD_H_ */