#include <Arduino.h>
#include <FlexCAN_T4.h>
#include <server_communication_functions.h>

FlexCAN_T4<CAN1, RX_SIZE_256, TX_SIZE_16> can1;
FlexCAN_T4<CAN2, RX_SIZE_256, TX_SIZE_16> can2;
CAN_message_t msg;

void setup(void) {
  can1.begin();
  can1.setBaudRate(250000);
  can2.begin();
  can2.setBaudRate(250000);
}
int chan_0_idx = 0;
int chan_1_idx = 0;
void loop() {
  if ( can1.read(msg) ) {
    UDP_send_CAN(0; chan_0_idx; msg);
    chan_0_idx++;
  }
  if ( can2.read(msg) ) {
    UDP_send_CAN(1, chan_1_idx, msg);
    chan_1_idx++;
  }
  if ( UDP_receive_CAN(int channel, int channel_idx, UDP_CAN_Package) ) {
    if (channel == 0){
      can1.write(msg);
    }
    else if (channel == 1){
      can2.write(msg);
    }
  }
}