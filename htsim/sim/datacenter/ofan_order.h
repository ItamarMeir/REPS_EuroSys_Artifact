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

}  // namespace ofan

#endif
