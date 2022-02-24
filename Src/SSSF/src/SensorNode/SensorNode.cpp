#include <Arduino.h>
#include <SensorNode/SensorNode.h>
#include <CANNode/CANNode.h>

int SensorNode::read(struct WSensorBlock *buffer)
{
    uint8_t *buf = reinterpret_cast<uint8_t*>(buffer);
    int recvdHeaders = CANNode::read(buf, 4);
    if (recvdHeaders > 0)
    {
        numSignals = buffer->numSignals;
        int readSize = numSignals * sizeof(float);
        signals = new float[numSignals];
        int recvdData = CANNode::read(reinterpret_cast<unsigned char*>(signals), readSize);
        if (recvdData > 0)
        {
            buffer->signals = signals;
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

String SensorNode::dumpSensorBlock(struct WSensorBlock &senseBlock)
{
    String msg = "Number of Signals: " + String(senseBlock.numSignals) + "\n";
    msg += "Signals:\n";
    for(uint8_t i = 0; i < senseBlock.numSignals; i++)
    {
        msg += String(i) + ": " + String(senseBlock.signals[i]) + " ";
        if ((i != 0) && (i != senseBlock.numSignals - 1) && (i % 4 == 0))
        {
            msg += "\n";
        }
    }
    msg += "\n";
    return msg;
}