#include <Arduino.h>
#include <SensorNode/SensorNode.h>
#include <CANNode/CANNode.h>

int SensorNode::read(struct WSensorBlock *buffer)
{
    uint8_t *buf = reinterpret_cast<uint8_t*>(buffer);
    int recvdHeaders = CANNode::read(buf, 1);
    if (recvdHeaders > 0)
    {
        numSignals = buffer->numSignals;
        int readSize = numSignals * sizeof(float);
        signals = new float[numSignals];
        int recvdData = CANNode::read(reinterpret_cast<uint8_t*>(signals), readSize);
        if (recvdData > 0)
        {
            memcpy(buffer + 1, signals, 4);
            return recvdHeaders + recvdData;
        }
        else
        {
            numSignals = 0;
            delete[] signals;
        }
    }
    return -1;
}

int SensorNode::write(struct WSensorBlock *sensorFrame)
{
    return CANNode::write(reinterpret_cast<uint8_t *>(sensorFrame), sizeof(WSensorBlock));
}

void SensorNode::printSensorBlock(struct WSensorBlock &senseBlock)
{
    Serial.printf("Number of Signals: %d\n", senseBlock.numSignals);
    Serial.println("Signals:");
    for(uint8_t i = 0; i < senseBlock.numSignals; i++)
    {
        Serial.printf("%d: %3f ", i, (senseBlock.signals[i]));
        if (i % 5 == 0) Serial.println();
    }
}