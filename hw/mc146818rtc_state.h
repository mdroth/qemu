#ifndef MC146818RTC_STATE_H
#define MC146818RTC_STATE_H

#include "isa.h"

typedef struct RTCState {
    ISADevice dev;
    MemoryRegion io;
    uint8_t cmos_data[128];
    uint8_t cmos_index;
    struct tm current_tm;
    int32_t base_year;
    qemu_irq irq;
    qemu_irq sqw_irq;
    int it_shift;
    /* periodic timer */
    QEMUTimer *periodic_timer;
    int64_t next_periodic_time;
    /* second update */
    int64_t next_second_time;
    uint16_t irq_reinject_on_ack_count;
    uint32_t irq_coalesced;
    uint32_t period;
    QEMUTimer *coalesced_timer;
    QEMUTimer *second_timer;
    QEMUTimer *second_timer2;
    Notifier clock_reset_notifier;
    LostTickPolicy lost_tick_policy;
    Notifier suspend_notifier;
} RTCState;

#endif /* !MC146818RTC_STATE_H */
