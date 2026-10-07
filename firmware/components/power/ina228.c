#include "ina228.h"

#include "i2c_bus.h"

#define INA228_ADDR 0x40
#define REG_SHUNT_CAL 0x02
#define REG_VBUS 0x05
#define REG_CURRENT 0x07

static int32_t sign_extend_20(uint32_t word)
{
    int32_t value = (int32_t)((word >> 4) & 0xFFFFFu);
    if ((value & 0x80000) != 0) {
        value |= ~0xFFFFF;
    }
    return value;
}

static esp_err_t write16(uint8_t reg, uint16_t value)
{
    uint8_t cmd[3] = {reg, (uint8_t)(value >> 8), (uint8_t)value};
    return i2c_bus_write(INA228_ADDR, cmd, sizeof cmd);
}

esp_err_t ina228_init(uint16_t shunt_cal)
{
    esp_err_t err = write16(0x00, 0x0000);
    if (err != ESP_OK) {
        return err;
    }
    err = write16(REG_SHUNT_CAL, shunt_cal);
    if (err != ESP_OK) {
        return err;
    }
    return write16(0x01, 0xFB68);
}

esp_err_t ina228_read(uint16_t *bus_mv, int16_t *current_ma)
{
    uint8_t reg = REG_VBUS;
    uint8_t raw[3];
    esp_err_t err = i2c_bus_write_read(INA228_ADDR, &reg, 1, raw, sizeof raw);
    if (err != ESP_OK) {
        return err;
    }
    uint32_t vbus = ((uint32_t)raw[0] << 16) | ((uint32_t)raw[1] << 8) | raw[2];
    int32_t vcode = sign_extend_20(vbus);
    int32_t mv = (int32_t)(((int64_t)vcode * 3125) / 16000);
    if (mv < 0) {
        mv = 0;
    } else if (mv > 65535) {
        mv = 65535;
    }
    reg = REG_CURRENT;
    err = i2c_bus_write_read(INA228_ADDR, &reg, 1, raw, sizeof raw);
    if (err != ESP_OK) {
        return err;
    }
    uint32_t current = ((uint32_t)raw[0] << 16) | ((uint32_t)raw[1] << 8) | raw[2];
    int32_t ccode = sign_extend_20(current);
    int32_t ma = (int32_t)(((int64_t)ccode * 5000) / 524288);
    if (ma > 32767) {
        ma = 32767;
    } else if (ma < -32768) {
        ma = -32768;
    }
    if (bus_mv != NULL) {
        *bus_mv = (uint16_t)mv;
    }
    if (current_ma != NULL) {
        *current_ma = (int16_t)ma;
    }
    return ESP_OK;
}
