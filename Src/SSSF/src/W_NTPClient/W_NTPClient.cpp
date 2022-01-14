#include <Arduino.h>
#include <W_NTPClient/W_NTPClient.h>
#include <EthernetUdp.h>
#include <NTPClient.h>
#include <ArduinoLog.h>
#include <TimeLib.h>

W_NTPClient::W_NTPClient(): logging(false) {}
W_NTPClient::W_NTPClient(Logging* _logger): logger(_logger), logging(true) {}

W_NTPClient::~W_NTPClient()
{
    delete timeClient;
}

void W_NTPClient::setup()
{
    for (int i = 0; i < 3; i++)
    {
        timeClient = new NTPClient(ntpSock, ntpServer[i]);
        timeClient->begin();
        if (tryNTPServer(timeClient, i))
        {
            break;
        }
        else
        {
            delete timeClient;
        }
    }
    if (logging)
    {
        logger->noticeln("Chosen NTP Server: %s.", ntpServer[chosenNTPServer]);
        logger->noticeln("NTP server sync interval: %d (in milliseconds).", _updateInterval);
        logger->noticeln("Setting Teensy RTC's Sync Provider.");
        logger->noticeln("Setting Teensy RTC's Sync Interval to 1 second.\n");
    }
    setTeensyTime();
    setSyncProvider((getExternalTime)Teensy3Clock.get);
    setSyncInterval(1);
    udpSetup = true;
}

void W_NTPClient::update()
{
    if (!udpSetup) setup();
    if ((millis() - _lastUpdate) >= _updateInterval)
    {
        _lastUpdate = millis();
        if (timeClient->forceUpdate())
        {
            _updateInterval = 60000;
            setTeensyTime();
            Ethernet.maintain(); //Only tries to renew if 3/4 through lease
        }
        else
        {
            Log.errorln("Unable to reach NTP server. Doubling update interval.");
            _updateInterval *= 2;
        }
    }
}

bool W_NTPClient::tryNTPServer(NTPClient* client, int index)
{
    if (logging)
    {
        logger->noticeln("Trying the NTP server \"%s\".", ntpServer[index]);
    }
    if (timeClient->forceUpdate())
    {
        if (logging)
        {
            logger->noticeln("Successfully reached the NTP server \"%s\".", ntpServer[index]);
        }
        chosenNTPServer = index;
        return true;
    }
    else if (logging)
    {
        logger->errorln("Failed to reach the NTP server \"%s\".", ntpServer[index]);
        if (index == 2)
        {
            logger->error("No NTP servers could be reached. ");
            logger->errorln("Defaulting to \"%s\".", ntpServer[0]);
        }
    }
    return false;
}

void W_NTPClient::setTeensyTime()
{
    Teensy3Clock.set(timeClient->getEpochTime());
    setTime(Teensy3Clock.get());
    if ((timeStatus() != timeSet) && logging)
    {
        logger->errorln("Failed to set Teensy's clock.");
    }
}