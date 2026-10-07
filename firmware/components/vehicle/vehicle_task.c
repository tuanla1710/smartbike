#include "bike_ctrl.h"
#include "bike_port.h"
#include "board.h"

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static bool s_imu_prev;

static void sample_inputs(bike_plant_t *plant)
{
    plant->pressed[BIKE_SW_LEFT] = board_switch_closed(BIKE_SW_LEFT);
    plant->pressed[BIKE_SW_RIGHT] = board_switch_closed(BIKE_SW_RIGHT);
    plant->pressed[BIKE_SW_HORN] = board_switch_closed(BIKE_SW_HORN);
    plant->pressed[BIKE_SW_LIGHT] = board_switch_closed(BIKE_SW_LIGHT);
    plant->pressed[BIKE_SW_BRAKE] = board_switch_closed(BIKE_SW_BRAKE);
    bool level = board_imu_level();
    bool rising = level && !s_imu_prev;
    s_imu_prev = level;
    plant->gpio38 = level;
    plant->motion = rising;
}

static void vehicle_task(void *arg)
{
    (void)arg;
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(10));
        uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
        bike_port_lock();
        sample_inputs(bike_plant());
        bike_step(now, NULL);
        bike_rtc_capture();
        bike_port_unlock();
    }
}

void vehicle_start(void)
{
    xTaskCreate(vehicle_task, "vehicle", 4096, NULL, 10, NULL);
}
