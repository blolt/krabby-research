#pragma once

#include <stdint.h>

// Host memory is uniform, so program-space data is ordinary const data.
#define PROGMEM
#define pgm_read_byte(address) (*(const uint8_t *)(address))
