#include "ble_status.h"

#include "bike_ctrl.h"
#include "bike_port.h"

#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "host/util/util.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <string.h>

static const ble_uuid128_t UUID_SVC = BLE_UUID128_INIT(
    0xfb, 0x34, 0x9b, 0x5f, 0x80, 0x00, 0x00, 0x80,
    0x00, 0x10, 0x00, 0x40, 0x00, 0x00, 0x69, 0x6b);
static const ble_uuid128_t UUID_SNAP = BLE_UUID128_INIT(
    0xfb, 0x34, 0x9b, 0x5f, 0x80, 0x00, 0x00, 0x80,
    0x00, 0x10, 0x00, 0x40, 0x01, 0x00, 0x69, 0x6b);
static const ble_uuid128_t UUID_CMD = BLE_UUID128_INIT(
    0xfb, 0x34, 0x9b, 0x5f, 0x80, 0x00, 0x00, 0x80,
    0x00, 0x10, 0x00, 0x40, 0x02, 0x00, 0x69, 0x6b);

static uint16_t s_conn = BLE_HS_CONN_HANDLE_NONE;
static uint16_t s_snap_handle;
static uint8_t s_own_addr;

static int gap_event(struct ble_gap_event *event, void *arg);

static void advertise(void)
{
    struct ble_hs_adv_fields fields;
    memset(&fields, 0, sizeof fields);
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.name = (uint8_t *)"smartbike";
    fields.name_len = 9;
    fields.name_is_complete = 1;
    ble_gap_adv_set_fields(&fields);

    struct ble_gap_adv_params adv;
    memset(&adv, 0, sizeof adv);
    adv.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv.disc_mode = BLE_GAP_DISC_MODE_GEN;
    ble_gap_adv_start(s_own_addr, NULL, BLE_HS_FOREVER, &adv, gap_event, NULL);
}

static int gap_event(struct ble_gap_event *event, void *arg)
{
    (void)arg;
    switch (event->type) {
    case BLE_GAP_EVENT_CONNECT:
        if (event->connect.status == 0) {
            s_conn = event->connect.conn_handle;
        } else {
            advertise();
        }
        return 0;
    case BLE_GAP_EVENT_DISCONNECT:
        s_conn = BLE_HS_CONN_HANDLE_NONE;
        advertise();
        return 0;
    case BLE_GAP_EVENT_ADV_COMPLETE:
        advertise();
        return 0;
    default:
        return 0;
    }
}

static int access_cb(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    (void)conn;
    (void)attr;
    (void)arg;
    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        uint8_t raw[32];
        bike_port_lock();
        bike_pack_snapshot(raw);
        bike_port_unlock();
        if (os_mbuf_append(ctxt->om, raw, sizeof raw) != 0) {
            return BLE_ATT_ERR_INSUFFICIENT_RES;
        }
        return 0;
    }
    if (ctxt->op == BLE_GATT_ACCESS_OP_WRITE_CHR) {
        uint8_t opcode = 0;
        uint16_t len = 0;
        if (ble_hs_mbuf_to_flat(ctxt->om, &opcode, 1, &len) != 0 || len != 1) {
            return BLE_ATT_ERR_INVALID_ATTR_VALUE_LEN;
        }
        bike_enqueue_opcode(opcode);
        return 0;
    }
    return BLE_ATT_ERR_UNLIKELY;
}

static struct ble_gatt_chr_def CHRS[] = {
    {
        .uuid = &UUID_SNAP.u,
        .access_cb = access_cb,
        .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
        .val_handle = &s_snap_handle,
    },
    {
        .uuid = &UUID_CMD.u,
        .access_cb = access_cb,
        .flags = BLE_GATT_CHR_F_WRITE,
    },
    {0},
};

static struct ble_gatt_svc_def SVCS[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &UUID_SVC.u,
        .characteristics = CHRS,
    },
    {0},
};

static void notify_task(void *arg)
{
    (void)arg;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(500));
        if (s_conn == BLE_HS_CONN_HANDLE_NONE) {
            continue;
        }
        uint8_t raw[32];
        bike_port_lock();
        bike_pack_snapshot(raw);
        bike_port_unlock();
        struct os_mbuf *om = ble_hs_mbuf_from_flat(raw, sizeof raw);
        if (om != NULL) {
            ble_gatts_notify_custom(s_conn, s_snap_handle, om);
        }
    }
}

static void sync_cb(void)
{
    ble_hs_id_infer_auto(0, &s_own_addr);
    ble_svc_gap_device_name_set("smartbike");
    advertise();
}

static void host_task(void *arg)
{
    (void)arg;
    nimble_port_run();
    nimble_port_freertos_deinit();
}

void ble_status_start(void)
{
    nimble_port_init();
    ble_hs_cfg.sync_cb = sync_cb;
    ble_svc_gap_init();
    ble_svc_gatt_init();
    ble_gatts_count_cfg(SVCS);
    ble_gatts_add_svcs(SVCS);
    xTaskCreate(notify_task, "ble_notify", 4096, NULL, 4, NULL);
    nimble_port_freertos_init(host_task);
}
