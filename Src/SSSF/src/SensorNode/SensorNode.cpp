#include <Arduino.h>
#include <SensorNode/SensorNode.h>
#include <CANNode/CANNode.h>

int SensorNode::read(struct WSensorBlock *sensorFrame)
{
    return CANNode::read(reinterpret_cast<unsigned char *>(sensorFrame), sizeof(WSensorBlock));
}

int SensorNode::write(struct WSensorBlock *sensorFrame)
{
    return CANNode::write(reinterpret_cast<uint8_t *>(sensorFrame), sizeof(WSensorBlock));
}