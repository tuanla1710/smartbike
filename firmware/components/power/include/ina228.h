#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

esp_err_t ina228_init(uint16_t shunt_cal);
esp_err_t ina228_read(uint16_t *bus_mv, int16_t *current_ma);
