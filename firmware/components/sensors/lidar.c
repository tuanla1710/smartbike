#include "lidar.h"

#include "i2c_bus.h"

#define VL53L1X_ADDR 0x29

bool lidar_present(void)
{
    return i2c_bus_probe(VL53L1X_ADDR);
}
