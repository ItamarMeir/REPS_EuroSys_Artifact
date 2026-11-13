// ===== ADDED (dps) =====================================================
// Distribution Packet Spraying (DPS): pure distribution helpers, no htsim dependency, so
// experiments/tools/dps_dist_test.cpp can link them standalone.
//
// A distribution is a probability mass function over the EV index e = 0..N-1. Under SRv6 the
// route of an EV is _paths[e % P]. The sender draws one EV per packet from it (UecSrc::nextEntropy_dps).
#ifndef DPS_DIST_H
#define DPS_DIST_H

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <functional>
#include <random>
#include <stdexcept>
#include <string>
#include <vector>

namespace dps {

// Number of numeric arguments each distribution name takes on the command line (-1 = unknown name).
// "list" and "file" take one command-line argument that main_uec.cpp expands into the weights.
inline int arg_count(const std::string& name) {
    if (name == "uniform" || name == "capacity") return 0;
    if (name == "list" || name == "file" || name == "poisson" || name == "geometric" || name == "zipf") return 1;
    if (name == "normal" || name == "binomial") return 2;
    return -1;
}

// Raw (unnormalised, non-negative) weights over e = 0..N-1.
// args: list/file -> the N weights; normal mu sigma; poisson lambda; binomial n p; geometric p; zipf s.
// capacity_fn(e) is only called for "capacity" (weight of EV e, any positive unit).
inline std::vector<double> raw_weights(const std::string& name, const std::vector<double>& args, size_t N,
                                       const std::function<double(size_t)>& capacity_fn) {
    if (N == 0) throw std::invalid_argument("dps: EV space is empty");
    int ac = arg_count(name);
    if (ac < 0) throw std::invalid_argument("dps: unknown distribution '" + name + "'");
    if (name != "list" && name != "file" && (int)args.size() != ac)
        throw std::invalid_argument("dps: distribution '" + name + "' takes " + std::to_string(ac) + " argument(s)");
    std::vector<double> w(N, 0.0);
    if (name == "uniform") {
        std::fill(w.begin(), w.end(), 1.0);
    } else if (name == "list" || name == "file") {
        if (args.size() != N)
            throw std::invalid_argument("dps: '" + name + "' needs exactly " + std::to_string(N) + " weights (the EV space size), got " + std::to_string(args.size()));
        w = args;
    } else if (name == "capacity") {
        if (!capacity_fn) throw std::invalid_argument("dps: capacity needs the routes of the source (use -use_srv6)");
        for (size_t e = 0; e < N; e++) w[e] = capacity_fn(e);
    } else if (name == "normal") {
        double mu = args[0], sigma = args[1];
        if (!(sigma > 0)) throw std::invalid_argument("dps: normal needs sigma > 0");
        // mass of the unit bin [e-0.5, e+0.5] under N(mu, sigma), truncated to the EV range by the renormalisation
        auto cdf = [&](double x) { return 0.5 * std::erfc(-(x - mu) / (sigma * std::sqrt(2.0))); };
        for (size_t e = 0; e < N; e++) w[e] = cdf(e + 0.5) - cdf(e - 0.5);
    } else if (name == "poisson") {
        double lam = args[0];
        if (!(lam > 0)) throw std::invalid_argument("dps: poisson needs lambda > 0");
        for (size_t e = 0; e < N; e++) w[e] = std::exp(-lam + e * std::log(lam) - std::lgamma(e + 1.0));
    } else if (name == "binomial") {
        double n = args[0], p = args[1];
        if (!(n >= 1) || n != std::floor(n) || !(p >= 0 && p <= 1))
            throw std::invalid_argument("dps: binomial needs integer n >= 1 and 0 <= p <= 1");
        for (size_t e = 0; e < N; e++) {
            if (e > n) { w[e] = 0; continue; }
            if (p == 0) { w[e] = (e == 0); continue; }
            if (p == 1) { w[e] = (e == n); continue; }
            w[e] = std::exp(std::lgamma(n + 1) - std::lgamma(e + 1.0) - std::lgamma(n - e + 1) + e * std::log(p) + (n - e) * std::log1p(-p));
        }
    } else if (name == "geometric") {
        double p = args[0];
        if (!(p > 0 && p <= 1)) throw std::invalid_argument("dps: geometric needs 0 < p <= 1");
        for (size_t e = 0; e < N; e++) w[e] = p * std::pow(1.0 - p, (double)e);
    } else if (name == "zipf") {
        double s = args[0];
        if (!(s >= 0)) throw std::invalid_argument("dps: zipf needs s >= 0");
        for (size_t e = 0; e < N; e++) w[e] = std::pow(e + 1.0, -s);
    }
    double sum = 0;
    for (double x : w) {
        if (!(x >= 0) || !std::isfinite(x)) throw std::invalid_argument("dps: weights must be finite and non-negative");
        sum += x;
    }
    if (!(sum > 0)) throw std::invalid_argument("dps: weights sum to zero");
    return w;
}

// True when all raw weights are exactly equal: DPS then takes the OPS draw (rand() % N), byte-identical to
// -load_balancing_algo oblivious.
inline bool is_uniform(const std::vector<double>& w) {
    return std::all_of(w.begin(), w.end(), [&](double x) { return x == w[0]; });
}

// Fixed relabelling of the EVs: pmf'[perm[e]] = pmf[e]. perm is a pure function of (N, seed); it does not
// use the libc rand() stream, so enabling it does not shift any other random draw.
inline std::vector<double> permute(const std::vector<double>& p, uint64_t seed) {
    std::vector<size_t> perm(p.size());
    for (size_t i = 0; i < perm.size(); i++) perm[i] = i;
    std::mt19937_64 g(seed);
    for (size_t i = perm.size(); i > 1; i--) std::swap(perm[i - 1], perm[g() % i]);
    std::vector<double> out(p.size());
    for (size_t e = 0; e < p.size(); e++) out[perm[e]] = p[e];
    return out;
}

inline std::vector<double> normalise(const std::vector<double>& w) {
    double s = 0;
    for (double x : w) s += x;
    std::vector<double> p(w.size());
    for (size_t e = 0; e < w.size(); e++) p[e] = w[e] / s;
    return p;
}

// Cumulative distribution for sampling. sample(u), u in [0,1): the first EV whose cdf exceeds u, so
// zero-mass EVs are never returned.
struct Cdf {
    std::vector<double> cdf;
    void build(const std::vector<double>& p) {
        cdf.assign(p.size(), 0.0);
        double s = 0;
        for (size_t e = 0; e < p.size(); e++) { s += p[e]; cdf[e] = s; }
        // Rounding must not leave the last mass below 1.0: the last EV with positive mass owns the tail.
        size_t last = 0;
        for (size_t e = 0; e < p.size(); e++) if (p[e] > 0) last = e;
        for (size_t e = last; e < p.size(); e++) cdf[e] = 2.0;
    }
    uint16_t sample(double u) const {
        return (uint16_t)(std::upper_bound(cdf.begin(), cdf.end(), u) - cdf.begin());
    }
};

}  // namespace dps
#endif
// ===== END ADDED (dps) =================================================
