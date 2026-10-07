#pragma once

#include <stdbool.h>

void bike_port_init(void);
void bike_port_lock(void);
void bike_port_unlock(void);
bool bike_rtc_from_sleep(void);
void bike_rtc_capture(void);
