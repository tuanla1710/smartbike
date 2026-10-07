#include "bike_config.h"
#include "bike_ctrl.h"
#include "bike_port.h"
#include "bike_types.h"
#include "ble_status.h"
#include "board.h"
#include "console.h"
#include "gps.h"
#include "sensors_task.h"
#include "vehicle_task.h"

#include "esp_sleep.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "nvs_flash.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static bike_plant_t s_plant;

static int save_nvs(const char *key, int value)
{
    uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
    bike_mark(now);
    int rc = bike_config_save(key, value);
    bike_mark((uint32_t)(esp_timer_get_time() / 1000));
    return rc;
}

static void deep_sleep_hook(void)
{
    bike_rtc_capture();
    board_xshut(false);
    board_failsafe_isr();
    esp_sleep_enable_ext0_wakeup(BOARD_IMU_INT, 1);
    esp_deep_sleep_start();
}

static void IRAM_ATTR failsafe_cb(void *arg)
{
    (void)arg;
    uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
    uint32_t age = bike_elapsed(now, bike_last_kick());
    if (age >= 50u) {
        board_failsafe_isr();
    }
    if (age >= 200u) {
        esp_restart();
    }
}

static void start_failsafe(void)
{
    const esp_timer_create_args_t args = {
        .callback = failsafe_cb,
        .dispatch_method = ESP_TIMER_ISR,
        .name = "failsafe",
    };
    esp_timer_handle_t timer = NULL;
    if (esp_timer_create(&args, &timer) == ESP_OK) {
        esp_timer_start_periodic(timer, 10000);
    }
}

void app_main(void)
{
    board_outputs_safe();

    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    esp_task_wdt_config_t wdt = {
        .timeout_ms = 5000,
        .idle_core_mask = 0,
        .trigger_panic = true,
    };
    if (esp_task_wdt_reconfigure(&wdt) != ESP_OK) {
        esp_task_wdt_init(&wdt);
    }

    bike_port_init();
    bike_plant_init(&s_plant);
    s_plant.power_alive = false;
    for (int i = 0; i < BIKE_I2C_N; i++) {
        s_plant.i2c[i] = false;
    }
    bike_setup(&s_plant, bike_rtc_from_sleep());

    int horn = 0;
    int shunt = 1250;
    bike_config_load(&horn, &shunt);
    bike_restore_saved(horn, shunt);
    bike_rtc_capture();

    bike_hooks_t hooks = {
        .apply = board_apply,
        .led = board_status_led,
        .xshut = board_xshut,
        .deep_sleep = deep_sleep_hook,
        .nvs_save = save_nvs,
    };
    bike_set_hooks(&hooks);
    bike_mark((uint32_t)(esp_timer_get_time() / 1000));

    console_start();
    sensors_start();
    gps_start();
    vehicle_start();
    start_failsafe();
    ble_status_start();
}
