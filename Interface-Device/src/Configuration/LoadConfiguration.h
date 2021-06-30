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
private:
    const char *_filename;

public:
    // MAC address of WIZnet Device. Hostname is "WIZnet" + last three bytes of the MAC.
    struct DEVICE
    {
        char type[8];
        uint16_t year;
        char make[11];
        char model[11];
    } attachedDevice;

    std::array<uint8_t, 6> mac;
    IPAddress serverIP;
    char FQDN[256]; // FQDN can be up to 255 characters long.
    unsigned int serverPort;

    LoadConfiguration() : LoadConfiguration("/config.txt") {}
    LoadConfiguration(const char *filename);

private:
    File initializeSD(const char *filename);
    File fileExists(const char *filename);
    File openFile(const char *filename);
    void printDefaultSDFormatOnError();
    std::array<uint8_t, 6> stringToByte(char *config, const char *delim, int base);
    void printConfiguration();
};

#endif /* load_configuration_h */