idf_component_register(
    SRCS "ble_status.c"
    INCLUDE_DIRS "include"
    REQUIRES vehicle bt nvs_flash
)
