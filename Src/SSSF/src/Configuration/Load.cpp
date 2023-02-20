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
    exECU1["SN"] = "1a2b3c4d";
    exECU1["Make"] = "Cummins";
    exECU1["Model"] = "theModel";
    exECU1["Year"] = 1999;
    JsonArray ecuType1 = exECU1.createNestedArray("Type");
    ecuType1.add("ECU");
    ecuType1.add("Electronic Control Unit");

    exECU2["SN"] = "a1b2c3d4";
    exECU2["Make"] = "Detroit Desiel";
    exECU2["Model"] = "theModel";
    exECU2["Year"] = 2000;
    JsonArray ecuType2 = exECU2.createNestedArray("Type");
    ecuType2.add("ECM");
    ecuType2.add("Engine Control Module");

    JsonArray ecus1 = exConfig.createNestedArray("AttachedDevices");
    ecus1.add(exECU1);
    ecus1.add(exECU2);

    exConfig["SSSFDevice"] = "SSS3";
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
    Serial.print("The SSSF configuration file \"");
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
        Serial.println("The default format for the SSSF SD card is:");
        serializeJsonPretty(config, Serial);
    }
    else
    {
        Serial.println("Done.");
        Serial.println("Configuration read from SD card:");
        serializeJsonPretty(config, Serial);
        Serial.println("\n");
    }
}