// Standalone test for htsim/sim/datacenter/ofan_order.h
// g++ -std=c++17 -O2 -I htsim/sim/datacenter test_ofan_order.cpp -o test_ofan_order
#include "ofan_order.h"
#include <cstdio>
#include <cstdlib>
#include <set>
#include <random>

static int fails = 0;
#define CHECK(name, cond) do { bool ok_ = (cond); printf("%s: %s\n", ok_ ? "PASS" : "FAIL", name); if (!ok_) fails++; } while (0)

static const uint64_t SEEDS[] = {ofan::DEFAULT_SEED, 1, 42, 0xdeadbeefULL};

int main() {
    // (a) pi is a bijection for w in 1..128, id in [0,4096), several seeds.
    bool a = true;
    for (uint64_t seed : SEEDS)
        for (int w = 1; w <= 128 && a; w++)
            for (uint32_t id = 0; id < 4096 && a; id++) {
                std::vector<char> seen(w, 0);
                for (int i = 0; i < w; i++) {
                    int p = ofan::pi(i, id, w, seed);
                    if (p < 0 || p >= w || seen[p]) { a = false; printf("  bad w=%d id=%u seed=%llu\n", w, id, (unsigned long long)seed); break; }
                    seen[p] = 1;
                }
            }
    CHECK("(a) pi is a bijection, w=1..128, id<4096, 4 seeds", a);

    // (b) from any start pointer, any w consecutive packets visit every port once.
    bool b = true;
    for (int w : {1, 2, 3, 6, 8, 12, 16, 24, 32, 33, 64, 100, 128})
        for (uint32_t id : {0u, 1u, 7u, 100u, 4095u})
            for (int start = 0; start < w && b; start++) {
                int ptr = start; std::vector<int> cnt(w, 0);
                for (int k = 0; k < w; k++) cnt[ofan::step(ptr, id, w)]++;
                for (int c : cnt) if (c != 1) b = false;
                if (ptr != start) b = false;
            }
    CHECK("(b) any w packets from any start hit each port exactly once", b);

    // (c) ACK init offset == floor(w/2) mod w.
    bool c = true;
    for (int w = 1; w <= 128; w++)
        for (int d = 0; d < w; d++)
            if (ofan::init_ptr_ack(d, w) != (d + w / 2) % w) c = false;
    CHECK("(c) ACK init = (data_init + floor(w/2)) mod w", c);

    // (d) Validity mask. PROPERTY (provable): for a FIXED mask, the commit-past-
    // found-slot scheme visits the valid *slots* in increasing cyclic slot order,
    // each once per pass, because pi is a bijection (valid ports <-> valid slots).
    // Hence the output is an exact round-robin over the V valid ports: every
    // window of V consecutive picks, starting at any pick, hits each valid port
    // exactly once, and after N picks counts differ by <= 1 (equal if V | N).
    // This holds for any (shuffled) mask. It is NOT guaranteed when the mask
    // CHANGES mid-run (reported below, not gated).
    std::mt19937_64 rng(7);
    bool d = true;
    for (int w : {2, 3, 6, 8, 12, 16, 24, 32, 64})
        for (int trial = 0; trial < 200 && d; trial++) {
            std::vector<bool> valid(w); int V = 0;
            for (int i = 0; i < w; i++) { valid[i] = rng() & 1; V += valid[i]; }
            if (V == 0) { valid[rng() % w] = true; V = 1; }
            uint32_t id = rng() % 4096; int ptr = rng() % w;
            int N = 1000 * w + (int)(rng() % V);
            std::vector<int> seq(N), cnt(w, 0);
            for (int k = 0; k < N; k++) { seq[k] = ofan::pick(ptr, id, w, valid); cnt[seq[k]]++; if (!valid[seq[k]]) d = false; }
            for (int k = 0; k + V <= N && d; k++) {   // every V-window is a permutation of valid ports
                std::set<int> s(seq.begin() + k, seq.begin() + k + V);
                if ((int)s.size() != V) d = false;
            }
            int lo = 1 << 30, hi = 0;
            for (int p = 0; p < w; p++) if (valid[p]) { lo = std::min(lo, cnt[p]); hi = std::max(hi, cnt[p]); }
            if (hi - lo > 1) d = false;
            if (!d) printf("  mask fail w=%d V=%d id=%u\n", w, V, id);
        }
    CHECK("(d) fixed mask: exact RR over valid ports (every V-window unique, counts differ <=1)", d);

    // (d2) no valid port: returns pi(ptr) and advances by 1.
    {
        std::vector<bool> none(6, false); int ptr = 3;
        int p = ofan::pick(ptr, 5, 6, none);
        CHECK("(d2) no valid port -> pi(ptr), ptr+1", p == ofan::pi(3, 5, 6) && ptr == 4);
    }

    // (e) non-power-of-two sanity: w=6,12,24,32, per-pass balance over many ids.
    bool e = true;
    for (int w : {6, 12, 24, 32}) {
        std::vector<long> cnt(w, 0);
        for (uint32_t id = 0; id < 4096; id++) { int ptr = id % w; for (int k = 0; k < w; k++) cnt[ofan::step(ptr, id, w)]++; }
        for (long x : cnt) if (x != 4096) e = false;
    }
    CHECK("(e) w=6,12,24,32: each port used equally over all ids", e);

    // REPORT only: mask change mid-run (w=8, one port toggles) -- is exact RR kept?
    {
        int w = 8, viol = 0, total = 0;
        for (int t = 0; t < 200; t++) {
            std::vector<bool> v(w, true); int ptr = rng() % w; uint32_t id = rng() % 64;
            std::vector<int> cnt(w, 0);
            for (int k = 0; k < 8; k++) ofan::pick(ptr, id, w, v);
            v[rng() % w] = false;  // fail one port
            for (int k = 0; k < 7; k++) cnt[ofan::pick(ptr, id, w, v)]++;
            total++; for (int x : cnt) if (x > 1) { viol++; break; }
        }
        printf("REPORT: after a port fails mid-run, 7 picks hit some port twice in %d/%d trials (expected 0)\n", viol, total);
    }

    // REPORT only: number of distinct cyclic orders over ids (rotation-canonical).
    for (int w : {6, 8, 16}) {
        for (int ident = 0; ident < 2; ident++) {
            std::set<std::vector<int> > orders;
            for (uint32_t id = 0; id < 4096; id++) {
                std::vector<int> o(w);
                for (int i = 0; i < w; i++) o[i] = ofan::pi(i, id, w, ofan::DEFAULT_SEED, ident);
                int z = 0; while (o[z] != 0) z++;
                std::vector<int> c(w);
                for (int i = 0; i < w; i++) c[i] = o[(z + i) % w];
                orders.insert(c);
            }
            printf("REPORT: w=%d %s P: %zu distinct cyclic orders (ids<4096)\n", w, ident ? "identity" : "shuffled", orders.size());
        }
    }

    // REPORT only: formula with P = identity permutation (paper's "30 orders" for w=6).
    for (int w : {6, 8, 16}) {
        std::set<std::vector<int> > orders; int b = ofan::ceil_log2(w);
        for (uint32_t id = 0; id < 4096; id++) {
            std::vector<int> o(w);
            for (int i = 0; i < w; i++) o[i] = (int)(((uint64_t)ofan::xor_w(i, (int)(id & ((1u << b) - 1)), w) + (id >> b)) % w);
            int z = 0; while (o[z] != 0) z++;
            std::vector<int> c(w); for (int i = 0; i < w; i++) c[i] = o[(z + i) % w];
            orders.insert(c);
        }
        printf("REPORT: w=%d formula with P=identity: %zu distinct cyclic orders\n", w, orders.size());
    }

    printf(fails ? "OVERALL: FAIL (%d)\n" : "OVERALL: PASS\n", fails);
    return fails ? 1 : 0;
}
