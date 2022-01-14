#ifndef TIME_DRIFT_INFO  //To get time drift stats
#define TIME_DRIFT_INFO
#endif /* TIME_DRIFT_INFO */

#ifndef W_NTPCLIENT_H_
#define W_NTPCLIENT_H_

#include <Arduino.h>
#include <EthernetUdp.h>
#include <NTPClient.h>
#include <ArduinoLog.h>

class W_NTPClient
{
private:
    const char* ntpServer[3] = {"dailyserver", "time.nist.gov", "pool.ntp.org"};
    int chosenNTPServer = 0;
    bool udpSetup = false;
    EthernetUDP ntpSock;
    NTPClient* timeClient;

    unsigned long  _updateInterval = 60000;
    unsigned long _lastUpdate = 0;

    Logging* logger;
    bool logging;

public:
    W_NTPClient();
    W_NTPClient(Logging* _logger);

    ~W_NTPClient();

    void setup();
    void update();

private:
    bool tryNTPServer(NTPClient* client, int index);
    void setTeensyTime();
};

#endif /* W_NTPCLIENT_H_ */