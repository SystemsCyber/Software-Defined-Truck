#include <Arduino.h>
#include <PTPClient/PTPClient.h>

PTPClient::PTPClient() : logging(false) {}

PTPClient::PTPClient(Logging *logger) : logger(logger), logging(true) {}

void PTPClient::start(uint8_t numMembers, uint8_t index)
{
    numSSSFs = numMembers - 1;
    this->index = index;
}

void PTPClient::stop()
{
    numSSSFs = 0;
    index = 0;
}

void PTPClient::syncUpdate(uint64_t us, uint64_t receivedUS)
{
    syncCount++;
    syncCountOffset = syncCount + index;
    originate = us;
    receive = receivedUS;
}

bool PTPClient::followUpUpdate(uint64_t us, uint64_t actualUS)
{
    if (us == originate) // this is the follow up for the previous sync message
    {
        if (syncCount <= 5 || (syncCountOffset % numSSSFs == 0))
        { // first couple of syncs respond otherwise wait for turn
            if (syncCount == 1)
            { // first sync don't calculate offset just set time
                setTeensyTime(us);
                return false;
            }
            originate = actualUS;
            return true;
        }
        else
        { // Not our turn to sync but we can still calculate offset
            betweenRoundsOffset = calculateOffset(us);
            if ((syncCountOffset + 1) % numSSSFs == 0)
            { // If its the next persons turn to sync lets check this
                Ethernet.maintain();
            }
        }
    }
    return false;
}

void PTPClient::delayUpdate(uint64_t us)
{
    adjustment = calculateOffsetDelay(us);
    setTeensyTime(getTeensyTime() + adjustment);
}

uint32_t PTPClient::getDay()
{
    return (((getEpochTime() / 86400L) + 4) % 7); //0 is Sunday
}
uint32_t PTPClient::getHours()
{
    return ((getEpochTime() % 86400L) / 3600);
}
uint32_t PTPClient::getMinutes()
{
    return ((getEpochTime() % 3600) / 60);
}
uint32_t PTPClient::getSeconds()
{
    return (getEpochTime() % 60);
}

String PTPClient::getFormattedTime()
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

uint64_t PTPClient::getEpochTime()
{
    return (getEpochTimeMS() / MILLISPERSEC);
}

uint64_t PTPClient::getEpochTimeMS()
{
    return (getEpochTimeUS() / MICROSPERMILLIS);
}

uint64_t PTPClient::getEpochTimeUS()
{
    // // handle micros overflow
    // if (micros() < lastRTCSync)
    // {
    //     lastRTCSync = micros();
    // }
    // if ((micros() - lastRTCSync) >= rtcSyncInterval)
    // {
    //     currentEpoch = getTeensyTime();
    //     Serial.print("Current Epoch: ");
    //     Serial.println(currentEpoch);
    //     lastRTCSync = micros();
    // }
    // Epoc returned by the NTP server or Teensy RTC + Time since last sync - 70 years
    // uint64_t timePassed = (micros() - lastRTCSync) * MICROSPERMILLIS;
    // uint64_t timePassed = (micros() - lastRTCSync) * MICROSPERMILLIS;
    // return currentEpoc + timePassed - SEVENTYYEARSMICROS + adjustment;
    // return currentEpoch + timePassed - SEVENTYYEARSMICROS;
    // return currentEpoch + timePassed;
    return getTeensyTime();
}

int64_t PTPClient::calculateOffset(uint64_t us)
{
    return us + (buffer[indexSmallestDelay].delay / 2) - getTeensyTime();
}

int64_t PTPClient::calculateOffsetDelay(uint64_t us)
{
    // Need to convert to signed integers
    t1 = originate;
    t2 = receive;
    t3 = transmit;
    t4 = us;

    buffer[bufferIndex].offset = -((t2 - t1) + (t3 - t4)) / 2;
    buffer[bufferIndex].delay = ((t4 - t1) - (t3 - t2));
    buffer[bufferIndex].time = t4;
    buffer[bufferIndex].used = false;

    // Serial.print("Offset: ");
    // Serial.println(buffer[bufferIndex].offset);
    // Serial.print("Delay: ");
    // Serial.println(buffer[bufferIndex].delay);

    int64_t offset = getPeerUpdate();
    bufferIndex = (bufferIndex + 1) % 8;
    return offset;
}

int64_t PTPClient::getPeerUpdate()
{
    int64_t delay0 = buffer[bufferIndex].delay;
    int64_t offset0 = buffer[bufferIndex].offset;
    int pui = bufferIndex;
    for (int i = 0; i < 8; i++)
    {
        bool smallDelay = buffer[i].delay < buffer[pui].delay;
        bool recent = buffer[i].time >= previousClockUpdate;
        if (smallDelay && recent)
        {
            pui = i;
        }
    }
    int64_t delay1 = buffer[pui].delay;
    int64_t offset1 = buffer[pui].offset;
    int64_t peerUpdate = (buffer[pui].used) ? 0 : offset1;
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
    buffer[pui].used = true;
    previousClockUpdate = buffer[pui].time;
    // Serial.printf("Peer Update Index: %d\n", pui);
    // Serial.printf("Offset: %f\n", double(peerUpdate) / double(MICROSPERSEC));
    return peerUpdate;
}

// Thank you to Dean Blackketter and his clock library:
// https://github.com/blackketter/Clock

// Thank you to Manitou and his Teensy RTC millisecond code found here:
// https://github.com/manitou48/teensy3/blob/master/RTCms.ino

void PTPClient::setTeensyTime(uint64_t newTime)
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

uint32_t PTPClient::glitchlessRead(volatile uint32_t *ptr)
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

uint64_t PTPClient::getTeensyTime()
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