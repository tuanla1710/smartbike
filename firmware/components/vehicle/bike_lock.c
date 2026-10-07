#include "bike_port.h"

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static SemaphoreHandle_t s_lock;

void bike_port_init(void)
{
    if (s_lock == NULL) {
        s_lock = xSemaphoreCreateMutex();
    }
}

void bike_port_lock(void)
{
    if (s_lock != NULL) {
        xSemaphoreTake(s_lock, portMAX_DELAY);
    }
}

void bike_port_unlock(void)
{
    if (s_lock != NULL) {
        xSemaphoreGive(s_lock);
    }
}
