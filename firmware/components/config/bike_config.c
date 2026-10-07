#include "bike_config.h"
#include "defaults.h"

#include "esp_err.h"
#include "nvs.h"

static const char *NS = "bike";

void bike_config_load(int *horn_current_ma, int *shunt_cal)
{
    int horn = 0;
    int shunt = BIKE_SHUNT_CAL_DEFAULT;
    nvs_handle_t handle;
    if (nvs_open(NS, NVS_READONLY, &handle) == ESP_OK) {
        int32_t value = 0;
        if (nvs_get_i32(handle, "horn_current_ma", &value) == ESP_OK) {
            horn = (int)value;
        }
        if (nvs_get_i32(handle, "shunt_cal", &value) == ESP_OK && value > 0 && value <= 65535) {
            shunt = (int)value;
        }
        nvs_close(handle);
    }
    if (horn_current_ma != NULL) {
        *horn_current_ma = horn;
    }
    if (shunt_cal != NULL) {
        *shunt_cal = shunt;
    }
}

int bike_config_save(const char *key, int value)
{
    if (key == NULL) {
        return -1;
    }
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return -1;
    }
    err = nvs_set_i32(handle, key, value);
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }
    nvs_close(handle);
    return err == ESP_OK ? 0 : -1;
}
