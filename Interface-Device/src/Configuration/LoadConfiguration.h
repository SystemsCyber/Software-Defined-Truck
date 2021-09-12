#ifndef load_configuration_h
#define load_configuration_h

#include <Arduino.h>
#include <IPAddress.h>
#include <ArduinoJson.h>
#include <SD.h>
#include <SPI.h>
#include <array>

class LoadConfiguration
{
public:
    // MAC address of WIZnet Device. Hostname is "WIZnet" + last three bytes of the MAC.
    uint8_t mac[6];
    String macString;
    IPAddress serverIP;
    DynamicJsonDocument config;
    char FQDN[256]; // FQDN can be up to 255 characters long.

    LoadConfiguration();

private:
    void readMACAddress();
    void readLowLevelData(uint8_t word, uint8_t loc);
    File initializeSD(const char *filename);
    File fileExists(const char *filename);
    File openFile(const char *filename);
    bool deserializeConfiguration(File file);
    std::array<uint8_t, 6> stringToByte(char *config, const char *delim, int base);
    void printConfiguration();
};

#endif /* load_configuration_h */