// ===== ADDED (reps-bank) =====
// BankBuffer: the "bank" of REPS-Bank. A small ring of EVs that came back clean
// (no ECN) with RTT below target. Header-only, no simulator dependencies, so it
// can be unit-tested standalone (experiments/tools/bank_buffer_test.cpp).
//
// Semantics (mirrors CircularBufferREPS where the spec says "like REPS"):
//   add(ev, now): write at `head`, advance head. When the ring is full this
//                 overwrites the slot at head, i.e. the OLDEST slot (valid or not).
//                 No rejection. Same overwrite policy as CircularBufferREPS::add.
//   pop_oldest(): scan from `head` (physically the oldest position) forward.
//                 Invalid slots are skipped. A valid slot whose age
//                 (now - insert_time) is strictly greater than `timer` is expired:
//                 invalidated and skipped. The first valid, unexpired slot is
//                 returned and invalidated (single use).
// Expiry is lazy (checked at pop time) -- observationally identical to an eager
// per-slot timer because a slot is only ever read through pop_oldest().
#pragma once
#include <cstdint>
#include <utility>
#include <vector>

class BankBuffer {
public:
    explicit BankBuffer(int capacity)
        : _slots(capacity > 0 ? capacity : 0), _cap(capacity > 0 ? capacity : 0) {}

    // `lost` (optional): receives {ev, insert_time} of a still-valid slot that this
    // add overwrote (for the -log_reps_bank trace). Returns true iff one was lost.
    bool add(uint16_t ev, uint64_t now, std::pair<uint16_t, uint64_t>* lost = nullptr) {
        if (_cap == 0) return false;
        bool over = _slots[_head].valid;
        if (over) {
            n_overwritten++;                        // valid slot lost to wrap-around
            if (lost) *lost = {_slots[_head].ev, _slots[_head].t};
        }
        _slots[_head].ev = ev;
        _slots[_head].t = now;
        _slots[_head].valid = true;
        _head = (_head + 1) % _cap;
        n_added++;
        return over;
    }

    // Returns true and sets `ev` if a valid, unexpired slot exists.
    // `expired_out` (optional): receives {ev, insert_time} of every slot this call
    // expired (for the -log_reps_bank trace).
    bool pop_oldest(uint16_t& ev, uint64_t now, uint64_t timer,
                    std::vector<std::pair<uint16_t, uint64_t>>* expired_out = nullptr) {
        for (int k = 0; k < _cap; ++k) {
            Slot& s = _slots[(_head + k) % _cap];
            if (!s.valid) continue;
            if (now - s.t > timer) {          // expired (age strictly > timer)
                s.valid = false;
                n_expired++;
                if (expired_out) expired_out->push_back({s.ev, s.t});
                continue;
            }
            ev = s.ev;
            s.valid = false;
            n_popped++;
            last_pop_age = now - s.t;
            return true;
        }
        return false;
    }

    // Read-only: number of valid, unexpired slots at `now`.
    int count_live(uint64_t now, uint64_t timer) const {
        int n = 0;
        for (int k = 0; k < _cap; ++k)
            if (_slots[k].valid && now - _slots[k].t <= timer) n++;
        return n;
    }

    // Valid slots regardless of age (for the conservation identity
    // inserted == popped + expired + overwritten + valid_at_end).
    int count_valid() const {
        int n = 0;
        for (const auto& s : _slots) if (s.valid) n++;
        return n;
    }

    int capacity() const { return _cap; }
    void reset() {
        for (auto& s : _slots) s.valid = false;
        _head = 0;
    }

    // Counters (cumulative, never reset by reset()).
    uint64_t n_added = 0;        // add() calls
    uint64_t n_overwritten = 0;  // add() that replaced a still-valid slot
    uint64_t n_expired = 0;      // slots invalidated by timer at pop time
    uint64_t n_popped = 0;       // successful pops
    uint64_t last_pop_age = 0;   // age of the most recent popped slot (ps)

private:
    struct Slot { uint16_t ev = 0; uint64_t t = 0; bool valid = false; };
    std::vector<Slot> _slots;
    int _cap;
    int _head = 0;
};
// ===== END ADDED (reps-bank) =====
