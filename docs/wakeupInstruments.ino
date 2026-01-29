/*
 * This is a test sketch for the NMFTA/NSF CAN Logger 3
 * It uses a Teensy 3.6, two CAN Transceivers and 3 LEDs.
 * The test will light the LEDs upon transmit and toggle the LED on receive.
 * Tests can be conducted with a live network, or the CAN connections can be bridged
 * to so a device can be tested by itself.
 * 
 * The serial monitor may look something like this (with bridged CAN busses):
 * 
CAN1 Message Sent: 2965
0         2964    264216579 00000101 1 8 0F BF 9D C1 00 00 0B 94
CAN0 Message Sent: 1771
1         1770    264266572 00000100 1 8 0F C0 61 11 00 00 06 EA
CAN1 Message Sent: 2966
0         2965    264305572 00000101 1 8 0F C0 F9 69 00 00 0B 95
CAN1 Message Sent: 2967
0         2966    264394564 00000101 1 8 0F C2 55 10 00 00 0B 96
CAN0 Message Sent: 1772
1         1771    264415572 00000100 1 8 0F C2 A7 18 00 00 06 EB
CAN1 Message Sent: 2968
0         2967    264483568 00000101 1 8 0F C3 B0 B9 00 00 0B 97

 */
#include <FlexCAN.h>

//Define message from FlexCAN library
static CAN_message_t txmsg0;
static CAN_message_t txmsg1;
static CAN_message_t rxmsg0;
static CAN_message_t rxmsg1;

//Set up timing variables (Use prime numbers so they don't overlap)
#define TXPeriod0 40
elapsedMillis TXTimer0;

#define TXPeriod1 189
elapsedMillis TXTimer1;


//Create a counter to keep track of message traffic
uint32_t TXCount0 = 0;
uint32_t TXCount1 = 0;
uint32_t RXCount0 = 0;
uint32_t RXCount1 = 0;

//Define LED
#define GREEN_LED_PIN 6
#define RED_LED_PIN 14
#define YELLOW_LED_PIN 5

boolean GREEN_LED_state; 
boolean RED_LED_state;
boolean YELLOW_LED_state;

//Define CAN TXRX Transmission Silent pins
#define SILENT_0 42
#define SILENT_1 41
#define SILENT_2 40

//Define default baudrate
#define BAUDRATE250K 250000
#define BAUDRATE500K 250000


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


void setup() {
  // put your setup code here, to run once:
  //Set baudrate
  Can1.begin(BAUDRATE250K);
  Can0.begin(BAUDRATE250K);
  
  //Set message extension, ID, and length
  txmsg0.ext = 1;
  txmsg0.id=0x100;
  txmsg0.len=8;
  
  txmsg1.ext = 1;
  txmsg1.id=0x101;
  txmsg1.len=8;
  
  // Enable transmission for the CAN TXRX
  pinMode(SILENT_0,OUTPUT);
  pinMode(SILENT_1,OUTPUT);
  pinMode(SILENT_2,OUTPUT);
  digitalWrite(SILENT_0,LOW);
  digitalWrite(SILENT_1,LOW);
  digitalWrite(SILENT_2,LOW);
  
  pinMode(GREEN_LED_PIN,OUTPUT);
  pinMode(RED_LED_PIN,OUTPUT);
  pinMode(YELLOW_LED_PIN,OUTPUT);
  
  //The default filters exclude the extended IDs, so we have to set up CAN filters to allow those to pass.
  CAN_filter_t allPassFilter;
  allPassFilter.ext=1;
  for (uint8_t filterNum = 0; filterNum < 8;filterNum++){ //only use half the available filters for the extended IDs
   Can0.setFilter(allPassFilter,filterNum); 
   Can1.setFilter(allPassFilter,filterNum); 
  }
}


void loop() {
  // put your main code here, to run repeatedly:

  if (Can0.available()) {
    Can0.read(rxmsg0);
    printFrame(rxmsg0,0,RXCount0++);
    //Toggle the LED
    GREEN_LED_state = !GREEN_LED_state;
    digitalWrite(GREEN_LED_PIN,GREEN_LED_state);
  }
  if (Can1.available()) {
    Can1.read(rxmsg1);
    printFrame(rxmsg1,1,RXCount1++);
    //Toggle the LED
    GREEN_LED_state = !GREEN_LED_state;
    digitalWrite(GREEN_LED_PIN,GREEN_LED_state);
  }
  
  if (TXTimer0 >= TXPeriod0){
	  TXTimer0 = 0;//Reset Timer
    TXCount0++;


    // Engine speed at about 50ms
    //0CF00427  [8] FF  FF  FF  00  00  FF  FF  FF
    txmsg0.id = 0x0CF00427;
    memset(&txmsg0.buf[0],0xFF,8);
    txmsg0.buf[3] = 0xC0;
    txmsg0.buf[4] = 0x5D; //0x5DC0 = 24,000 = 3000rpm 
    Can0.write(txmsg0);
    delay(2);
    
    //Speedometer    
    //0CFE6C27  [8] FF  FF  FF  FF  FF  FF  04  00
    txmsg0.id = 0x0CFE6C27;
    memset(&txmsg0.buf[0],0xFF,8);
    txmsg0.buf[6] = 0x00;
    txmsg0.buf[7] = 0x88; // km/h
    Can0.write(txmsg0);
    delay(2);
    
    //Mileage
    //18FEC127  [8] E5  FD  82  06  59  30  07  00
    txmsg0.id = 0x18FEC127;
    txmsg0.buf[0] = 0xE5;
    txmsg0.buf[1] = 0xFD;
    txmsg0.buf[2] = 0x82;
    txmsg0.buf[3] = 0x06; //E5  FD  82  06 = 339417 miles
    txmsg0.buf[4] = 0x59;
    txmsg0.buf[5] = 0x30;
    txmsg0.buf[6] = 0x07;
    txmsg0.buf[7] = 0x00; // 59  30  07  00 = 1463.7 miles (trip)
    Can0.write(txmsg0);
    delay(2);
    
    //18FF3017  [8] 00  FC  F4  F0  0A  FF  FF  FF
//    txmsg0.id = 0x18FF3017;
//    txmsg0.buf[0] = 0x00;
//    txmsg0.buf[1] = 0xFC;
//    txmsg0.buf[2] = 0xF4;
//    txmsg0.buf[3] = 0xF0;
//    txmsg0.buf[4] = 0x0A;
//    txmsg0.buf[5] = 0xFF;
//    txmsg0.buf[6] = 0xFF;
//    txmsg0.buf[7] = 0xFF;
//    Can0.write(txmsg0);
//    delay(2);


    //18FF3227  [8] FF  FF  FF  FF  FF  FF  FF  FF
    txmsg0.id = 0x18FF3227;
    memset(&txmsg0.buf[0],0xFF,8);
    Can0.write(txmsg0);
    delay(2);


    //Dimmer and self test
    //18FF3327  [8] 04  00  FA  00  FA  01  FF  FA
    txmsg0.id = 0x18FF3327;
    txmsg0.buf[0] = 0x04; //01=kills the display, 00=kills needles, 04=normal, 40=make all LCDs turn on 
    //0x10 = Self test cycles through all the lights and counts things on the dash
    txmsg0.buf[1] = 0xFA; //Dimmer for Needles
    txmsg0.buf[2] = 0xFA; //Dimmer for letters, 00=off, FA=brightest
    txmsg0.buf[3] = 0x00; //??
    txmsg0.buf[4] = 0x55; //??
    txmsg0.buf[5] = 0x00;
    txmsg0.buf[6] = 0x00;
    txmsg0.buf[7] = 0x00;
    Can0.write(txmsg0);
    delay(2);

    //Temperature display
    //18FF3427  [8] 04  20  35  35  20  FF  01  00
    txmsg0.id = 0x18FF3427;
    txmsg0.buf[0] = 0xF4; // 0x04=Deg F, 0x01=DegC
    txmsg0.buf[1] = 0x31; //First digit for temperature (ASCII: 0x20 for space, 0x31 for 1)
    txmsg0.buf[2] = 0x36;
    txmsg0.buf[3] = 0x39;
    txmsg0.buf[4] = 0x38; //Small digit in temperature
    txmsg0.buf[5] = 0xFF; //
    txmsg0.buf[6] = 0x01; // 0x01=miles, km otherwise
    txmsg0.buf[7] = 0x01; // 0x01 = Snow on road
    Can0.write(txmsg0);
    delay(2);

//    //18FF3527  [8] 10  16  09  0A  01  00  03  21
//    txmsg0.id = 0x18FF3527;
//    txmsg0.buf[0] = 0x10;
//    txmsg0.buf[1] = 0x16;
//    txmsg0.buf[2] = 0x09;
//    txmsg0.buf[3] = 0x0A;
//    txmsg0.buf[4] = 0x01;
//    txmsg0.buf[5] = 0x00;
//    txmsg0.buf[6] = 0x03;
//    txmsg0.buf[7] = 0x21;
//    Can0.write(txmsg0);
//    delay(2);

    
    //18FF3527  [8] 21  11  11  03  00  00  00  00
    //18FF3527  [8] 22  00  00  00  00  00  00  00
    //18FF3527  [8] 23  00  00  FF  FF  FF  FF  FF
    
//    //18FF3727  [8] 10  1F  14  A0  01  00  01  80
//    txmsg0.id = 0x18FF3727;
//    txmsg0.buf[0] = 0x10;
//    txmsg0.buf[1] = 0x1F;
//    txmsg0.buf[2] = 0x14;
//    txmsg0.buf[3] = 0xA0;
//    txmsg0.buf[4] = 0x01;
//    txmsg0.buf[5] = 0x00;
//    txmsg0.buf[6] = 0x01;
//    txmsg0.buf[7] = 0x80;
//    Can0.write(txmsg0);
//    delay(2);

    
    //18FF3617  [8] 30  00  28  00  00  00  00  00 // CTS
//    txmsg0.id = 0x18FF3617;
//    txmsg0.buf[0] = 0x30;
//    txmsg0.buf[1] = 0x00;
//    txmsg0.buf[2] = 0x28;
//    txmsg0.buf[3] = 0x00;
//    txmsg0.buf[4] = 0x00;
//    txmsg0.buf[5] = 0x00;
//    txmsg0.buf[6] = 0x00;
//    txmsg0.buf[7] = 0x00;
//    Can0.write(txmsg0);

    //18FF3727  [8] 10  1F  14  A0  01  00  01  80
    //18FF3727  [8] 21  07  00  53  65  72  76  69
    //18FF3727  [8] 22  63  65  07  00  41  64  76
    //18FF3727  [8] 23  69  73  65  64  01  00  20
    //18FF3727  [8] 24  00  00  00  00  FF  FF  FF

    
    //18FF3817  [8] 30  00  28  00  00  00  00  00
//    txmsg0.id = 0x18FF3617;
//    txmsg0.buf[0] = 0x30;
//    txmsg0.buf[1] = 0x00;
//    txmsg0.buf[2] = 0x28;
//    txmsg0.buf[3] = 0x00;
//    txmsg0.buf[4] = 0x00;
//    txmsg0.buf[5] = 0x00;
//    txmsg0.buf[6] = 0x00;
//    txmsg0.buf[7] = 0x00;
//    Can0.write(txmsg0);

    //Instrument Lamps
    //18FF3927  [8] 51  55  55  45  55  54  01  00
    //18FF3927  [8] 00  00  00  00  50  00  00  00
    txmsg0.id = 0x18FF3927;
    txmsg0.buf[0] = 0x55; //0x01=PTO, 0x04=??, 0x10=Green Fan Engine, 0x40=Engine Service
    txmsg0.buf[1] = 0x55; //0x01=Left Blinker, 0x04=DPF Regen, 0x10=High Beams, 0x40=Stop Engine
    txmsg0.buf[2] = 0x55; //0x01=ABS, 0x04=Trailer ABS, 0x10=Right Blinker, 0x40=??
    txmsg0.buf[3] = 0x55; //0x01=??, 0x04=??, 0x10=??, 0x40=??
    txmsg0.buf[4] = 0x55; //0x01=Brake, 0x04=Check Engine (gear with exclaimation), 0x10=Seatbelt, 0x40=Parking Brake
    txmsg0.buf[5] = 0x55; //0x01=??, 0x04=Green Engine, 0x10=Hot Exaust, 0x40=??
    txmsg0.buf[6] = 0x00; //Audible Warning: 0x01 = long beep, 0x04 = Chime, 0x40 = short quiet beep, 0x10 = short loud beep
    txmsg0.buf[7] = 0x00; // 0x10 = Audible click, 0x40 = click, 0x01 = tone with clicks, 0x04=??
    Can0.write(txmsg0);
    delay(2);

    //18FF3A27  [8] 55  14  00  00  00  00  00  00
    txmsg0.id = 0x18FF3A27;
    txmsg0.buf[0] = 0x55; //0x01=??, 0x04=HRS label, 0x10=Coolant Tank, 0x40=ESP Lamp
    txmsg0.buf[1] = 0x14;
    txmsg0.buf[2] = 0x55; 
    txmsg0.buf[3] = 0x55;
    txmsg0.buf[4] = 0x55;
    txmsg0.buf[5] = 0x55;
    txmsg0.buf[6] = 0x55;
    txmsg0.buf[7] = 0x55;
    Can0.write(txmsg0);
    delay(2);

    //18FF3B27  [8] 00  00  00  00  00  00  00  00
    txmsg0.id = 0x18FF3B27;
    txmsg0.buf[1] = 0x55;
    txmsg0.buf[2] = 0x55;
    txmsg0.buf[3] = 0x55;
    txmsg0.buf[4] = 0x55;
    txmsg0.buf[5] = 0x55;
    txmsg0.buf[6] = 0x55;
    txmsg0.buf[7] = 0x55;
    Can0.write(txmsg0);
    delay(2);

    //18FF3C27  [8] FF  FF  FF  FF  FF  FF  FF  FF
    txmsg0.id = 0x18FF3C27;
    txmsg0.buf[1] = 0x00;
    txmsg0.buf[2] = 0x55;
    txmsg0.buf[3] = 0x55;
    txmsg0.buf[4] = 0x55;
    txmsg0.buf[5] = 0x55;
    txmsg0.buf[6] = 0x55;
    txmsg0.buf[7] = 0x55;
    Can0.write(txmsg0);
    delay(2);

    //Display Hours
    //18FF3D27  [8] 05  20  37  37  37  33  37  FF
    txmsg0.id = 0x18FF3D27;
    txmsg0.buf[1] = 0x38; // ASCII space and numbers
    txmsg0.buf[2] = 0x36;
    txmsg0.buf[3] = 0x37;
    txmsg0.buf[4] = 0x37;
    txmsg0.buf[5] = 0x37;
    txmsg0.buf[6] = 0x33;
    txmsg0.buf[7] = 0xFF;
    Can0.write(txmsg0);
    delay(2);

    
    //Toggle the LED
    RED_LED_state = !RED_LED_state;
    digitalWrite(RED_LED_PIN,RED_LED_state);
//    Serial.print("CAN0 Message Sent: ");
//    Serial.println(TXCount0);
  }

}
