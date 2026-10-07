CC ?= gcc
CFLAGS := -std=c11 -Wall -Wextra -Werror -O2 -I../components/vehicle/include -I../components/config/include
LDFLAGS := -lm

.PHONY: all clean test

all: bike_host

bike_host: main.c session.c ../components/vehicle/bike_ctrl.c
	$(CC) $(CFLAGS) -o $@ main.c session.c ../components/vehicle/bike_ctrl.c $(LDFLAGS)

clean:
	rm -f bike_host
