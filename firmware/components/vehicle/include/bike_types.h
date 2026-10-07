#pragma once

#include <stdbool.h>
#include <stdint.h>

#define BIKE_SW_LEFT 0
#define BIKE_SW_RIGHT 1
#define BIKE_SW_HORN 2
#define BIKE_SW_LIGHT 3
#define BIKE_SW_BRAKE 4
#define BIKE_SW_HAZARD 5
#define BIKE_SW_N 6

#define BIKE_LOAD_HEAD 0
#define BIKE_LOAD_TAIL 1
#define BIKE_LOAD_LEFT 2
#define BIKE_LOAD_RIGHT 3
#define BIKE_LOAD_BRAKE 4
#define BIKE_LOAD_HORN 5
#define BIKE_LOAD_AUX 6
#define BIKE_LOAD_N 7

#define BIKE_I2C_INA 0
#define BIKE_I2C_LUX 1
#define BIKE_I2C_LIDAR 2
#define BIKE_I2C_IMU 3
#define BIKE_I2C_N 4

#define BIKE_GPS_NONE 0
#define BIKE_GPS_FIX 1
#define BIKE_GPS_BAD 2

#define BIKE_RESET_POWER 0
#define BIKE_RESET_WDT 1
#define BIKE_RESET_DEEPSLEEP 2

typedef struct {
    bool pressed[BIKE_SW_N];
    uint16_t lux;
    bool range_valid;
    uint16_t range_mm;
    bool motion;
    bool gpio38;
    uint16_t bus_mv;
    bool power_alive;
    bool i2c[BIKE_I2C_N];
    uint16_t loads_ma[BIKE_LOAD_N];
    int gps_mode;
    double gps_lat;
    double gps_lon;
    bool use_measured_i;
    int16_t measured_ma;
} bike_plant_t;

static inline uint32_t bike_elapsed(uint32_t now, uint32_t since)
{
    return now - since;
}
