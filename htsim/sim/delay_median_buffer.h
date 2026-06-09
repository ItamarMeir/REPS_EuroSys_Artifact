// ===== ADDED (swift-cc / median-buffer) =====================================
// Circular buffer of simtime_picosec delay samples used by MSwift and MNSCC.
// Supports push(), median(), and percentile(p) operations.
//
// Design:
//  - MAX_H = 128 (was 32). Paper 2 (arXiv:2509.07907v2) Eq (8) sets MSwift's
//    H = max(W/2, 1). At BDP cwnd ~120 pkts in the Fig 4 setup, paper H = 60;
//    earlier MAX_H = 32 silently clamped to half-paper-H and made the median
//    behave closer to raw delay. Sort cost is now ~640 cmp/ACK — negligible.
//  - setCapacity(H): on shrink, keeps the most-recent newCap samples (paper has
//    no flush rule). The earlier "flush on shrink" behaviour discarded all
//    history right after MD-induced cwnd drops, defeating the median framework
//    exactly when its smoothing was most useful.
//  - percentile(p): generalised form used for Fig-12 P10/P50/P90 variants.
//    median() = percentile(50).
// ===== END ADDED (swift-cc / median-buffer) ==================================

#pragma once
#include <algorithm>
#include <cstdint>
#include "eventlist.h"   // simtime_picosec

class DelayMedianBuffer {
public:
    static const int MAX_H = 128;  // hard cap on history window

    DelayMedianBuffer() : _head(0), _count(0), _capacity(1) {}

    // Update window size H.
    void setCapacity(int H) {
        int newCap = H < 1 ? 1 : (H > MAX_H ? MAX_H : H);
        // ===== FIX (median-buf-paper-faithful) ===============================
        // On shrink, keep the most-recent newCap samples (paper has no flush
        // rule). The ring already stores them at indices
        //   (_head - newCap) % MAX_H .. (_head - 1) % MAX_H
        // so simply truncating _count to newCap leaves _head correct.
        // =====================================================================
        if (newCap < _count) {
            _count = newCap;
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
