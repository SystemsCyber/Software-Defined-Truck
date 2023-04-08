#include <Arduino.h>
#include <SensorNode/SensorNode.h>
#include <CANNode/CANNode.h>

int SensorNode::unpackSensorBlock(struct WSensorBlock &sensorBlock, uint8_t *msgBuffer)
{
    // print address of msgBuffer in sensor node
    int size = CANNode::read(msgBuffer, 1);
    if (size > 0)
    {
        memcpy(&sensorBlock.numSignals, msgBuffer, 1);
        if (sensorBlock.numSignals > 0)
        {
            if (sensorBlock.numSignals > 16)
                sensorBlock.numSignals = 16;
            sensorBlock.signals = signals;
            size_t readSize = sensorBlock.numSignals * sizeof(float);
            size += CANNode::read(&msgBuffer[1], readSize);
            if (size == (int)(1 + readSize))
            {
                memcpy(sensorBlock.signals, &msgBuffer[1], readSize);
            }
        }
    }
    return size;
}

int SensorNode::packSensorBlock(struct WSensorBlock &sensorBlock, uint8_t *msgBuffer)
{
    memcpy(msgBuffer, &sensorBlock.numSignals, 1);
    memcpy(&msgBuffer[1], sensorBlock.signals, sensorBlock.numSignals * sizeof(float));
    return 1 + sensorBlock.numSignals * sizeof(float);
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