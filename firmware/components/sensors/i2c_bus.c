#include "i2c_bus.h"

#include "board.h"

#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"

static i2c_master_bus_handle_t s_bus;
static int64_t s_recover_us;

static esp_err_t bus_install(void)
{
    i2c_master_bus_config_t cfg = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = BOARD_I2C_SDA,
        .scl_io_num = BOARD_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    return i2c_new_master_bus(&cfg, &s_bus);
}

esp_err_t i2c_bus_init(void)
{
    if (s_bus != NULL) {
        return ESP_OK;
    }
    return bus_install();
}

static void recover_once(void)
{
    int64_t now = esp_timer_get_time();
    if (s_recover_us != 0 && now - s_recover_us < 1000000) {
        return;
    }
    s_recover_us = now;
    if (s_bus != NULL) {
        i2c_del_master_bus(s_bus);
        s_bus = NULL;
    }
    gpio_set_direction(BOARD_I2C_SDA, GPIO_MODE_INPUT);
    gpio_set_pull_mode(BOARD_I2C_SDA, GPIO_PULLUP_ONLY);
    gpio_set_direction(BOARD_I2C_SCL, GPIO_MODE_OUTPUT);
    for (int i = 0; i < 9; i++) {
        gpio_set_level(BOARD_I2C_SCL, 0);
        esp_rom_delay_us(5);
        gpio_set_level(BOARD_I2C_SCL, 1);
        esp_rom_delay_us(5);
    }
    gpio_set_level(BOARD_I2C_SDA, 0);
    bus_install();
}

static esp_err_t transact(uint8_t addr, const uint8_t *tx, size_t tx_len, uint8_t *rx, size_t rx_len)
{
    if (s_bus == NULL && i2c_bus_init() != ESP_OK) {
        return ESP_FAIL;
    }
    if (i2c_master_probe(s_bus, addr, 20) != ESP_OK) {
        recover_once();
        if (s_bus == NULL || i2c_master_probe(s_bus, addr, 20) != ESP_OK) {
            return ESP_FAIL;
        }
    }
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = addr,
        .scl_speed_hz = 100000,
    };
    i2c_master_dev_handle_t dev = NULL;
    esp_err_t err = i2c_master_bus_add_device(s_bus, &dev_cfg, &dev);
    if (err != ESP_OK) {
        return err;
    }
    if (rx == NULL) {
        err = i2c_master_transmit(dev, tx, tx_len, 50);
    } else if (tx == NULL) {
        err = i2c_master_receive(dev, rx, rx_len, 50);
    } else {
        err = i2c_master_transmit_receive(dev, tx, tx_len, rx, rx_len, 50);
    }
    i2c_master_bus_rm_device(dev);
    if (err != ESP_OK) {
        recover_once();
        return err;
    }
    return ESP_OK;
}

esp_err_t i2c_bus_write(uint8_t addr, const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    return transact(addr, data, len, NULL, 0);
}

esp_err_t i2c_bus_read(uint8_t addr, uint8_t *data, size_t len)
{
    if (data == NULL || len == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    return transact(addr, NULL, 0, data, len);
}

esp_err_t i2c_bus_write_read(uint8_t addr, const uint8_t *reg, size_t reg_len,
                             uint8_t *data, size_t len)
{
    if (reg == NULL || data == NULL || reg_len == 0 || len == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    return transact(addr, reg, reg_len, data, len);
}

bool i2c_bus_probe(uint8_t addr)
{
    if (s_bus == NULL && i2c_bus_init() != ESP_OK) {
        return false;
    }
    return i2c_master_probe(s_bus, addr, 20) == ESP_OK;
}
