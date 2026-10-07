#pragma once

#include <stdint.h>

#include "esp_err.h"

esp_err_t light_start(void);
esp_err_t light_read(uint16_t *lux);
