#pragma once

void bike_config_load(int *horn_current_ma, int *shunt_cal);
int bike_config_save(const char *key, int value);
