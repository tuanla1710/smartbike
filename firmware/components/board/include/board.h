#pragma once

#include <stdbool.h>
#include <stdint.h>

#define BOARD_LIDAR_XSHUT 4
#define BOARD_LIDAR_INT 5
#define BOARD_HORN_GATE 6
#define BOARD_HEAD_GATE 7
#define BOARD_I2C_SDA 8
#define BOARD_I2C_SCL 9
#define BOARD_LEFT_GATE 10
#define BOARD_RIGHT_GATE 11
#define BOARD_TAIL_GATE 12
#define BOARD_BRAKE_GATE 13
#define BOARD_LEFT_SW 15
#define BOARD_RIGHT_SW 16
#define BOARD_GPS_RX 17
#define BOARD_GPS_TX 18
#define BOARD_HORN_SW 21
#define BOARD_IMU_INT 38
#define BOARD_LIGHT_SW 39
#define BOARD_BRAKE_SW 40
#define BOARD_AUX_GATE 41
#define BOARD_STATUS_LED 42

void board_outputs_safe(void);
void board_apply(uint16_t head, uint16_t tail, uint16_t left, uint16_t right,
                 bool brake, bool horn, bool aux);
void board_failsafe_isr(void);
void board_status_led(bool on);
void board_xshut(bool high);
bool board_switch_closed(int index);
bool board_imu_level(void);
