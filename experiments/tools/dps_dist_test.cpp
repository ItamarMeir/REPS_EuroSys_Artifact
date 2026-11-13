// Standalone known-answer test of htsim/sim/dps_dist.h (DPS distributions). No simulator needed.
// Build + run (in the Docker container, repo root):
//   g++ -O2 -std=c++17 experiments/tools/dps_dist_test.cpp -o /tmp/dps_dist_test && /tmp/dps_dist_test
// Expected answers are derived from the definitions (closed-form means, variances, ratios) and written
// next to each check. A check that cannot fail proves nothing, so the NEG checks must report a failure.
#include "../../htsim/sim/dps_dist.h"
#include <cstdio>
#include <cstdlib>

static int g_fail = 0, g_pass = 0;
static void check(bool ok, const char* what) {
    printf("%s  %s\n", ok ? "PASS" : "FAIL", what);
    ok ? g_pass++ : g_fail++;
}
static bool close(double a, double b, double tol) { return std::fabs(a - b) <= tol; }

static std::vector<double> pmf(const std::string& n, std::vector<double> a, size_t N) {
    return dps::normalise(dps::raw_weights(n, a, N, nullptr));
}
static double mean(const std::vector<double>& p) { double m = 0; for (size_t e = 0; e < p.size(); e++) m += e * p[e]; return m; }
static double var(const std::vector<double>& p) { double m = mean(p), v = 0; for (size_t e = 0; e < p.size(); e++) v += (e - m) * (e - m) * p[e]; return v; }
static bool throws(const std::string& n, std::vector<double> a, size_t N) {
    try { dps::raw_weights(n, a, N, nullptr); } catch (const std::invalid_argument&) { return true; }
    return false;
}

// Chi-square of `draws` samples (libc rand() stream like the simulator) against the pmf `test`, while the sampler is built from `src`.
// Bins with expected < 5 are merged into one tail bin. Returns chi2 and sets df.
static double chi2(const std::vector<double>& src, const std::vector<double>& test, size_t draws, double& df, size_t& zero_hits) {
    dps::Cdf c; c.build(src);
    std::vector<uint64_t> cnt(src.size(), 0);
    srand(12345);
    for (size_t i = 0; i < draws; i++) cnt[c.sample(rand() / (RAND_MAX + 1.0))]++;
    zero_hits = 0;
    for (size_t e = 0; e < src.size(); e++) if (src[e] == 0) zero_hits += cnt[e];
    double chi = 0, tail_o = 0, tail_e = 0; int bins = 0;
    for (size_t e = 0; e < src.size(); e++) {
        double ex = test[e] * draws;
        if (ex < 5) { tail_o += cnt[e]; tail_e += ex; continue; }
        chi += (cnt[e] - ex) * (cnt[e] - ex) / ex; bins++;
    }
    if (tail_e >= 5) { chi += (tail_o - tail_e) * (tail_o - tail_e) / tail_e; bins++; }
    df = bins - 1;
    return chi;
}
static bool chi_ok(double chi, double df) { return chi < df + 6 * std::sqrt(2 * df) + 10; }  // far-tail bound, p << 1e-4

int main() {
    const size_t N = 16, D = 2000000;
    // --- pmf identities ---
    auto u = pmf("uniform", {}, N);
    check(close(u[0], 1.0 / N, 1e-15) && close(u[N - 1], 1.0 / N, 1e-15), "uniform: p = 1/N");
    check(dps::is_uniform(dps::raw_weights("uniform", {}, N, nullptr)), "uniform: is_uniform true");
    check(dps::is_uniform(dps::raw_weights("list", std::vector<double>(N, 1), N, nullptr)), "list 1,1,..,1: is_uniform true (OPS path)");
    check(dps::is_uniform(dps::raw_weights("list", std::vector<double>(N, 7), N, nullptr)), "list 7,7,..,7: is_uniform true (OPS path)");
    { std::vector<double> w(N, 1); w[3] = 2; check(!dps::is_uniform(dps::raw_weights("list", w, N, nullptr)), "NEG list 1,1,1,2,..: is_uniform false"); }
    check(close(pmf("poisson", {5}, 64)[3], std::exp(-5.0) * 125.0 / 6.0, 1e-12), "poisson(5): p[3] = e^-5 5^3/3!");
    { auto p = pmf("poisson", {5}, 64); check(close(mean(p), 5, 1e-6) && close(var(p), 5, 1e-5), "poisson(5): mean = var = 5"); }
    { auto p = pmf("binomial", {10, 0.3}, 16); check(close(mean(p), 3.0, 1e-9) && close(var(p), 2.1, 1e-9), "binomial(10,0.3): mean 3, var 2.1"); check(p[11] == 0 && p[15] == 0, "binomial(10,.3): zero mass above n"); }
    { auto p = pmf("geometric", {0.5}, 64); check(close(mean(p), 1.0, 1e-9) && close(p[2] / p[1], 0.5, 1e-12), "geometric(0.5): mean (1-p)/p = 1, ratio 1-p"); }
    { auto p = pmf("zipf", {1.5}, N); check(close(p[1] / p[0], std::pow(2.0, -1.5), 1e-12) && close(p[7] / p[3], std::pow(2.0, -1.5), 1e-12), "zipf(1.5): p[1]/p[0] = 2^-1.5, p[7]/p[3] = 2^-1.5"); }
    { auto p = pmf("normal", {8, 2}, 33); check(close(mean(p), 8, 1e-3) && close(var(p), 4 + 1.0 / 12, 5e-3), "normal(8,2): mean 8, var 4 + 1/12 (unit-bin variance; tolerance covers the truncation of 1e-5 mass below EV 0)"); }
    { std::vector<double> w = {1, 2, 3, 4}; auto p = pmf("list", w, 4); check(close(p[0], 0.1, 1e-15) && close(p[3], 0.4, 1e-15), "list 1,2,3,4: p = .1 .2 .3 .4"); }
    { auto w = dps::raw_weights("capacity", {}, 4, [](size_t e) { return e % 2 == 0 ? 20.0 : 380.0; });
      auto p = dps::normalise(w); check(close(p[0] + p[2], 0.05, 1e-15), "capacity 20/380: mass on slow EVs 0.05 (8x20 / (8x20 + 8x380) scaled: 2x20/(2x20+2x380))"); }
    // --- permutation ---
    { auto p = pmf("zipf", {1.0}, N); auto q = dps::permute(p, 7); auto s1 = p, s2 = q; std::sort(s1.begin(), s1.end()); std::sort(s2.begin(), s2.end());
      check(s1 == s2 && q != p, "permute: same multiset of masses, different positions");
      check(dps::permute(p, 7) == q, "permute: deterministic for a seed");
      check(dps::permute(p, 8) != q, "permute: different seed, different relabelling"); }
    // --- startup errors ---
    check(throws("nosuch", {}, N), "error: unknown name");
    check(throws("list", {1, 2, 3}, N), "error: list length != N");
    check(throws("list", std::vector<double>(N, 0), N), "error: zero-sum weights");
    { std::vector<double> w(N, 1); w[2] = -1; check(throws("list", w, N), "error: negative weight"); }
    { std::vector<double> w(N, 1); w[2] = NAN; check(throws("list", w, N), "error: NaN weight"); }
    check(throws("normal", {5, 0}, N), "error: normal sigma 0");
    check(throws("poisson", {}, N), "error: poisson without lambda");
    check(throws("binomial", {10.5, 0.3}, N), "error: binomial non-integer n");
    check(throws("capacity", {}, N), "error: capacity without routes");
    // --- sampling chi-square (libc rand() stream, 2e6 draws) ---
    struct Case { const char* n; std::vector<double> a; size_t N; };
    std::vector<Case> cases = {{"uniform", {}, 16}, {"zipf", {1.2}, 16}, {"poisson", {4}, 16}, {"binomial", {10, 0.3}, 16},
                               {"geometric", {0.3}, 16}, {"normal", {5, 2}, 16}, {"list", {5, 1, 0, 9, 3, 3, 3, 3, 0, 1, 1, 1, 1, 1, 1, 20}, 16}};
    for (auto& c : cases) {
        auto p = pmf(c.n, c.a, c.N); double df; size_t z;
        double chi = chi2(p, p, D, df, z);
        char buf[160]; snprintf(buf, sizeof buf, "sampler %s: chi2 %.1f, df %.0f, draws on zero-mass EVs %zu", c.n, chi, df, z);
        check(chi_ok(chi, df) && z == 0, buf);
    }
    // --- negative controls: the chi-square must be able to fail ---
    { auto a = pmf("zipf", {1.2}, 16), b = pmf("zipf", {1.3}, 16); double df; size_t z; double chi = chi2(a, b, D, df, z);
      char buf[160]; snprintf(buf, sizeof buf, "NEG sampler zipf(1.2) vs pmf zipf(1.3): chi2 %.1f must exceed bound", chi); check(!chi_ok(chi, df), buf); }
    { auto a = pmf("uniform", {}, 16); auto b = a; b[0] *= 1.02; b[1] *= 0.98; double df; size_t z; double chi = chi2(a, b, D, df, z);
      char buf[160]; snprintf(buf, sizeof buf, "NEG sampler uniform vs 2%% shifted pmf: chi2 %.1f must exceed bound", chi); check(!chi_ok(chi, df), buf); }
    // Sampler never returns an index >= N even at u -> 1
    { dps::Cdf c; c.build(pmf("zipf", {1.0}, N)); check(c.sample(0.0) < N && c.sample(std::nextafter(1.0, 0.0)) < N, "sampler: u = 0 and u = 1-eps stay in range"); }
    printf("\n%d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
