idf_component_register(
    SRCS "app_main.c"
    INCLUDE_DIRS "."
    REQUIRES board config vehicle sensors bike_console link nvs_flash esp_timer esp_system
)
