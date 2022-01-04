#include <Arduino.h>
#include <ArduinoJson.h>
#include <SD.h>
#include <SPI.h>
#include <Configuration/Load.h>
#include <array>

Load::Load():
    exConfig(512),
    exECU1(256),
    exECU2(256),
    config(1024)                   
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

    JsonArray ecus1 = exConfig.createNestedArray("attachedDevices");
    ecus1.add(exECU1);
    ecus1.add(exECU2);
};

void Load::init()
{
    File file = initializeSD("config.txt");
    deserializeConfiguration(file);
    file.close();
}

File Load::initializeSD(const char *filename)
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

File Load::fileExists(const char *filename)
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

File Load::openFile(const char *filename)
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

void Load::deserializeConfiguration(File file)
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
        Serial.println("Configuration read from SD card:");
        serializeJsonPretty(config, Serial);
    }
}