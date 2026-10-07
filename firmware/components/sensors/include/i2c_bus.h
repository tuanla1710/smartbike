#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

esp_err_t i2c_bus_init(void);
esp_err_t i2c_bus_write(uint8_t addr, const uint8_t *data, size_t len);
esp_err_t i2c_bus_read(uint8_t addr, uint8_t *data, size_t len);
esp_err_t i2c_bus_write_read(uint8_t addr, const uint8_t *reg, size_t reg_len,
                             uint8_t *data, size_t len);
bool i2c_bus_probe(uint8_t addr);
