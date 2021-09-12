#include <Arduino.h>
#include <IPAddress.h>
#include <ArduinoJson.h>
#include <SD.h>
#include <SPI.h>
#include <Configuration/LoadConfiguration.h>
#include <array>

LoadConfiguration::LoadConfiguration() : mac({0}), config(256)
{
    readMACAddress();
    File file = initializeSD("config.txt");
    deserializeConfiguration(file);

    strncpy(FQDN, config["serverIP"], (size_t)256);
    if (FQDN[0] >= '0' && FQDN[0] <= '9')
    {
        serverIP = stringToByte(FQDN, ".", 10).data();
    }
    
    file.close();
    printConfiguration();
}

void LoadConfiguration::readMACAddress()
{
    // From http://forum.pjrc.com/threads/91-teensy-3-MAC-address 

    // Retrieve the 6 byte MAC address Paul burnt into two 32 bit words
    // at the end of the "READ ONCE" area of the flash controller.
    Serial.print("Reading Teensy's burned-in MAC address...");
    readLowLevelData(0xe,0);
    readLowLevelData(0xf,3);
    for(uint8_t i = 0; i < 6; ++i) {
        if (i!=0) macString += ":";
        macString += String((*(mac+i) & 0xF0) >> 4, 16);
        macString += String(*(mac+i) & 0x0F, 16);
    }
    Serial.println("Done");
}

void LoadConfiguration::readLowLevelData(uint8_t word, uint8_t loc)
{
    // From http://forum.pjrc.com/threads/91-teensy-3-MAC-address 

    // To understand what's going on here, see
    // "Kinetis Peripheral Module Quick Reference" page 85 and
    // "K20 Sub-Family Reference Manual" page 548.

    cli();
    FTFL_FCCOB0 = 0x41;             // Selects the READONCE command
    FTFL_FCCOB1 = word;             // read the given word of read once area
                                    // -- this is one half of the mac addr.
    FTFL_FSTAT = FTFL_FSTAT_CCIF;   // Launch command sequence
    while(!(FTFL_FSTAT & FTFL_FSTAT_CCIF)) {
                                    // Wait for command completion
    }
    *(mac+loc) =   FTFL_FCCOB5;       // collect only the top three bytes,
    *(mac+loc+1) = FTFL_FCCOB6;       // in the right orientation (big endian).
    *(mac+loc+2) = FTFL_FCCOB7;       // Skip FTFL_FCCOB4 as it's always 0.
    sei();
}

File LoadConfiguration::initializeSD(const char *filename)
{
    Serial.print("Initializing SD card...");
    if (!SD.begin(BUILTIN_SDCARD))
    {
        Serial.println("card failed, or not present.");
    }
    else
    {
        Serial.println("card initialized.");
    }
    return fileExists(filename);
}

File LoadConfiguration::fileExists(const char *filename)
{
    Serial.print("The SSS3 configuration file \"");
    Serial.print(filename);
    if (!SD.exists(filename))
    {
        Serial.println("\" could not be found.");
    }
    else
    {
        Serial.println("\" was located.");
    }
    return openFile(filename);
}

File LoadConfiguration::openFile(const char *filename)
{
    File file = SD.open(filename);
    if (file.available())
    {
        Serial.print("Reading ");
        Serial.print(filename);
        Serial.println("...");
    }
    else
    {
        Serial.print(filename);
        Serial.println(" is empty!!");
    }
    return file;
}

bool LoadConfiguration::deserializeConfiguration(File file)
{
    Serial.print("Deserializing the configuration file into a JSON object...");
    DeserializationError error = deserializeJson(config, file);
    if (error)
    {
        Serial.println();
        Serial.print(F("Deserializing the configuration file failed with code "));
        Serial.println(error.f_str());
        Serial.println();
        Serial.println("The default format for the SSS3 SD card is:");
        Serial.println("{");
        Serial.println("\t\"serverIP\":\"123.456.789.101\",");
        Serial.println("\t\"attachedDevice\":\"ECM_CM2150_200k\"");
        Serial.println("}");
    }
    else
    {
        Serial.println("Done.");
        Serial.print("Adding MAC address to the registration JSON...");
        config["MAC"] = macString;
        Serial.println("Done.");
    }
}

std::array<uint8_t, 6> LoadConfiguration::stringToByte(char *config, const char *delim, int base)
{
    std::array<uint8_t, 6> byteArray;
    char *splitPtr = strtok(config, delim);
    for (int i = 0; i < 5; i++)
    {
        byteArray[i] = (uint8_t)strtol(splitPtr, nullptr, base);
        splitPtr = strtok(NULL, delim);
    }
    byteArray[5] = (uint8_t)strtol(splitPtr, nullptr, base);
    return byteArray;
}

void LoadConfiguration::printConfiguration()
{
    Serial.println("Configuration read from SD card:");
    Serial.println("MAC: " + macString);
    Serial.println();
    if (FQDN[0] >= '0' && FQDN[0] <= '9')
    {
        Serial.print("Server IP: ");
        Serial.println(serverIP);
    }
    else
    {
        Serial.print("Server FQDN: ");
        Serial.println(FQDN);
    }
    String type = config["attachedDevice"]["type"];
    String year = config["attachedDevice"]["year"];
    String model = config["attachedDevice"]["model"];
    String make = config["attachedDevice"]["make"];
    Serial.println("Attached Device: ");
    Serial.println("\tType: " + type);
    Serial.println("\tYear: " + year);
    Serial.println("\tModel: " + model);
    Serial.println("\tMake: " + make);
}