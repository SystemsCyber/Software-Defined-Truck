/**
 * Much of this code comes from the Arduino NTPClient library created by Fabrice
 * Weinberg.
 */

#include <Arduino.h>
#include <TimeClient/TimeClient.h>
#include <EthernetUdp.h>
#include <ArduinoLog.h>
#include <inttypes.h>
#include <math.h>
#include <Dns.h>
#include <IPAddress.h>

TimeClient::TimeClient() : logging(false) {}
TimeClient::TimeClient(Logging *_logger) : logger(_logger), logging(true) {}

TimeClient::~TimeClient()
{
    ntpSock.stop();
}

void TimeClient::setup()
{
    ntpSock.begin(NTP_DEFAULT_LOCAL_PORT);
    for (int i = 0; i < 3; i++)
    {
        if (tryNTPServer(i))
        {
            getAddrInfo();
            break;
        }
    }
    if (logging)
    {
        logger->noticeln("Chosen NTP Server: %s.", ntpServer);
        logger->noticeln("Inital NTP polling interval: 2s.");
        logger->noticeln("Synchronizing with the NTP server for the first time.");
    }
    udpSetup = true;
    delay((pow(2, pollingInterval) * MILLISPERSEC));
    Teensy3Clock.compensate(500);
    update();
}

void TimeClient::update()
{
    if (!udpSetup)
        setup();

    if (status == Sent)
    {
        recvNTPPacket();
        if (status == Received)
            setPollingInterval();
    }
    else if ((millis() - lastUpdate) >= (pow(2, pollingInterval) * MILLISPERSEC))
    {
        sendNTPPacket();
        Ethernet.maintain(); //Only tries to renew if 3/4 through lease
    }

    if (status == Timedout)
    {
        setPollingInterval();
        lastUpdate = millis();
        status = NotSet;
    }
}

uint32_t TimeClient::getDay()
{
    return (((getEpochTime() / 86400L) + 4) % 7); //0 is Sunday
}
uint32_t TimeClient::getHours()
{
    return ((getEpochTime() % 86400L) / 3600);
}
uint32_t TimeClient::getMinutes()
{
    return ((getEpochTime() % 3600) / 60);
}
uint32_t TimeClient::getSeconds()
{
    return (getEpochTime() % 60);
}

String TimeClient::getFormattedTime()
{
    unsigned long rawTime = getEpochTime();
    unsigned long hours = (rawTime % 86400L) / 3600;
    String hoursStr = hours < 10 ? "0" + String(hours) : String(hours);

    unsigned long minutes = (rawTime % 3600) / 60;
    String minuteStr = minutes < 10 ? "0" + String(minutes) : String(minutes);

    unsigned long seconds = rawTime % 60;
    String secondStr = seconds < 10 ? "0" + String(seconds) : String(seconds);

    return hoursStr + ":" + minuteStr + ":" + secondStr;
}

uint64_t TimeClient::getEpochTime()
{
    return (getEpochTimeMS() / MILLISPERSEC);
}

uint64_t TimeClient::getEpochTimeMS()
{
    return (getEpochTimeUS() / MICROSPERMILLIS);
}

uint64_t TimeClient::getEpochTimeUS()
{
    if ((millis() - lastSync) >= syncInterval)
    {
        currentEpoc = getTeensyTime();
        lastSync = millis();
    }
    // Epoc returned by the NTP server or Teensy RTC + Time since last sync - 70 years
    uint64_t timePassed = (millis() - lastSync) * MICROSPERMILLIS;
    // return currentEpoc + timePassed - SEVENTYYEARSMICROS + adjustment;
    return currentEpoc + timePassed - SEVENTYYEARSMICROS;
}

void TimeClient::setPollingInterval()
{
    if (status == Received)
    {
        if (session)
        {
            if (pollingInterval < 4)
            {
                pollingInterval++;
                if (logging)
                    logger->notice("Increasing NTP polling interval to: ");
                    logger->noticeln("%ds.", int(pow(2, pollingInterval)));
            }
            else if (pollingInterval > 4)
            {
                pollingInterval = 4;
            }
        }
        else
        {
            if (pollingInterval < 7)
            {
                if (logging)
                    logger->notice("Increasing NTP polling interval to: ");
                    logger->noticeln("%ds.", int(pow(2, pollingInterval)));
                pollingInterval++;
            }
            else if (pollingInterval > 7)
            {
                pollingInterval = 7;
            }
        }
    }
    else if (status == Timedout)
    {
        if (logging)
            logger->errorln("Unable to reach NTP server. Doubling update interval.");
        pollingInterval++;
    }
}

uint64_t TimeClient::timeFromNTPTimestamp(uint64_t timestamp)
{
    uint64_t secs = (timestamp >> 32) * MICROSPERSEC;
    uint64_t frac = (timestamp & 0xffffffff) * MICROSPERSEC;
    uint64_t us = frac >> 32;
    if (uint32_t(frac) >= 0x80000000)
        us++;
    return (secs + us);
}

void TimeClient::makeNTPPacket(bool firstTime)
{
    // set all bytes in the buffer to 0
    memset(packetBuffer, 0, NTP_PACKET_SIZE);
    // Initialize values needed to form NTP request
    packetBuffer[0] = 0b11100011;      // LI, Version, Mode
    packetBuffer[1] = 0;               // Stratum, or type of clock
    packetBuffer[2] = pollingInterval; // Polling Interval.
    packetBuffer[3] = 0xEC;            // Peer Clock Precision
    // 8 bytes of zero for Root Delay & Root Dispersion
    packetBuffer[12] = 49;
    packetBuffer[13] = 0x4E;
    packetBuffer[14] = 49;
    packetBuffer[15] = 52;

    // Instead of insterting originate timestamp into ntp packet we just save it
    // in a variable.
    if (!firstTime)
        originate = getTeensyTime();
}

void TimeClient::sendNTPPacket(bool firstTime)
{
    int resolved = 0;
    if (ipTranslated)
    {
        resolved = ntpSock.beginPacket(ntpIP, 123);
    }
    else
    {
        resolved = ntpSock.beginPacket(ntpServer, 123);
    }
    if (resolved)
    {
        makeNTPPacket(firstTime);
        ntpSock.write(packetBuffer, NTP_PACKET_SIZE);
        if (ntpSock.endPacket())
        {
            status = Sent;
            sentNTPPacket = millis();
        }
        else
        {
            logger->errorln("Failed to send NTP packet.");
        }
    }
    else
    { // Server is not available.
        status = Timedout;
    }
}

int64_t TimeClient::getPeerUpdate()
{
    // Serial.printf("Current Index: %d\n", bufferIndex);
    // Serial.printf("Recent Delay: %f\n", double(ntpBuffer[bufferIndex].delay) / double(MICROSPERSEC));
    // Serial.printf("Recent Offset: %f\n", double(ntpBuffer[bufferIndex].offset) / double(MICROSPERSEC));
    // Recent delay and offset
    int64_t delay0 = ntpBuffer[bufferIndex].delay;
    int64_t offset0 = ntpBuffer[bufferIndex].offset;
    int pui = bufferIndex;
    for (int i = 0; i < 8; i++)
    {
        bool smallDelay = ntpBuffer[i].delay < ntpBuffer[pui].delay;
        bool recent = ntpBuffer[i].time >= previousClockUpdate;
        if (smallDelay && recent)
        {
            pui = i;
        }
    }
    int64_t delay1 = ntpBuffer[pui].delay;
    int64_t offset1 = ntpBuffer[pui].offset;
    int64_t peerUpdate = (ntpBuffer[pui].used) ? 0 : offset1;
    if (peerUpdate != 0)
    {// Hush and Puff algorithm
        if (offset0 > offset1)
        {
            peerUpdate -= ((delay0 - delay1) / 2);
        }
        else if (offset0 < offset1)
        {
            peerUpdate += ((delay0 - delay1) / 2);
        }
    }
    ntpBuffer[pui].used = true;
    previousClockUpdate = ntpBuffer[pui].time;
    // Serial.printf("Peer Update Index: %d\n", pui);
    // Serial.printf("Offset: %f\n", double(peerUpdate) / double(MICROSPERSEC));
    return peerUpdate;
}

int64_t TimeClient::calculateOffset(bool firstTime)
{
    // If its the first time the system clock is too far off to use the proper
    // clock synchronization algorithm so we instead get the RTT/2.
    if (firstTime)
    {
        return (millis() - (millis() - sentNTPPacket)) / 2.0;
    }
    else
    {
        // Need to convert to signed integers
        int64_t t1 = originate;
        int64_t t2 = receive;
        int64_t t3 = transmit;
        int64_t t4 = getTeensyTime();

        ntpBuffer[bufferIndex].offset = ((t2 - t1) + (t3 - t4)) / 2;
        ntpBuffer[bufferIndex].delay = ((t4 - t1) - (t3 - t2));
        ntpBuffer[bufferIndex].time = t4;
        ntpBuffer[bufferIndex].used = false;

        int64_t offset = getPeerUpdate();
        bufferIndex = (bufferIndex + 1) % 8;
        return offset;
    }
}

uint64_t TimeClient::readTimestamp(int start)
{
    uint64_t timestamp = uint64_t(word(packetBuffer[start], packetBuffer[start + 1])) << 48;
    timestamp |= uint64_t(word(packetBuffer[start + 2], packetBuffer[start + 3])) << 32;
    timestamp |= uint64_t(word(packetBuffer[start + 4], packetBuffer[start + 5])) << 16;
    timestamp |= uint64_t(word(packetBuffer[start + 6], packetBuffer[start + 7]));
    return timestamp;
}

void TimeClient::recvNTPPacket(bool firstTime)
{
    if (status == Sent && ntpSock.parsePacket())
    {
        ntpSock.read(packetBuffer, NTP_PACKET_SIZE);
        receive = timeFromNTPTimestamp(readTimestamp(32));
        transmit = timeFromNTPTimestamp(readTimestamp(40));

        int64_t offset = calculateOffset(firstTime);
        currentEpoc = transmit + offset;
        setTeensyTime(currentEpoc);

        status = Received;
        lastUpdate = millis();
    }
    else if (millis() - sentNTPPacket >= 3000)
    {
        status = Timedout;
    }
}

bool TimeClient::firstUpdate()
{
    sendNTPPacket(true);
    while (true)
    {
        delay(10);
        recvNTPPacket(true);
        if (status == Received)
        {
            return true;
        }
        if (status == Timedout)
        {
            return false;
        }
    }
}

bool TimeClient::tryNTPServer(int index)
{
    if (logging)
    {
        logger->noticeln("Trying the NTP server \"%s\".", ntpServers[index]);
    }
    ntpServer = ntpServers[index];
    if (firstUpdate())
    {
        if (logging)
        {
            logger->noticeln("Successfully reached the NTP server \"%s\".", ntpServers[index]);
        }
        return true;
    }
    else if (logging)
    {
        logger->errorln("Failed to reach the NTP server \"%s\".", ntpServers[index]);
        if (index == 2)
        {
            logger->error("No NTP servers could be reached. ");
            logger->errorln("Defaulting to \"%s\".", ntpServers[0]);
        }
    }
    ntpServer = ntpServers[0];
    return false;
}

void TimeClient::getAddrInfo()
{
    if (logging)
        logger->noticeln("Getting the IP for the NTP server: \"%s\".", ntpServer);
    DNSClient dns;
    dns.begin(Ethernet.dnsServerIP());
    if (dns.getHostByName(ntpServer, ntpIP) == 1)
    {
        ipTranslated = true;
        if (logging)
            logger->noticeln("The IP for \"%s\" is: %p.", ntpServer, ntpIP);
    }
    else if (logging)
    {
        logger->errorln("Failed to get the IP for \"%s\".", ntpServer);
    }
}

// Thank you to Dean Blackketter and his clock library:
// https://github.com/blackketter/Clock

// Thank you to Manitou and his Teensy RTC millisecond code found here:
// https://github.com/manitou48/teensy3/blob/master/RTCms.ino

void TimeClient::setTeensyTime(uint64_t newTime)
{
    uint32_t secs = newTime / MICROSPERSEC;
    uint64_t frac = newTime % MICROSPERSEC;
    uint32_t tics = (frac * 32768) / MICROSPERSEC; // a teensy tic is 1/32768

#if defined(ARDUINO_TEENSY31) || defined(ARDUINO_TEENSY36)

    RTC_SR = 0;
    RTC_TPR = tics;
    RTC_TSR = secs;
    RTC_SR = RTC_SR_TCE;

#elif defined(ARDUINO_TEENSY40) || defined(ARDUINO_TEENSY41)

    uint32_t hi, lo;
    hi = secs >> 17;
    lo = (secs << 15) + tics;
    // stop the RTC
    SNVS_HPCR &= ~(SNVS_HPCR_RTC_EN | SNVS_HPCR_HP_TS);
    while (SNVS_HPCR & SNVS_HPCR_RTC_EN)
        ; // wait
    // stop the SRTC
    SNVS_LPCR &= ~SNVS_LPCR_SRTC_ENV;
    while (SNVS_LPCR & SNVS_LPCR_SRTC_ENV)
        ; // wait
    // set the SRTC
    SNVS_LPSRTCLR = lo;
    SNVS_LPSRTCMR = hi;
    // start the SRTC
    SNVS_LPCR |= SNVS_LPCR_SRTC_ENV;
    while (!(SNVS_LPCR & SNVS_LPCR_SRTC_ENV))
        ; // wait
    // start the RTC and sync it to the SRTC
    SNVS_HPCR |= SNVS_HPCR_RTC_EN | SNVS_HPCR_HP_TS;

#endif
}

uint32_t TimeClient::glitchlessRead(volatile uint32_t *ptr)
{
    // Insure the same read twice to avoid 'glitches' For more information:
    // https://community.nxp.com/t5/Kinetis-Microcontrollers/RTC-and-Sub-second-Time/m-p/433586
    uint32_t read1, read2 = 0;
    do
    {
        read1 = *ptr;
        read2 = *ptr;
    } while (read1 != read2);
    return read1;
}

uint64_t TimeClient::getTeensyTime()
{
#if defined(ARDUINO_TEENSY31) || defined(ARDUINO_TEENSY36)

    uint32_t secs = glitchlessRead(&RTC_TSR);
    uint32_t tics = glitchlessRead(&RTC_TPR);

    //Scale 32.768KHz to microseconds
    uint32_t us = (uint64_t(tics) * MICROSPERSEC) / 32768;

    //if prescaler just rolled over from zero, might have just incremented seconds -- refetch
    if (us < 1000)
        secs = glitchlessRead(&RTC_TSR);

    return ((uint64_t(secs) * MICROSPERSEC) + us);

#elif defined(ARDUINO_TEENSY40) || defined(ARDUINO_TEENSY41)

    uint32_t hi1 = SNVS_HPRTCMR;
    uint32_t lo1 = SNVS_HPRTCLR;
    while (1)
    {
        uint32_t hi2 = SNVS_HPRTCMR;
        uint32_t lo2 = SNVS_HPRTCLR;
        if (lo1 == lo2 && hi1 == hi2)
        {
            uint32_t secs = (hi2 << 17) | (lo2 >> 15);
            uint32_t frac = lo2 & 0x7fff;

            return ((uint64_t(secs) * MICROSPERSEC) + (uint64_t(frac) * MICROSPERSEC)) / 32768;
        }
        hi1 = hi2;
        lo1 = lo2;
    }

#endif
}
// ============================================================================