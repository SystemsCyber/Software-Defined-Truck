#include <Arduino.h>
#include <ArduinoJson.h>
#include <SD.h>
#include <SPI.h>
#include <Configuration/LoadConfiguration.h>
#include <array>

LoadConfiguration::LoadConfiguration(): exConfigWithIP(512), exConfigWithFQDN(512), exECU1(256),
                                        exECU2(256), mac{0}, config(1024)                   
{
    exECU1["sn"] = "1a2b3c4d";
    exECU1["make"] = "Cummins";
    exECU1["model"] = "theModel";
    exECU1["year"] = 1999;
    JsonArray ecuType1 = exECU1.createNestedArray("type");
    ecuType1.add("ECU");
    ecuType1.add("Electronic Control Unit");

    exECU2["sn"] = "a1b2c3d4";
    exECU2["make"] = "Detroit Desiel";
    exECU2["model"] = "theModel";
    exECU2["year"] = 2000;
    JsonArray ecuType2 = exECU2.createNestedArray("type");
    ecuType2.add("ECM");
    ecuType2.add("Engine Control Module");

    exConfigWithIP["serverAddress"] = "123.456.789.101";
    JsonArray ecus1 = exConfigWithIP.createNestedArray("ECUs");
    ecus1.add(exECU1);
    ecus1.add(exECU2);

    exConfigWithFQDN["serverAddress"] = "aHostName";
    JsonArray ecus2 = exConfigWithFQDN.createNestedArray("ECUs");
    ecus2.add(exECU1);
    ecus2.add(exECU2);
};

void LoadConfiguration::init()
{
    File file = initializeSD("config.txt");
    deserializeConfiguration(file);
    file.close();
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

void LoadConfiguration::deserializeConfiguration(File file)
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
        serializeJsonPretty(config, Serial);
    }
    else
    {
        Serial.println("Done.");
        config["MAC"] = readMACAddress();
        Serial.println("Configuration read from SD card:");
        serializeJsonPretty(config, Serial);
    }
}

String LoadConfiguration::readMACAddress()
{
    // From http://forum.pjrc.com/threads/91-teensy-3-MAC-address 

    // Retrieve the 6 byte MAC address Paul burnt into two 32 bit words
    // at the end of the "READ ONCE" area of the flash controller.
    Serial.print("Reading Teensy's burned-in MAC address...");
    readLowLevelData(0xe,0);
    readLowLevelData(0xf,3);
    String macString = "";
    for(uint8_t i = 0; i < 6; ++i) {
        if (i!=0) macString += ":";
        macString += String((*(mac+i) & 0xF0) >> 4, 16);
        macString += String(*(mac+i) & 0x0F, 16);
    }
    Serial.println("Done");
    return macString;
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