#include <FlexCAN_T4.h>

static CAN_message_t rxmsg;
uint32_t RXCount0 = 0;
uint32_t RXCount1 = 0;

//A generic CAN Frame print function for the Serial terminal
void printFrame(CAN_message_t rxmsg, uint8_t channel, uint32_t RXCount)
{
  char CANdataDisplay[50];
  sprintf(CANdataDisplay, "%d %12lu %12lu %08X %d %d", channel, RXCount, micros(), rxmsg.id, rxmsg.ext, rxmsg.len);
  Serial.print(CANdataDisplay);
  for (uint8_t i = 0; i < rxmsg.len; i++) {
    char CANBytes[4];
    sprintf(CANBytes, " %02X", rxmsg.buf[i]);
    Serial.print(CANBytes);
  }
  Serial.println();
}

void can_setup(){
//Initialize the CAN channels with autobaud setting
  Can0.begin(0);
  #if defined(__MK66FX1M0__)
  Can1.begin(0);
  #endif
}

void can_read(){
    while (Can0.read(rxmsg)) {
    printFrame(rxmsg,0,RXCount0++);
    LED_state = !LED_state;
    digitalWrite(LED_BUILTIN, LED_state);
  }
  #if defined(__MK66FX1M0__)
  while (Can1.read(rxmsg)) {
    printFrame(rxmsg,1,RXCount1++);
    LED_state = !LED_state;
    digitalWrite(LED_BUILTIN, LED_state);
   }
}