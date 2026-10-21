// -*- c-basic-offset: 4; indent-tabs-mode: nil -*-
// ===== ADDED (ofan-order) =====
// Ofan port-order math (arXiv 2610.07230, App. F.2). Header-only and
// simulator-independent: no htsim types, no rand()/random().
//
// A switch keeps one round-robin pointer ptr in [0,w-1] per key
// (destination d, packet type t in {0=data,1=ACK}) over its w uplinks.
// The key is id = d + Nd*t. The pointer indexes a *slot*; the slot is mapped
// to a physical port by a per-id permutation pi:
//     b   = ceil(log2 w)            (b = 0 for w = 1)
//     id1 = id mod 2^b,  id2 = floor(id / 2^b)
//     pi(i) = ( xor_w(P[i], id1) + id2 ) mod w
//     xor_w(v,x) = (v^x) if (v^x) < w else v
// P is a global permutation of {0..w-1}, shared by all switches and derived
// deterministically from a seed (local mt19937_64 + Fisher-Yates).
// xor_w is an involution on [0,w) (hence a bijection) even for non power of
// two w, and adding id2 mod w is a bijection, so pi is always a bijection.
#ifndef OFAN_ORDER_H
#define OFAN_ORDER_H

#include <cstdint>
#include <map>
#include <random>
#include <utility>
#include <vector>

namespace ofan {

const uint64_t DEFAULT_SEED = 0x0fa17ULL;

// b = ceil(log2 w); 0 for w <= 1.
inline int ceil_log2(int w) {
    int b = 0;
    while ((1LL << b) < w) b++;
    return b;
}

// Shared permutation P of {0..w-1}; memoised per (seed, w).
// Not thread-safe (htsim is single-threaded).
inline const std::vector<int>& shared_perm(int w, uint64_t seed = DEFAULT_SEED) {
    static std::map<std::pair<uint64_t, int>, std::vector<int> > cache;
    std::pair<uint64_t, int> key(seed, w);
    std::map<std::pair<uint64_t, int>, std::vector<int> >::iterator it = cache.find(key);
    if (it != cache.end()) return it->second;
    std::vector<int> p(w);
    for (int i = 0; i < w; i++) p[i] = i;
    // seed mixed with w so different w get unrelated shuffles
    std::mt19937_64 rng(seed * 0x9E3779B97F4A7C15ULL + (uint64_t)w);
    for (int i = w - 1; i > 0; i--) {  // Fisher-Yates
        int j = (int)(rng() % (uint64_t)(i + 1));
        std::swap(p[i], p[j]);
    }
    return cache.insert(std::make_pair(key, p)).first->second;
}

inline int xor_w(int v, int x, int w) {
    int r = v ^ x;
    return r < w ? r : v;
}

// Port for pointer slot i under key id. identity=true gives pi(i)=i (ablation).
inline int pi(int i, uint32_t id, int w, uint64_t seed = DEFAULT_SEED, bool identity = false) {
    if (identity || w <= 1) return identity ? i : 0;
    int b = ceil_log2(w);
    int id1 = (int)(id & ((1u << b) - 1u));
    uint64_t id2 = (uint64_t)id >> b;
    int base = xor_w(shared_perm(w, seed)[i], id1, w);
    return (int)(((uint64_t)base + id2) % (uint64_t)w);
}

// Plain step: output pi(ptr), then ptr = (ptr+1) mod w.
inline int step(int& ptr, uint32_t id, int w, uint64_t seed = DEFAULT_SEED, bool identity = false) {
    int port = pi(ptr, id, w, seed, identity);
    ptr = (ptr + 1) % w;
    return port;
}

// Step skipping invalid (failed) ports. Finds the first slot s in
// ptr, ptr+1, ... (at most w steps) whose port is valid, returns pi(s) and
// commits ptr = (s+1) mod w. If no port is valid, behaves like step().
inline int pick(int& ptr, uint32_t id, int w, const std::vector<bool>& valid,
                uint64_t seed = DEFAULT_SEED, bool identity = false) {
    for (int k = 0; k < w; k++) {
        int s = (ptr + k) % w;
        int port = pi(s, id, w, seed, identity);
        if (valid[port]) {
            ptr = (s + 1) % w;
            return port;
        }
    }
    return step(ptr, id, w, seed, identity);
}

// Initial pointers. Data (t=0): caller supplies a random value in [0,w-1].
// ACK (t=1): half a round away from the data pointer.
inline int init_ptr_data(int rnd, int w) { return rnd % w; }
inline int init_ptr_ack(int data_init, int w) { return (data_init + w / 2) % w; }

// ===== ADDED (ofan-weighted) =====
// Weighted variant (extension, not in the paper): port i has integer weight wt[i] >= 0 (0 = invalid, e.g. the
// number of valid paths through that port). The schedule is an interleaved weighted round robin over the SAME
// permuted port order pi: sub-round r (r = 0..maxw-1) visits, in pi order, every port with wn[port] > r, where
// wn = wt / gcd(positive weights). One full schedule has L = sum(wn) slots and gives port i exactly wn[i] slots.
// With all weights equal and positive the schedule is exactly the plain Ofan order (L = w).
// Header-only helpers; the plain functions above are untouched.
inline int gcd_int(int a, int b) { while (b) { int t = a % b; a = b; b = t; } return a; }

// Normalises wt in place by the gcd of its positive entries; returns L = sum (0 if no positive weight).
inline int normalize_weights(std::vector<int>& wt) {
    int g = 0, L = 0;
    for (size_t i = 0; i < wt.size(); i++) if (wt[i] > 0) g = gcd_int(g, wt[i]);
    if (g == 0) return 0;
    for (size_t i = 0; i < wt.size(); i++) { wt[i] = wt[i] > 0 ? wt[i] / g : 0; L += wt[i]; }
    return L;
}

// Physical port of schedule slot s in [0, L) for normalised weights wn (size w).
inline int weighted_port(int s, uint32_t id, int w, const std::vector<int>& wn,
                         uint64_t seed = DEFAULT_SEED, bool identity = false) {
    int maxw = 0;
    for (int i = 0; i < w; i++) if (wn[i] > maxw) maxw = wn[i];
    for (int r = 0; r < maxw; r++) {
        int cnt = 0;
        for (int i = 0; i < w; i++) if (wn[pi(i, id, w, seed, identity)] > r) cnt++;
        if (s >= cnt) { s -= cnt; continue; }
        for (int i = 0; i < w; i++) {
            int port = pi(i, id, w, seed, identity);
            if (wn[port] > r) { if (s == 0) return port; s--; }
        }
    }
    return pi(0, id, w, seed, identity);  // unreachable for 0 <= s < L
}

// Weighted step: output the port of slot ptr, then ptr = (ptr+1) mod L.
inline int weighted_step(int& ptr, uint32_t id, int w, const std::vector<int>& wn, int L,
                         uint64_t seed = DEFAULT_SEED, bool identity = false) {
    int port = weighted_port(ptr, id, w, wn, seed, identity);
    ptr = (ptr + 1) % L;
    return port;
}
// ===== END ADDED (ofan-weighted) =====

}  // namespace ofan

#endif
