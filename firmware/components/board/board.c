#include "board.h"

#include "driver/gpio.h"
#include "esp_attr.h"
#include "driver/ledc.h"
#include "esp_rom_gpio.h"
#include "hal/gpio_ll.h"
#include "soc/gpio_sig_map.h"

#define LEDC_MODE LEDC_LOW_SPEED_MODE
#define LEDC_TIMER LEDC_TIMER_0

enum {
    CH_HEAD = LEDC_CHANNEL_0,
    CH_TAIL = LEDC_CHANNEL_1,
    CH_LEFT = LEDC_CHANNEL_2,
    CH_RIGHT = LEDC_CHANNEL_3
};

static const gpio_num_t GATES[] = {
    BOARD_HORN_GATE, BOARD_HEAD_GATE, BOARD_LEFT_GATE, BOARD_RIGHT_GATE,
    BOARD_TAIL_GATE, BOARD_BRAKE_GATE, BOARD_AUX_GATE
};

static const gpio_num_t SWITCHES[] = {
    BOARD_LEFT_SW, BOARD_RIGHT_SW, BOARD_HORN_SW, BOARD_LIGHT_SW, BOARD_BRAKE_SW
};

static void pin_low_output(gpio_num_t pin)
{
    gpio_set_level(pin, 0);
    gpio_set_direction(pin, GPIO_MODE_OUTPUT);
    gpio_set_level(pin, 0);
}

static void ledc_bind(ledc_channel_t channel, int gpio, uint32_t duty)
{
    ledc_set_duty(LEDC_MODE, channel, duty);
    ledc_update_duty(LEDC_MODE, channel);
    ledc_set_pin(gpio, LEDC_MODE, channel);
}

void board_outputs_safe(void)
{
    for (size_t i = 0; i < sizeof GATES / sizeof GATES[0]; i++) {
        pin_low_output(GATES[i]);
    }
    pin_low_output(BOARD_STATUS_LED);
    pin_low_output(BOARD_LIDAR_XSHUT);

    ledc_timer_config_t timer = {
        .speed_mode = LEDC_MODE,
        .duty_resolution = LEDC_TIMER_10_BIT,
        .timer_num = LEDC_TIMER,
        .freq_hz = 1000,
        .clk_cfg = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&timer);

    const ledc_channel_t channels[] = {CH_HEAD, CH_TAIL, CH_LEFT, CH_RIGHT};
    const int pins[] = {BOARD_HEAD_GATE, BOARD_TAIL_GATE, BOARD_LEFT_GATE, BOARD_RIGHT_GATE};
    for (int i = 0; i < 4; i++) {
        ledc_channel_config_t channel = {
            .gpio_num = pins[i],
            .speed_mode = LEDC_MODE,
            .channel = channels[i],
            .intr_type = LEDC_INTR_DISABLE,
            .timer_sel = LEDC_TIMER,
            .duty = 0,
            .hpoint = 0,
        };
        ledc_channel_config(&channel);
    }

    for (size_t i = 0; i < sizeof SWITCHES / sizeof SWITCHES[0]; i++) {
        gpio_config_t cfg = {
            .pin_bit_mask = 1ULL << SWITCHES[i],
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        gpio_config(&cfg);
    }
    gpio_config_t imu = {
        .pin_bit_mask = 1ULL << BOARD_IMU_INT,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    gpio_config(&imu);
}

void board_apply(uint16_t head, uint16_t tail, uint16_t left, uint16_t right,
                 bool brake, bool horn, bool aux)
{
    ledc_bind(CH_HEAD, BOARD_HEAD_GATE, head);
    ledc_bind(CH_TAIL, BOARD_TAIL_GATE, tail);
    ledc_bind(CH_LEFT, BOARD_LEFT_GATE, left);
    ledc_bind(CH_RIGHT, BOARD_RIGHT_GATE, right);
    gpio_set_level(BOARD_BRAKE_GATE, brake ? 1 : 0);
    gpio_set_level(BOARD_HORN_GATE, horn ? 1 : 0);
    gpio_set_level(BOARD_AUX_GATE, aux ? 1 : 0);
}

void IRAM_ATTR board_failsafe_isr(void)
{
    for (size_t i = 0; i < sizeof GATES / sizeof GATES[0]; i++) {
        int pin = GATES[i];
        esp_rom_gpio_connect_out_signal(pin, SIG_GPIO_OUT_IDX, false, false);
        gpio_ll_set_level(&GPIO, pin, 0);
    }
}

void board_status_led(bool on)
{
    gpio_set_level(BOARD_STATUS_LED, on ? 1 : 0);
}

void board_xshut(bool high)
{
    gpio_set_level(BOARD_LIDAR_XSHUT, high ? 1 : 0);
}

bool board_switch_closed(int index)
{
    if (index < 0 || index >= (int)(sizeof SWITCHES / sizeof SWITCHES[0])) {
        return false;
    }
    return gpio_get_level(SWITCHES[index]) == 0;
}

bool board_imu_level(void)
{
    return gpio_get_level(BOARD_IMU_INT) != 0;
}
