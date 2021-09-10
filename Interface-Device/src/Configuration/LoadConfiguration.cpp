#include <Arduino.h>
#include <IPAddress.h>
#include <ArduinoJson.h>
#include <SD.h>
#include <SPI.h>
#include <Configuration/LoadConfiguration.h>
#include <array>

LoadConfiguration::LoadConfiguration(const char *filename) : _filename(filename)
{
    File file = initializeSD(filename);
    DeserializationError error = deserializeJson(config, file);
    if (error)
    {
        printDefaultSDFormatOnError();
    }
    serializeJson(config, config_as_string)
    char macPtr[18];
    strncpy(macPtr, config["mac"], (size_t)18);
    mac = stringToByte(macPtr, ":", 16);

    strncpy(FQDN, config["serverIP"], (size_t)256);
    if (FQDN[0] >= '0' && FQDN[0] <= '9')
    {
        serverIP = stringToByte(FQDN, ".", 10).data();
    }

    serverPort = config["serverPort"].as<unsigned short>() | 41660;
    strncpy(attachedDevice.type, config["attachedDevice"]["type"], (size_t)8);
    attachedDevice.year = config["attachedDevice"]["year"].as<unsigned short>();
    strncpy(attachedDevice.make, config["attachedDevice"]["make"], (size_t)11);
    strncpy(attachedDevice.model, config["attachedDevice"]["model"], (size_t)11);

    file.close();
    printConfiguration();
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

void LoadConfiguration::printDefaultSDFormatOnError()
{
    Serial.println("Failed to read file, using default configuration.");
    Serial.println("The default format for the SSS3 SD card is:");
    Serial.println("{");
    Serial.println("\t\"mac\":\"AB:CD:EF:GH:IJ:KL\",");
    Serial.println("\t\"serverIP\":\"123.456.789.101\",");
    Serial.println("\t\"serverPort\":\"12345\",");
    Serial.println("\t\"attachedDevice\":\"ECM_CM2150_200k\"");
    Serial.println("}");
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
    Serial.print("MAC: ");
    for (size_t i = 0; i < sizeof(mac); i++)
    {
        Serial.print(mac[i], HEX);
    }
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
    Serial.print("Server Port: ");
    Serial.println(serverPort);
    Serial.println("Attached Device: ");
    Serial.print("\tType: ");
    Serial.println(attachedDevice.type);
    Serial.print("\tYear: ");
    Serial.println(attachedDevice.year);
    Serial.print("\tModel: ");
    Serial.println(attachedDevice.make);
    Serial.print("\tMake: ");
    Serial.println(attachedDevice.model);
}