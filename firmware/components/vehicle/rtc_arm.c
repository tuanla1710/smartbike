#include "bike_ctrl.h"

#include "esp_attr.h"
#include "esp_system.h"

#define RTC_MAGIC 0xB1CE0A11u

typedef struct {
    uint32_t magic;
    uint8_t armed;
    uint8_t crc;
} rtc_arm_t;

static RTC_DATA_ATTR rtc_arm_t s_rtc;

bool bike_rtc_from_sleep(void)
{
    if (esp_reset_reason() != ESP_RST_DEEPSLEEP || s_rtc.magic != RTC_MAGIC) {
        return false;
    }
    uint8_t flag = s_rtc.armed ? 1u : 0u;
    return bike_crc8(&flag, 1) == s_rtc.crc && s_rtc.armed != 0;
}

void bike_rtc_capture(void)
{
    uint8_t armed = 0;
    uint8_t crc = 0;
    bike_export_rtc(&armed, &crc);
    s_rtc.magic = RTC_MAGIC;
    s_rtc.armed = armed;
    s_rtc.crc = crc;
}
