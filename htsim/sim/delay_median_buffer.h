// ===== ADDED (swift-cc / median-buffer) =====================================
// Circular buffer of simtime_picosec delay samples used by MSwift and MNSCC.
// Supports push(), median(), and percentile(p) operations.
//
// Design:
//  - Fixed MAX_H = 32 cap — bounds per-ACK sort to ~160 comparisons, negligible.
//  - setCapacity(H): only flushes the buffer when H decreases below the current
//    fill level, so the buffer stays valid during AI-phase cwnd growth.
//  - percentile(p): generalised form used for Fig-12 P10/P50/P90 variants.
//    median() = percentile(50).
// ===== END ADDED (swift-cc / median-buffer) ==================================

#pragma once
#include <algorithm>
#include <cstdint>
#include "eventlist.h"   // simtime_picosec

class DelayMedianBuffer {
public:
    static const int MAX_H = 32;   // hard cap on history window

    DelayMedianBuffer() : _head(0), _count(0), _capacity(1) {}

    // Update window size H. Only flushes when the new capacity is smaller than
    // the number of valid samples already stored (shrinking the window).
    void setCapacity(int H) {
        int newCap = H < 1 ? 1 : (H > MAX_H ? MAX_H : H);
        if (newCap < _count) {
            // Window shrank past stored samples — flush and start fresh.
            _count = 0;
            _head  = 0;
        }
        _capacity = newCap;
    }

    // Record one delay sample.
    void push(simtime_picosec delay) {
        _buf[_head % MAX_H] = delay;
        _head = (_head + 1) % MAX_H;
        if (_count < _capacity)
            _count++;
    }

    // Return the p-th percentile (0–100) of buffered samples.
    // percentile(50) == median.
    simtime_picosec percentile(int p) const {
        if (_count == 0) return 0;
        int n = _count;
        simtime_picosec tmp[MAX_H];
        // Copy the n most recent valid entries from the ring buffer.
        int start = (_head - n + MAX_H) % MAX_H;
        for (int i = 0; i < n; i++)
            tmp[i] = _buf[(start + i) % MAX_H];
        std::sort(tmp, tmp + n);
        int idx = (n * p) / 100;
        if (idx >= n) idx = n - 1;
        return tmp[idx];
    }

    simtime_picosec median() const { return percentile(50); }

    int size()     const { return _count;    }
    int capacity() const { return _capacity; }

private:
    simtime_picosec _buf[MAX_H];
    int _head;     // next write position (ring)
    int _count;    // valid samples stored (≤ _capacity)
    int _capacity; // current window size H
};
