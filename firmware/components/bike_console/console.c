#include "console.h"

#include "bike_ctrl.h"
#include "bike_port.h"

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>

typedef struct {
    char line[96];
} console_evt_t;

static QueueHandle_t s_events;

void console_emit(const char *line, void *ctx)
{
    (void)ctx;
    if (s_events == NULL || line == NULL) {
        return;
    }
    console_evt_t evt;
    snprintf(evt.line, sizeof evt.line, "%s", line);
    xQueueSend(s_events, &evt, 0);
}

static void print_reply(const bike_reply_t *reply)
{
    for (int i = 0; i < reply->count; i++) {
        printf("%s\n", reply->text[i]);
    }
    fflush(stdout);
}

static void handle_line(char *line)
{
    static bike_reply_t reply;
    bike_port_lock();
    bike_handle(line, &reply);
    bike_port_unlock();
    print_reply(&reply);
}

static void console_task(void *arg)
{
    (void)arg;
    int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
    if (flags >= 0) {
        fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK);
    }
    printf("ok boot\n");
    fflush(stdout);

    char line[81];
    int len = 0;
    bool overflow = false;
    int64_t watch_us = esp_timer_get_time();
    for (;;) {
        console_evt_t evt;
        while (xQueueReceive(s_events, &evt, 0) == pdTRUE) {
            printf("%s\n", evt.line);
            fflush(stdout);
        }
        int ch = getchar();
        if (ch == EOF) {
            uint32_t period = 0;
            bike_port_lock();
            period = bike_watch_period();
            bike_port_unlock();
            int64_t now = esp_timer_get_time();
            if (period > 0 && (uint32_t)((now - watch_us) / 1000) >= period) {
                watch_us = now;
                handle_line("status");
            }
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        if (ch == '\r') {
            continue;
        }
        if (ch != '\n') {
            if (len >= 80) {
                overflow = true;
            } else {
                line[len++] = (char)ch;
            }
            continue;
        }
        line[len] = '\0';
        if (overflow) {
            printf("err syntax\n");
            fflush(stdout);
        } else if (len > 0) {
            handle_line(line);
        }
        len = 0;
        overflow = false;
    }
}

void console_start(void)
{
    s_events = xQueueCreate(16, sizeof(console_evt_t));
    bike_set_emit(console_emit, NULL);
    xTaskCreate(console_task, "console", 4096, NULL, 4, NULL);
}
