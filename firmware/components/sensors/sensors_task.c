#include "bike_ctrl.h"
#include "bike_port.h"
#include "bike_types.h"
#include "board.h"
#include "i2c_bus.h"
#include "imu.h"
#include "ina228.h"
#include "lidar.h"
#include "light.h"

#include "esp_task_wdt.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static void publish(bool ina_ok, uint16_t bus_mv, int16_t current_ma, bool lux_ok, uint16_t lux,
                    bool lidar_ok, bool imu_ok)
{
    bike_port_lock();
    bike_plant_t *plant = bike_plant();
    plant->i2c[BIKE_I2C_INA] = ina_ok;
    plant->i2c[BIKE_I2C_LUX] = lux_ok;
    plant->i2c[BIKE_I2C_LIDAR] = lidar_ok;
    plant->i2c[BIKE_I2C_IMU] = imu_ok;
    if (ina_ok) {
        plant->power_alive = true;
        plant->bus_mv = bus_mv;
        plant->measured_ma = current_ma;
        plant->use_measured_i = true;
    } else {
        plant->power_alive = false;
    }
    if (lux_ok) {
        plant->lux = lux;
    }
    bike_port_unlock();
}

static void sensors_task(void *arg)
{
    (void)arg;
    esp_task_wdt_add(NULL);
    bool light_ready = false;
    int last_cal = -1;
    TickType_t wake = xTaskGetTickCount();
    uint32_t lux_wait = 0;
    for (;;) {
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(50));
        esp_task_wdt_reset();
        bike_port_lock();
        bool sleeping = bike_sleep_pending();
        int cal = bike_shunt_cal();
        bike_port_unlock();
        if (sleeping) {
            board_xshut(false);
            continue;
        }
        board_xshut(true);
        if (i2c_bus_init() != ESP_OK) {
            publish(false, 0, 0, false, 0, false, false);
            vTaskDelay(pdMS_TO_TICKS(1000));
            wake = xTaskGetTickCount();
            continue;
        }
        if (cal != last_cal) {
            if (ina228_init((uint16_t)cal) == ESP_OK) {
                last_cal = cal;
            }
        }
        uint16_t bus_mv = 0;
        int16_t current_ma = 0;
        bool ina_ok = ina228_read(&bus_mv, &current_ma) == ESP_OK;
        if (!light_ready) {
            light_ready = light_start() == ESP_OK;
        }
        uint16_t lux = 0;
        bool lux_ok = false;
        lux_wait += 50;
        if (light_ready && lux_wait >= 500) {
            lux_wait = 0;
            lux_ok = light_read(&lux) == ESP_OK;
            if (!lux_ok) {
                light_ready = false;
            }
        }
        publish(ina_ok, bus_mv, current_ma, lux_ok, lux, lidar_present(), imu_present());
    }
}

void sensors_start(void)
{
    xTaskCreate(sensors_task, "sensors", 8192, NULL, 8, NULL);
}
