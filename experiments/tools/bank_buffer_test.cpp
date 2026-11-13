// Unit test for BankBuffer (REPS-Bank). Standalone, no simulator deps.
// Build + run (inside the Docker container, from repo root):
//   g++ -std=c++17 -O1 -g -fsanitize=address,undefined -I htsim/sim \
//       experiments/tools/bank_buffer_test.cpp -o /tmp/bank_buffer_test && /tmp/bank_buffer_test
// Exit 0 = all checks pass AND all negative controls (deliberately broken
// buffers) are detected by the same harness.
#include "bank_buffer.h"
#include <cstdio>
#include <cstdlib>
#include <array>
#include <deque>
#include <random>
#include <string>

static int g_fail = 0;
#define CHECK(c, ...) do { if (!(c)) { g_fail++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

// ---- Reference model: a deque of slots in physical age order (front = oldest
// position = where the ring's head points). Independent of the ring-index code.
struct RefSlot { uint16_t ev; uint64_t t; bool valid; };
struct RefModel {
    size_t cap;
    std::deque<RefSlot> d;
    explicit RefModel(size_t c) : cap(c) {}
    void add(uint16_t ev, uint64_t now) {
        if (cap == 0) return;
        if (d.size() == cap) d.pop_front();          // overwrite oldest position (valid or not)
        d.push_back({ev, now, true});
    }
    bool pop(uint16_t& ev, uint64_t now, uint64_t timer) {
        for (auto& s : d) {
            if (!s.valid) continue;
            if (now - s.t > timer) { s.valid = false; continue; }
            ev = s.ev; s.valid = false; return true;
        }
        return false;
    }
    int live(uint64_t now, uint64_t timer) const {
        int n = 0; for (auto& s : d) if (s.valid && now - s.t <= timer) n++; return n;
    }
};

// ---- Deliberately broken buffers (negative controls). Same interface as BankBuffer.
template <int MUT>
struct Broken {
    struct Slot { uint16_t ev = 0; uint64_t t = 0; bool valid = false; };
    std::vector<Slot> s; int cap, head = 0;
    explicit Broken(int c) : s(c), cap(c) {}
    void add(uint16_t ev, uint64_t now) {
        if (MUT == 4) { // bug: reject when full instead of overwriting
            if (s[head].valid) return;
        }
        s[head] = {ev, now, true}; head = (head + 1) % cap;
    }
    bool pop_oldest(uint16_t& ev, uint64_t now, uint64_t timer) {
        for (int k = 0; k < cap; k++) {
            Slot& x = s[(head + k) % cap];
            if (!x.valid) continue;
            bool expired = (MUT == 1) ? (now - x.t >= timer)   // bug: off-by-one at boundary
                                      : (now - x.t > timer);
            if (MUT == 5) expired = false;                     // bug: timer ignored
            if (expired) { x.valid = false; continue; }
            ev = x.ev;
            if (MUT != 2) x.valid = false;                     // bug 2: not single-use
            return true;
        }
        return false;
    }
    int count_live(uint64_t, uint64_t) const { return 0; }
};
// MUT 3: returns NEWEST instead of oldest
struct BrokenNewest : Broken<0> {
    using Broken<0>::Broken;
    bool pop_oldest(uint16_t& ev, uint64_t now, uint64_t timer) {
        for (int k = cap - 1; k >= 0; k--) {
            Slot& x = s[(head + k) % cap];
            if (!x.valid) continue;
            if (now - x.t > timer) { x.valid = false; continue; }
            ev = x.ev; x.valid = false; return true;
        }
        return false;
    }
};

// Randomized differential run against the reference model. Returns #mismatches.
template <class B>
static long diff_run(int cap, long ops, uint64_t timer, unsigned seed, int pop_pct, int max_dt) {
    std::mt19937 rng(seed);
    B b(cap); RefModel m(cap);
    uint64_t now = 1000; long bad = 0;
    for (long i = 0; i < ops; i++) {
        now += rng() % (max_dt + 1);
        if ((int)(rng() % 100) < pop_pct) {
            uint16_t e1 = 0xFFFF, e2 = 0xFFFE;
            bool r1 = b.pop_oldest(e1, now, timer), r2 = m.pop(e2, now, timer);
            if (r1 != r2 || (r1 && e1 != e2)) bad++;
        } else {
            uint16_t ev = rng() % 65536;
            b.add(ev, now); m.add(ev, now);
        }
    }
    return bad;
}

int main() {
    // ---------- directed tests ----------
    { // empty pop fails; cap 0 inert
        BankBuffer b(4); uint16_t e;
        CHECK(!b.pop_oldest(e, 0, 10), "empty pop must fail");
        BankBuffer z(0); z.add(5, 1);
        CHECK(!z.pop_oldest(e, 1, 10), "cap0 never serves");
        CHECK(z.n_added == 0, "cap0 add is a no-op");
    }
    { // FIFO order + single use
        BankBuffer b(4); uint16_t e;
        for (uint16_t v = 1; v <= 3; v++) b.add(v, 100 + v);
        for (uint16_t v = 1; v <= 3; v++) { CHECK(b.pop_oldest(e, 110, 1000) && e == v, "FIFO order v=%d got %d", v, e); }
        CHECK(!b.pop_oldest(e, 110, 1000), "single use: all consumed");
        CHECK(b.n_popped == 3, "popped counter");
    }
    { // overwrite-when-full replaces the OLDEST; counters
        BankBuffer b(3); uint16_t e;
        for (uint16_t v = 1; v <= 5; v++) b.add(v, 10 * v);   // 4 and 5 overwrite 1 and 2
        CHECK(b.n_added == 5 && b.n_overwritten == 2, "overwritten=%llu", (unsigned long long)b.n_overwritten);
        CHECK(b.pop_oldest(e, 50, 1000) && e == 3, "oldest after wrap is 3, got %d", e);
        CHECK(b.pop_oldest(e, 50, 1000) && e == 4, "then 4");
        CHECK(b.pop_oldest(e, 50, 1000) && e == 5, "then 5");
        CHECK(!b.pop_oldest(e, 50, 1000), "then empty");
    }
    { // expiry boundary: age == timer valid, age == timer+1 expired
        BankBuffer b(2); uint16_t e;
        b.add(7, 100);
        CHECK(b.pop_oldest(e, 100 + 50, 50) && e == 7, "age==timer is valid");
        b.add(8, 200);
        CHECK(!b.pop_oldest(e, 200 + 51, 50), "age==timer+1 is expired");
        CHECK(b.n_expired == 1, "expired counter");
    }
    { // expired slot skipped, next live one served
        BankBuffer b(4); uint16_t e;
        b.add(1, 0); b.add(2, 90); b.add(3, 95);
        CHECK(b.pop_oldest(e, 100, 20) && e == 2, "slot 1 expired (age 100>20), serve 2, got %d", e);
        CHECK(b.n_expired == 1, "one expiry");
        CHECK(b.count_live(100, 20) == 1, "one live left");
    }
    { // size 1
        BankBuffer b(1); uint16_t e;
        b.add(1, 0); b.add(2, 1);
        CHECK(b.n_overwritten == 1, "size1 overwrite");
        CHECK(b.pop_oldest(e, 1, 10) && e == 2, "size1 serves latest");
        CHECK(!b.pop_oldest(e, 1, 10), "size1 empty after");
    }
    { // reset
        BankBuffer b(3); uint16_t e; b.add(1, 0); b.add(2, 0); b.reset();
        CHECK(!b.pop_oldest(e, 0, 10), "reset empties");
        b.add(9, 5); CHECK(b.pop_oldest(e, 5, 10) && e == 9, "usable after reset");
    }
    { // per-connection sharing: two successive "flows" use ONE bank (what startFlow does when it borrows the map's bank).
      // Slots and timestamps persist; per-flow counter deltas obey inserted + valid_at_start == popped + expired + overwritten + valid_at_end.
        BankBuffer b(3); uint16_t e;
        // flow 1: 4 adds into a ring of 3 (one overwrite), 1 pop
        auto s0 = std::array<uint64_t,4>{b.n_added, b.n_overwritten, b.n_expired, b.n_popped}; int v0 = b.count_valid();
        for (uint16_t v = 1; v <= 4; v++) b.add(v, 10 * v);                  // 1 is overwritten; live: 2,3,4
        CHECK(b.pop_oldest(e, 45, 1000) && e == 2, "flow1 pops oldest live (2), got %d", e);
        int v1 = b.count_valid();                                            // 2 live (3,4) inherited by flow 2
        CHECK(v1 == 2, "inherited live slots %d", v1);
        CHECK((b.n_added - s0[0]) + v0 == (b.n_popped - s0[3]) + (b.n_expired - s0[2]) + (b.n_overwritten - s0[1]) + v1, "flow1 conservation");
        // flow 2 starts later on the same bank: snapshot, then slot 3 (age 70-30=40 <= 50) is served, slot 4 too (age 30)
        auto t0 = std::array<uint64_t,4>{b.n_added, b.n_overwritten, b.n_expired, b.n_popped}; int w0 = b.count_valid();
        CHECK(w0 == 2, "valid_at_start of flow 2 is %d", w0);
        CHECK(b.pop_oldest(e, 70, 50) && e == 3, "inherited slot served by next flow, got %d", e);
        b.add(9, 80);
        CHECK(b.pop_oldest(e, 200, 50) == false, "all remaining slots (4 @40, 9 @80) expired by the later pop");   // ages 160, 120 > 50
        int w1 = b.count_valid();
        CHECK(w1 == 0, "no live slots left %d", w1);
        CHECK((b.n_added - t0[0]) + w0 == (b.n_popped - t0[3]) + (b.n_expired - t0[2]) + (b.n_overwritten - t0[1]) + w1,
              "flow2 conservation: added %llu popped %llu expired %llu", (unsigned long long)(b.n_added - t0[0]),
              (unsigned long long)(b.n_popped - t0[3]), (unsigned long long)(b.n_expired - t0[2]));
    }
    { // timer = 0: same-instant serves, any later instant expires
        BankBuffer b(2); uint16_t e;
        b.add(4, 500);
        CHECK(b.pop_oldest(e, 500, 0) && e == 4, "timer0 same instant ok");
        b.add(5, 500);
        CHECK(!b.pop_oldest(e, 501, 0), "timer0 one ps later expired");
    }
    { // invariant: pop returns min insert_time among live slots; pop age <= timer
        BankBuffer b(8); uint16_t e;
        for (int i = 0; i < 8; i++) b.add(i, 1000 + 7 * i);
        CHECK(b.pop_oldest(e, 1040, 100) && e == 0 && b.last_pop_age == 40, "age tracked");
    }

    // ---------- randomized differential (1e6 ops each) ----------
    struct Cfg { int cap; uint64_t timer; int pop_pct; int max_dt; };
    Cfg cfgs[] = {{1,50,50,20},{2,50,50,20},{3,0,50,3},{8,100,50,20},{8,100,20,20},{8,100,80,20},
                  {8,1,50,5},{8,1000000,50,20},{16,200,50,50},{64,500,50,10},{5,25,90,2},{5,25,10,2}};
    long total_bad = 0, total_ops = 0;
    for (auto& c : cfgs)
        for (unsigned seed = 1; seed <= 3; seed++) {
            total_bad += diff_run<BankBuffer>(c.cap, 1000000 / 3 + 1, c.timer, seed, c.pop_pct, c.max_dt);
            total_ops += 1000000 / 3 + 1;
        }
    printf("differential: %ld ops, %ld mismatches\n", total_ops, total_bad);
    CHECK(total_bad == 0, "differential mismatches=%ld", total_bad);

    // ---------- negative controls: each broken buffer MUST be caught ----------
    auto neg = [&](const char* name, long bad) {
        printf("negative control %-34s mismatches=%ld %s\n", name, bad, bad > 0 ? "(caught)" : "(NOT CAUGHT)");
        CHECK(bad > 0, "negative control '%s' not detected: harness cannot fail", name);
    };
    neg("expiry off-by-one (>= timer)",   diff_run<Broken<1>>(8, 300000, 100, 1, 50, 20));
    neg("pop not single-use",             diff_run<Broken<2>>(8, 300000, 100, 1, 50, 20));
    neg("pop newest instead of oldest",   diff_run<BrokenNewest>(8, 300000, 100, 1, 50, 20));
    neg("reject-when-full (no overwrite)",diff_run<Broken<4>>(8, 300000, 100, 1, 50, 20));
    neg("timer ignored",                  diff_run<Broken<5>>(8, 300000, 100, 1, 50, 20));

    printf(g_fail ? "RESULT: FAIL (%d)\n" : "RESULT: PASS\n", g_fail);
    return g_fail ? 1 : 0;
}
