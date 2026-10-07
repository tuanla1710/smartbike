#include "imu.h"

#include "i2c_bus.h"

#define BMI270_ADDR 0x68
#define BMI270_CHIP_ID 0x24

bool imu_present(void)
{
    uint8_t reg = 0x00;
    uint8_t id = 0;
    if (i2c_bus_write_read(BMI270_ADDR, &reg, 1, &id, 1) != ESP_OK) {
        return false;
    }
    return id == BMI270_CHIP_ID;
}
