#include "light.h"

#include "i2c_bus.h"

#define BH1750_ADDR 0x23

esp_err_t light_start(void)
{
    uint8_t power = 0x01;
    uint8_t mode = 0x10;
    esp_err_t err = i2c_bus_write(BH1750_ADDR, &power, 1);
    if (err != ESP_OK) {
        return err;
    }
    return i2c_bus_write(BH1750_ADDR, &mode, 1);
}

esp_err_t light_read(uint16_t *lux)
{
    uint8_t raw[2];
    esp_err_t err = i2c_bus_read(BH1750_ADDR, raw, sizeof raw);
    if (err != ESP_OK) {
        return err;
    }
    unsigned value = ((unsigned)raw[0] << 8) | raw[1];
    unsigned converted = (value * 5u) / 6u;
    if (converted > 65535u) {
        converted = 65535u;
    }
    if (lux != NULL) {
        *lux = (uint16_t)converted;
    }
    return ESP_OK;
}
