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
    // Example Configuration Json(s)
    DynamicJsonDocument exConfigWithIP;
    DynamicJsonDocument exConfigWithFQDN;
    DynamicJsonDocument exECU1;
    DynamicJsonDocument exECU2;

public:
    DynamicJsonDocument config;

    Load();
    void init();

private:
    File initializeSD(const char *filename);
    File fileExists(const char *filename);
    File openFile(const char *filename);
    void deserializeConfiguration(File file);
};

#endif /* LOAD_H_ */