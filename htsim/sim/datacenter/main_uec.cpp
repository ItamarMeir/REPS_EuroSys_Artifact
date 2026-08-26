// -*- c-basic-offset: 4; indent-tabs-mode: nil -*-
//#include "config.h"
#include <sstream>
#include <string.h>

#include <math.h>
#include <unistd.h>
#include "circular_buffer.h"
#include "network.h"
#include "pipe.h"
#include "eventlist.h"
#include "logfile.h"
#include "uec_logger.h"
#include "clock.h"
#include "uec.h"
#include "compositequeue.h"
#include "../statefulecnqueue.h"
#include "topology.h"
#include "connection_matrix.h"
#include "pciemodel.h"
#include "oversubscribed_cc.h"
#include "data_collector.h"


#include "fat_tree_topology.h"
#include "fat_tree_switch.h"

#include <list>
#include <sys/types.h>
#include <sys/stat.h>

// Simulation params

//#define PRINTPATHS 1

#include "main.h"

int DEFAULT_NODES = 128;
#define DEFAULT_QUEUE_SIZE 35
// #define DEFAULT_CWND 50

EventList& eventlist = EventList::getTheEventList();

// State-Aware NSCC+REPS: dynamic link-failure event. Fires once at t_fail to
// mark the targeted Agg<->Core pipes failed (both directions). If t_recover >
// t_fail, reschedules itself to clear the failure at t_recover. Pure addition;
// existing failure mechanisms (FAILURE_GENERATOR) are untouched.
class LinkFailureEvent : public EventSource {
public:
    LinkFailureEvent(EventList& el, Pipe* up, Pipe* down,
                     simtime_picosec t_fail, simtime_picosec t_recover)
        : EventSource(el, "link_failure"),
          _up(up), _down(down),
          _t_fail(t_fail), _t_recover(t_recover), _state(0) {
        eventlist().sourceIsPending(*this, _t_fail);
    }
    void doNextEvent() override {
        if (_state == 0) {
            if (_up)   _up->setFailed(true);
            if (_down) _down->setFailed(true);
            cout << "[link_failure] failed pipe at " << timeAsUs(eventlist().now())
                 << " us" << endl;
            _state = 1;
            if (_t_recover > _t_fail) {
                eventlist().sourceIsPending(*this, _t_recover);
            }
        } else {
            if (_up)   _up->setFailed(false);
            if (_down) _down->setFailed(false);
            cout << "[link_failure] restored pipe at " << timeAsUs(eventlist().now())
                 << " us" << endl;
        }
    }
private:
    Pipe *_up, *_down;
    simtime_picosec _t_fail, _t_recover;
    int _state;
};

// ===== ADDED (path-random queue logging) =====
// Samples agg→core uplink queue depths every interval_us µs and writes
// time_us,agg,core,bytes rows to a CSV. Gated by -log_core_queues <file>.
class CoreQueueSampler : public EventSource {
public:
    CoreQueueSampler(EventList& el, FatTreeTopology* topo,
                     const std::string& outpath, double interval_us)
        : EventSource(el, "core_queue_sampler"),
          _topo(topo),
          _interval((simtime_picosec)(interval_us * 1e6)) {
        _f = fopen(outpath.c_str(), "w");
        if (_f) fprintf(_f, "time_us,agg,core,bytes\n");
        eventlist().sourceIsPending(*this, _interval);
    }
    ~CoreQueueSampler() { if (_f) fclose(_f); }
    void doNextEvent() override {
        if (!_f) return;
        double t = timeAsUs(eventlist().now());
        for (uint32_t agg = 0; agg < _topo->getNAGG(); agg++) {
            if (agg >= _topo->queues_nup_nc.size()) continue;
            for (uint32_t core = 0; core < _topo->no_of_cores(); core++) {
                if (core >= _topo->queues_nup_nc[agg].size()) continue;
                if (_topo->queues_nup_nc[agg][core].empty()) continue;
                BaseQueue* q = _topo->queues_nup_nc[agg][core][0];
                if (q) fprintf(_f, "%.3f,%u,%u,%ld\n", t, agg, core,
                               (long)q->queuesize());
            }
        }
        eventlist().sourceIsPending(*this, eventlist().now() + _interval);
    }
private:
    FatTreeTopology* _topo;
    simtime_picosec _interval;
    FILE* _f = nullptr;
};
// ===== END ADDED (path-random queue logging) =====

// ===== ADDED (tor-queue logging) =====
// Samples ToR→Agg uplink queue depths every interval_us µs and writes
// time_us,tor,agg,bytes rows to a CSV. Gated by -log_tor_queues <file>.
class TorQueueSampler : public EventSource {
public:
    TorQueueSampler(EventList& el, FatTreeTopology* topo,
                    const std::string& outpath, double interval_us)
        : EventSource(el, "tor_queue_sampler"),
          _topo(topo),
          _interval((simtime_picosec)(interval_us * 1e6)) {
        _f = fopen(outpath.c_str(), "w");
        if (_f) fprintf(_f, "time_us,tor,agg,bytes\n");
        eventlist().sourceIsPending(*this, _interval);
    }
    ~TorQueueSampler() { if (_f) fclose(_f); }
    void doNextEvent() override {
        if (!_f) return;
        double t = timeAsUs(eventlist().now());
        for (uint32_t tor = 0; tor < _topo->queues_nlp_nup.size(); tor++) {
            for (uint32_t agg = 0; agg < _topo->queues_nlp_nup[tor].size(); agg++) {
                if (_topo->queues_nlp_nup[tor][agg].empty()) continue;
                BaseQueue* q = _topo->queues_nlp_nup[tor][agg][0];
                if (q) fprintf(_f, "%.3f,%u,%u,%ld\n", t, tor, agg,
                               (long)q->queuesize());
            }
        }
        eventlist().sourceIsPending(*this, eventlist().now() + _interval);
    }
private:
    FatTreeTopology* _topo;
    simtime_picosec _interval;
    FILE* _f = nullptr;
};
// ===== END ADDED (tor-queue logging) =====

// ===== ADDED (core-downlink-queue-log) =====
// Samples core→agg DOWNlink queue depths (queues_nc_nup, opposite direction
// from CoreQueueSampler's agg→core uplink) for the first num_cores core
// switches only, every interval_us µs, writing time_us,core,agg,bytes rows
// to a CSV. Built for exp25 (experiments/exp25_queue_dynamics_v25/)
// to check whether REPS's first-window round-robin (see exp24) produces a
// synchronized queue spike at flow start that FREEZING does not. Gated by
// -log_core_downlink_queues <file>; num_cores/interval are experiment-specific
// constants, not exposed as separate flags (single current caller).
class CoreDownlinkQueueSampler : public EventSource {
public:
    CoreDownlinkQueueSampler(EventList& el, FatTreeTopology* topo,
                              const std::string& outpath, double interval_us,
                              uint32_t num_cores)
        : EventSource(el, "core_downlink_queue_sampler"),
          _topo(topo),
          _interval((simtime_picosec)(interval_us * 1e6)),
          _num_cores(num_cores) {
        _f = fopen(outpath.c_str(), "w");
        if (_f) fprintf(_f, "time_us,core,agg,bytes\n");
        eventlist().sourceIsPending(*this, _interval);
    }
    ~CoreDownlinkQueueSampler() { if (_f) fclose(_f); }
    void doNextEvent() override {
        if (!_f) return;
        double t = timeAsUs(eventlist().now());
        uint32_t ncore = min(_num_cores, _topo->no_of_cores());
        for (uint32_t core = 0; core < ncore; core++) {
            if (core >= _topo->queues_nc_nup.size()) continue;
            for (uint32_t agg = 0; agg < _topo->getNAGG(); agg++) {
                if (agg >= _topo->queues_nc_nup[core].size()) continue;
                if (_topo->queues_nc_nup[core][agg].empty()) continue;
                BaseQueue* q = _topo->queues_nc_nup[core][agg][0];
                if (q) fprintf(_f, "%.3f,%u,%u,%ld\n", t, core, agg,
                               (long)q->queuesize());
            }
        }
        eventlist().sourceIsPending(*this, eventlist().now() + _interval);
    }
private:
    FatTreeTopology* _topo;
    simtime_picosec _interval;
    uint32_t _num_cores;
    FILE* _f = nullptr;
};
// ===== END ADDED (core-downlink-queue-log) =====

void exit_error(char* progr) {
    cout << "Usage " << progr << " [-nodes N]\n\t[-conns C]\n\t[-cwnd cwnd_size]\n\t[-q queue_size]\n\t[-recv_oversub_cc] Use receiver-driven AIMD to reduce total window when trims are not last hop\n\t[-queue_type composite|random|lossless|lossless_input|]\n\t[-tm traffic_matrix_file]\n\t[-strat route_strategy (single,rand,perm,pull,ecmp,\n\tecmp_host path_count,ecmp_ar,ecmp_rr,\n\tecmp_host_ar ar_thresh)]\n\t[-log log_level]\n\t[-seed random_seed]\n\t[-end end_time_in_usec]\n\t[-mtu MTU]\n\t[-hop_latency x] per hop wire latency in us,default 1 \n\t[-disable_fd] disable fair decrease to get higher throught, \n\t[-target_q_delay x] target_queuing_delay in us, default is 6us \n\t[-switch_latency x] switching latency in us, default 0\n\t[-host_queue_type  swift|prio|fair_prio]\n\t[-logtime dt] sample time for sinklogger, etc" << endl;
    exit(1);
}

int main(int argc, char **argv) {
    Clock c(timeFromSec(5 / 100.), eventlist);
    bool param_queuesize_set = false;
    mem_b queuesize = DEFAULT_QUEUE_SIZE;
    linkspeed_bps linkspeed = speedFromMbps((double)HOST_NIC);
    int packet_size = 4150;
    uint32_t path_entropy_size = 64;
    uint32_t no_of_conns = 0, cwnd = 0, no_of_nodes = 0;
    uint32_t tiers = 3; // we support 2 and 3 tier fattrees
    uint32_t planes = 1;  // multi-plane topologies
    uint32_t ports = 1;  // ports per NIC
    bool disable_trim = false; // Disable trimming, drop instead
    uint16_t trimsize = 64; // size of a trimmed packet
    simtime_picosec logtime = timeFromMs(0.25); // ms;
    stringstream filename(ios_base::out);
    simtime_picosec hop_latency = timeFromUs((uint32_t)1);
    simtime_picosec switch_latency = timeFromUs((uint32_t)0);
    queue_type qt = COMPOSITE;
    std::string tiers_latency;

    UecSrc::_load_balancing_algo = UecSrc::MIXED;

    bool log_sink = false;
    bool log_nic = false;
    bool log_flow_events = true;

    bool log_tor_downqueue = false;
    bool log_tor_upqueue = false;
    bool log_traffic = false;
    bool log_switches = false;
    bool log_queue_usage = false;
    double ecn_thresh = 0.5; // default marking threshold for ECN load balancing
    std::string log_core_queues_file = "";   // ===== ADDED (path-random queue logging) =====
    std::string log_tor_queues_file  = "";   // ===== ADDED (tor-queue logging) =====
    std::string log_core_downlink_queues_file = "";  // ===== ADDED (core-downlink-queue-log) =====

    bool param_ecn_set = false;
    bool ecn = true;
    mem_b ecn_low = 0.2 * queuesize, ecn_high = 0.8 * queuesize;

    bool receiver_driven = true;
    bool force_disable_tor_ecn = false;

    RouteStrategy route_strategy = NOT_SET;
    
    int seed = 13;
    int path_burst = 1;
    int i = 1;
    double pcie_rate = 1.1;

    filename << "logout.dat";
    int end_time = 100000;//in microseconds
    bool force_disable_oversubscribed_cc = false;
    bool enable_accurate_base_rtt = true;

    //unsure how to set this. 
    queue_type snd_type = FAIR_PRIO;

    float ar_sticky_delta = 10;
    FatTreeSwitch::sticky_choices ar_sticky = FatTreeSwitch::PER_PACKET;

    char* tm_file = NULL;
    char* topo_file = NULL;
    //bool disable_fair_decrease = true;
    bool _collect_data = false;
    bool enable_qa_gate = true;
    double fast_increase_scaling_factor = UecSrc::get_fast_increase_scaling_factor();
    double prop_increase_scaling_factor = UecSrc::get_prop_increase_scaling_factor();
    double fair_increase_scaling_factor = UecSrc::get_fair_decrease_scaling_factor();
    double fair_decrease_scaling_factor = UecSrc::get_fair_decrease_scaling_factor();
    double mult_decrease_scaling_factor = UecSrc::get_mult_decrease_scaling_factor();
    bool use_exp_avg_ecn = UecSrc::get_use_exp_avg_ecn();
    bool input_fail_on = false;

    // State-Aware NSCC+REPS testbed knobs. All default to "off / first link" so
    // omitting the flags leaves the simulation behavior unchanged. Units are
    // microseconds, matching the rest of the htsim CLI (e.g., -end).
    double fail_link_fail_us = 0.0;       // <= 0 means do not schedule a failure
    double fail_link_recover_us = 0.0;    // <= fail_link_fail_us means no recovery
    int    fail_link_bundle = 0;
    // Multi-link failure: each entry is one (agg_id, core_id) pair. If empty
    // when -fail_link_time is set, defaults to a single (0,0) link.
    vector<pair<int,int>> fail_link_targets;

    string data_collection_dir = "";
    htsim::DataCollector& data_collector = htsim::DataCollector::get_instance();

    // ===== ADDED (min-rto-flag) =====
    // -1 = not requested; otherwise overrides auto-computed RTO floor (us).
    // Re-applied after the auto-compute at main_uec.cpp:~L1018.
    int min_rto_us_override = -1;
    // ===== END ADDED =====

    // ===== ADDED (path-rr-npaths): per-host PATH_RR path-count cap =====
    std::map<uint32_t, uint32_t> path_rr_npaths_override;
    // ===== END ADDED (path-rr-npaths) =====

    while (i<argc) {
        if (!strcmp(argv[i], "-data_collection_config")) {
            data_collector.InitWithConfig(argv[i+1]);
            cout << "Data collector initialized with config file " << argv[i+1] << endl;
            i++;
        } else if (!strcmp(argv[i], "-data_collection_dir")) {
            data_collection_dir = argv[i+1];
            i++;
        } else if (!strcmp(argv[i],"-o")) {
            filename.str(std::string());
            filename << argv[i+1];
            i++;
        } else if (!strcmp(argv[i],"-conns")) {
            no_of_conns = atoi(argv[i+1]);
            cout << "no_of_conns "<<no_of_conns << endl;
            i++;
        } else if (!strcmp(argv[i],"-end")) {
            end_time = atoi(argv[i+1]);
            cout << "endtime(us) "<< end_time << endl;
            i++;            
        } else if (!strcmp(argv[i],"-nodes")) {
            no_of_nodes = atoi(argv[i+1]);
            cout << "no_of_nodes "<<no_of_nodes << endl;
            i++;
        } else if (!strcmp(argv[i],"-tiers")) {
            tiers = atoi(argv[i+1]);
            cout << "tiers " << tiers << endl;
            assert(tiers == 2 || tiers == 3);
            i++;
        } else if (!strcmp(argv[i],"-num_disabled")) {
            FatTreeSwitch::_num_disable_per_switch = atoi(argv[i+1]);
            i++;
        } else if (!strcmp(argv[i],"-planes")) {
            planes = atoi(argv[i+1]);
            ports = planes;
            cout << "planes " << planes << endl;
            cout << "ports per NIC " << ports << endl;
            assert(planes >= 1 && planes <= 8);
            i++;
        } else if (!strcmp(argv[i], "-fasti_scaling_factor")) {
            fast_increase_scaling_factor = std::stod(argv[i + 1]);
            UecSrc::set_fast_increase_scaling_factor(fast_increase_scaling_factor);
            printf("Fast increase: %f\n", fast_increase_scaling_factor);
            i++;
        } else if (!strcmp(argv[i], "-pi_scaling_factor")) {
            prop_increase_scaling_factor = std::stod(argv[i + 1]);
            UecSrc::set_prop_increase_scaling_factor(prop_increase_scaling_factor);
            printf("Prop increase: %f\n", prop_increase_scaling_factor);
            i++;
        } else if (!strcmp(argv[i], "-pi_scaling_factor")) {
            prop_increase_scaling_factor = std::stod(argv[i + 1]);
            UecSrc::set_prop_increase_scaling_factor(prop_increase_scaling_factor);
            printf("Prop increase: %f\n", prop_increase_scaling_factor);
            i++;
        } else if (!strcmp(argv[i], "-exit_freeze")) {
            CircularBufferREPS<int>::exit_freeze_after = std::stod(argv[i + 1]);
            i++;
        // ===== ADDED (freezing-pxr) =====
        } else if (!strcmp(argv[i], "-pxr_window_us")) {
            // Sliding-window timer (in microseconds) for FREEZING_PXR.
            UecSrc::_pxr_window = (simtime_picosec)atoll(argv[i + 1]) * 1000000ULL;
            printf("FREEZING_PXR sliding window set to %s us\n", argv[i + 1]);
            i++;
        // ===== END ADDED (freezing-pxr) =====
        } else if (!strcmp(argv[i], "-skip_asy")) {
            FatTreeTopology::skip_asy = true;
        } else if (!strcmp(argv[i],"-mixed_lb_traffic")) {
            UecSrc::_mixed_lb_traffic = true;
        } else if (!strcmp(argv[i],"-klb_k")) {
            UecSrc::_klb_k_param = atoi(argv[i+1]);
            printf("KLB/SKLB K=%d\n", UecSrc::_klb_k_param);
            i++;
        } else if (!strcmp(argv[i],"-klb_enable_fixes")) {
            UecSrc::_klb_enable_fixes = true;
            printf("KLB fixes enabled (EV cooldown + ECN hysteresis)\n");
        } else if (!strcmp(argv[i],"-max_incumbents")) {
            StatefulECNQueue::_max_incumbents_param = atoi(argv[i+1]);
            printf("StatefulECNQueue max_incumbents=%d\n", StatefulECNQueue::_max_incumbents_param);
            i++;
        } else if (!strcmp(argv[i],"-idle_timeout_us")) {
            StatefulECNQueue::_idle_timeout_ps_param = timeFromUs(atof(argv[i+1]));
            printf("StatefulECNQueue idle_timeout=%.1fus\n", atof(argv[i+1]));
            i++;
        } else if (!strcmp(argv[i],"-disable_tor_ecn")) {
            force_disable_tor_ecn = true;
        } else if (!strcmp(argv[i],"-mp_flows")) {
            UecSrc::_num_mp_flows = atoi(argv[i+1]);
            i++;
        } else if (!strcmp(argv[i],"-collect_data")) {
            UecSrc::_collect_data = true;
            CompositeQueue::_collect_data = true;
            _collect_data = true;
        } else if (!strcmp(argv[i],"-log_ecn_timeseries")) {
            CompositeQueue::_log_ecn_timeseries = true;
        } else if (!strcmp(argv[i],"-ecn_bin_us")) {
            CompositeQueue::_ecn_bin_ps = (simtime_picosec)atoll(argv[i+1]) * 1000000;
            i++;
        } else if (!strcmp(argv[i],"-save_rtt")) {
            UecSrc::_save_rtt = true;
        } else if (!strcmp(argv[i],"-other_location")) {
            FAILURE_GENERATOR->other_loc = true;
        } else if (!strcmp(argv[i],"-connections_mapping")) {
            UecSrc::_connections_mapping = true;
        } else if (!strcmp(argv[i],"-log_link")) {
            FatTreeSwitch::_log_link_utilization = true;
            Pipe::_log_link_utilization = true;
        } else if (!strcmp(argv[i],"-freezeoff")) {
            CircularBufferREPS<int>::repsUseFreezing = false;
        } else if (!strcmp(argv[i],"-switch_stats")) {
            FatTreeSwitch::_log_switch_stats = true;
        } else if (!strcmp(argv[i], "-fd_scaling_factor")) {
            fair_decrease_scaling_factor = std::stod(argv[i + 1]);
            UecSrc::set_fair_decrease_scaling_factor(fair_decrease_scaling_factor);
            printf("Fair decrease: %f\n", fair_decrease_scaling_factor);
            i++;
        } else if (!strcmp(argv[i], "-fd_scaling_factor")) {
            fair_decrease_scaling_factor = std::stod(argv[i + 1]);
            UecSrc::set_fair_decrease_scaling_factor(fair_decrease_scaling_factor);
            printf("Fair decrease: %f\n", fair_decrease_scaling_factor);
            i++;
        } else if (!strcmp(argv[i], "-down_ratio")) {
            FatTreeTopology::_failed_link_ratio = std::stod(argv[i + 1]);
            i++;
        // ===== ADDED (min-rto-flag) =====
        // Override the auto-computed RTO floor with an explicit value in microseconds.
        // Paper 1 (REPS, arXiv:2407.21625) sec 4.1 sets RTO = 70 us.
        // Must appear AFTER the -topo parsing so it survives the later auto-compute at
        // main_uec.cpp:~L1018. We track the override and re-apply post auto-compute.
        } else if (!strcmp(argv[i],"-min_rto")) {
            min_rto_us_override = atoi(argv[i+1]);
            cout << "min_rto override requested: " << min_rto_us_override << " us" << endl;
            i++;
        // ===== END ADDED =====
        // ===== ADDED (per-host-lb) =====
        // Override LB algorithm for specific source hosts. Format:
        //   -host_lb_overrides 0:ecmp,3:freezing,7:oblivious
        // Overridden hosts use the named algorithm; all others use the global
        // -load_balancing_algo. Used to reproduce paper Fig 4 mixed regime
        // (ECMP elephants + REPS or OPS sprayed) when -ecmp_elephant_threshold
        // isn't precise enough.
        } else if (!strcmp(argv[i],"-host_lb_overrides")) {
            if (!UecSrc::_parseHostLBString(argv[i+1])) {
                cerr << "Failed to parse -host_lb_overrides: " << argv[i+1] << endl;
                exit(1);
            }
            cout << "Per-host LB overrides set for " << UecSrc::_per_host_lb_override.size()
                 << " hosts" << endl;
            i++;
        // ===== END ADDED (per-host-lb) =====
        // ===== ADDED (path-rr-order) =====
        } else if (!strcmp(argv[i], "-path_rr_start_mode")) {
            const char* m = argv[i+1];
            if (!strcmp(m, "zero"))
                UecSrc::_path_rr_start_mode = UecSrc::PATH_RR_START_ZERO;
            else if (!strcmp(m, "src_mod"))
                UecSrc::_path_rr_start_mode = UecSrc::PATH_RR_START_SRC;
            else if (!strcmp(m, "dst_mod"))
                UecSrc::_path_rr_start_mode = UecSrc::PATH_RR_START_DST;
            else if (!strcmp(m, "srcdst_hash"))
                UecSrc::_path_rr_start_mode = UecSrc::PATH_RR_START_SRCDST_HASH;
            else if (!strcmp(m, "src_mod2")) // ===== ADDED (path-rr-startslot) =====
                UecSrc::_path_rr_start_mode = UecSrc::PATH_RR_START_SRC2;
            else { cerr << "Unknown -path_rr_start_mode: " << m << "\n"; exit(1); }
            cout << "PATH_RR start mode: " << m << "\n";
            i++;
        } else if (!strcmp(argv[i], "-path_rr_npaths_override")) { // ===== ADDED (path-rr-npaths) =====
            std::string spec(argv[++i]);
            std::istringstream ss(spec);
            std::string tok;
            while (std::getline(ss, tok, ',')) {
                auto colon = tok.find(':');
                if (colon != std::string::npos) {
                    uint32_t host = (uint32_t)std::stoul(tok.substr(0, colon));
                    uint32_t np   = (uint32_t)std::stoul(tok.substr(colon + 1));
                    path_rr_npaths_override[host] = np;
                    cout << "path_rr_npaths_override: host " << host << " -> max " << np << " paths\n";
                }
            }
        // ===== END ADDED (path-rr-npaths) =====
        // ===== END ADDED (path-rr-order) =====
        // ===== ADDED (srv6) =====
        } else if (!strcmp(argv[i], "-use_srv6")) {
            UecSrc::_use_srv6 = true;
            cout << "SRv6 source routing enabled: EV -> _paths[ev % N] (bypasses ECMP)" << endl;
        // ===== END ADDED (srv6) =====
        } else if (!strcmp(argv[i],"-sender_cc_only")) {
            UecSrc::_sender_based_cc = true;
            UecSrc::_receiver_based_cc = false;
            UecSink::_oversubscribed_cc = false;
            receiver_driven = false;
            cout << "sender based CC enabled ONLY" << endl;
//        } else if (!strcmp(argv[i],"-disable_fd")) {
//            disable_fair_decrease = true;
//            cout << "fair_decrease disabled" << endl;
        } else if (!strcmp(argv[i],"-enable_qa_gate")) {
            enable_qa_gate = true;
        } else if (!strcmp(argv[i],"-enable_fi")) {
            UecSrc::mprdma_fast_recovery = true;
        } else if (!strcmp(argv[i],"-enable_avg_ecn_over_path")) {
            UecSrc::_enable_avg_ecn_over_path = true;
            cout << "enable avg_ecn_over_path algorithm." << endl;            
        } else if (!strcmp(argv[i], "-no_timeouts")) {
            CompositeQueue::_use_timeouts = false;
            UecSrc::_use_timeouts = false;
            Pipe::_use_timeouts = false;
            failuregenerator::_use_timeouts = false;
        } else if (!strcmp(argv[i], "-failures_input")) {
            input_fail_on = true;
            FAILURE_GENERATOR->setInputFile(argv[i + 1]);
            i++;
        } else if (!strcmp(argv[i],"-target_q_delay")) {
            UecSrc::_target_Qdelay = timeFromUs(atof(argv[i+1]));
            cout << "target_q_delay" << atof(argv[i+1]) << " us"<< endl;
            i++;
        // ===== ADDED (swift-cc) CLI flags ===================================
        } else if (!strcmp(argv[i],"-swift_beta")) {
            UecSrc::_swift_beta = atof(argv[i+1]);
            cout << "swift_beta " << UecSrc::_swift_beta << endl;
            i++;
        } else if (!strcmp(argv[i],"-swift_max_mdf")) {
            UecSrc::_swift_max_mdf = atof(argv[i+1]);
            cout << "swift_max_mdf " << UecSrc::_swift_max_mdf << endl;
            i++;
        } else if (!strcmp(argv[i],"-swift_ai")) {
            UecSrc::_swift_ai = atof(argv[i+1]);
            cout << "swift_ai " << UecSrc::_swift_ai << endl;
            i++;
        } else if (!strcmp(argv[i],"-swift_median_pct")) {
            UecSrc::_swift_median_pct = atoi(argv[i+1]);
            cout << "swift_median_pct " << UecSrc::_swift_median_pct << endl;
            i++;
        } else if (!strcmp(argv[i],"-lswift_dup_threshold")) {
            UecSrc::_lswift_dup_threshold = (uint32_t)atoi(argv[i+1]);
            cout << "lswift_dup_threshold " << UecSrc::_lswift_dup_threshold << endl;
            i++;
        // ===== END ADDED (swift-cc) CLI flags ================================
        // ===== ADDED (ecmp-elephant) CLI flag ================================
        } else if (!strcmp(argv[i],"-ecmp_elephant_threshold")) {
            UecSrc::_ecmp_elephant_threshold = (uint64_t)atoll(argv[i+1]);
            cout << "ecmp_elephant_threshold " << UecSrc::_ecmp_elephant_threshold
                 << " bytes (flows >= this size use ECMP)" << endl;
            i++;
        // ===== END ADDED (ecmp-elephant) CLI flag ============================
        } else if (!strcmp(argv[i],"-sender_cc_algo")) {
            UecSrc::_sender_based_cc = true;
            
            if (!strcmp(argv[i+1],"dctcp")) 
                UecSrc::_sender_cc_algo = UecSrc::DCTCP;
            else if (!strcmp(argv[i+1],"nscc")) 
                UecSrc::_sender_cc_algo = UecSrc::NSCC;
            else if (!strcmp(argv[i+1],"mprdma")) 
                UecSrc::_sender_cc_algo = UecSrc::MPRDMA_CC;
            else if (!strcmp(argv[i+1],"constant")) 
                UecSrc::_sender_cc_algo = UecSrc::CONSTANT;
            else if (!strcmp(argv[i+1],"smartt"))
                UecSrc::_sender_cc_algo = UecSrc::SMARTT;
            else if (!strcmp(argv[i+1],"smartt_ecn_aimd"))
                UecSrc::_sender_cc_algo = UecSrc::SMARTT_ECN_AIMD;
            else if (!strcmp(argv[i+1],"smartt_ecn_aifd"))
                UecSrc::_sender_cc_algo = UecSrc::SMARTT_ECN_AIFD;
            else if (!strcmp(argv[i+1],"smartt_ecn_fimd"))
                UecSrc::_sender_cc_algo = UecSrc::SMARTT_ECN_FIMD;
            else if (!strcmp(argv[i+1],"smartt_ecn_fifd"))
                UecSrc::_sender_cc_algo = UecSrc::SMARTT_ECN_FIFD;
            else if (!strcmp(argv[i+1],"smartt_rtt"))
                UecSrc::_sender_cc_algo = UecSrc::SMARTT_RTT;
            // ===== ADDED (swift-cc) =========================================
            else if (!strcmp(argv[i+1],"swift"))
                UecSrc::_sender_cc_algo = UecSrc::SWIFT;
            else if (!strcmp(argv[i+1],"lswift"))
                UecSrc::_sender_cc_algo = UecSrc::LSWIFT;
            else if (!strcmp(argv[i+1],"mswift"))
                UecSrc::_sender_cc_algo = UecSrc::MSWIFT;
            else if (!strcmp(argv[i+1],"mnscc"))
                UecSrc::_sender_cc_algo = UecSrc::MNSCC;
            // ===== END ADDED (swift-cc) =====================================
            else {
                cout << "UNKNOWN CC ALGO " << argv[i+1] << endl;
                exit(1);
            }
            cout << "sender based algo "<< argv[i+1] << endl;
            i++;
        } else if (!strcmp(argv[i],"-save_data_folder")) {
            SAVE_DATA_FOLDER = argv[i + 1];
            i++;
        } else if (!strcmp(argv[i], "-use_wait_to_decrease")) {
            use_exp_avg_ecn = atoi(argv[i + 1]);
            printf("Use wait to decrease: %d\n", use_exp_avg_ecn);
            UecSrc::set_use_exp_avg_ecn(use_exp_avg_ecn);
            i++;
        } else if (!strcmp(argv[i],"-sender_cc")) {
            UecSrc::_sender_based_cc = true;
            UecSink::_oversubscribed_cc = false;
            cout << "sender based CC enabled " << endl;
        }
        else if (!strcmp(argv[i],"-load_balancing_algo")){
            if (!strcmp(argv[i+1], "bitmap")) {
                UecSrc::_load_balancing_algo = UecSrc::BITMAP;
            } 
            else if (!strcmp(argv[i+1], "reps")) {
                UecSrc::_load_balancing_algo = UecSrc::REPS;
            }
            else if (!strcmp(argv[i+1], "oblivious")) {
                UecSrc::_load_balancing_algo = UecSrc::OBLIVIOUS;
            }
            else if (!strcmp(argv[i+1], "mixed")) {
                UecSrc::_load_balancing_algo = UecSrc::MIXED;
            } else if (!strcmp(argv[i+1],"nvidia")){
                UecSrc::_load_balancing_algo = UecSrc::OBLIVIOUS;
                FatTreeSwitch::use_adaptive_roce = true;
            } else if (!strcmp(argv[i+1], "incremental")) {
                UecSrc::_load_balancing_algo = UecSrc::INCREMENTAL;
            } else if (!strcmp(argv[i+1], "plb")) {
                UecSrc::_load_balancing_algo = UecSrc::PLB;
            } else if (!strcmp(argv[i+1], "flowlet")) {
                UecSrc::_load_balancing_algo = UecSrc::FLOWLET;
            } else if (!strcmp(argv[i+1], "mprdma")) {
                UecSrc::_load_balancing_algo = UecSrc::MPRDMA;
            } else if (!strcmp(argv[i+1], "ecmp")) {
                UecSrc::_load_balancing_algo = UecSrc::ECMP;
            } else if (!strcmp(argv[i+1], "mp")) {
                UecSrc::_load_balancing_algo = UecSrc::MP;
            }else if (!strcmp(argv[i+1], "freezing")) {
                UecSrc::_load_balancing_algo = UecSrc::FREEZING;
            } else if (!strcmp(argv[i+1], "klb")) {
                UecSrc::_load_balancing_algo = UecSrc::KLB;
            } else if (!strcmp(argv[i+1], "sklb")) {
                UecSrc::_load_balancing_algo = UecSrc::SKLB;
            } else if (!strcmp(argv[i+1], "hklb")) {
                UecSrc::_load_balancing_algo = UecSrc::HKLB;
            // ===== ADDED (path-rr) =====
            // PATH_RR: true round-robin over distinct physical paths via source
            // routing.  Requires get_bidir_paths() path population per flow
            // (done below in the per-flow connectPort loop).
            } else if (!strcmp(argv[i+1], "path_rr")) {
                UecSrc::_load_balancing_algo = UecSrc::PATH_RR;
            // ===== END ADDED (path-rr) =====
            // ===== ADDED (path-random) =====
            // PATH_RANDOM: same source-routing as PATH_RR but picks a fresh
            // random path index on every packet instead of cycling.
            } else if (!strcmp(argv[i+1], "path_random")) {
                UecSrc::_load_balancing_algo = UecSrc::PATH_RANDOM;
            // ===== END ADDED (path-random) =====
            // ===== ADDED (path-static) =====
            // PATH_STATIC: collision-free precomputed single path per flow.
            } else if (!strcmp(argv[i+1], "path_static")) {
                UecSrc::_load_balancing_algo = UecSrc::PATH_STATIC;
            // ===== END ADDED (path-static) =====
            // ===== ADDED (freezing-pxr) =====
            // FREEZING_PXR: REPS-like LB with persistent excluded-EV set on RTO.
            } else if (!strcmp(argv[i+1], "freezing_pxr")) {
                UecSrc::_load_balancing_algo = UecSrc::FREEZING_PXR;
            // ===== END ADDED (freezing-pxr) =====
            } else {
                cout << "Unknown load balancing algorithm of type " << argv[i+1] << ", expecting bitmap, reps or reps2" << endl;
                exit_error(argv[0]);
            }
            cout << "Load balancing algorithm set to  "<< argv[i+1] << endl;
            i++;
        }
        else if (!strcmp(argv[i],"-queue_type")) {
            if (!strcmp(argv[i+1], "composite")) {
                qt = COMPOSITE;
            } 
            else if (!strcmp(argv[i+1], "composite_ecn")) {
                qt = COMPOSITE_ECN;
            }
            else if (!strcmp(argv[i+1], "aeolus")){
                qt = AEOLUS;
            }
            else if (!strcmp(argv[i+1], "aeolus_ecn")){
                qt = AEOLUS_ECN;
            }
            else if (!strcmp(argv[i+1], "stateful_ecn")) {
                qt = STATEFUL_ECN;
            }
            else {
                cout << "Unknown queue type " << argv[i+1] << endl;
                exit_error(argv[0]);
            }
            cout << "queue_type "<< qt << endl;
            i++;
        } else if (!strcmp(argv[i],"-debug")) {
            UecSrc::_debug = true;
        } else if (!strcmp(argv[i],"-host_queue_type")) {
            if (!strcmp(argv[i+1], "swift")) {
                snd_type = SWIFT_SCHEDULER;
            } 
            else if (!strcmp(argv[i+1], "prio")) {
                snd_type = PRIORITY;
            }
            else if (!strcmp(argv[i+1], "fair_prio")) {
                snd_type = FAIR_PRIO;
            }
            else {
                cout << "Unknown host queue type " << argv[i+1] << " expecting one of swift|prio|fair_prio" << endl;
                exit_error(argv[0]);
            }
            cout << "host queue_type "<< snd_type << endl;
            i++;
        } else if (!strcmp(argv[i],"-log")){
            if (!strcmp(argv[i+1], "flow_events")) {
                log_flow_events = true;
            } else if (!strcmp(argv[i+1], "sink")) {
                cout << "logging sinks\n";
                log_sink = true;
            } else if (!strcmp(argv[i+1], "nic")) {
                cout << "logging nics\n";
                log_nic = true;
            } else if (!strcmp(argv[i+1], "tor_downqueue")) {
                cout << "logging tor downqueues\n";
                log_tor_downqueue = true;
            } else if (!strcmp(argv[i+1], "tor_upqueue")) {
                cout << "logging tor upqueues\n";
                log_tor_upqueue = true;
            } else if (!strcmp(argv[i+1], "switch")) {
                cout << "logging total switch queues\n";
                log_switches = true;
            } else if (!strcmp(argv[i+1], "traffic")) {
                cout << "logging traffic\n";
                log_traffic = true;
            } else if (!strcmp(argv[i+1], "queue_usage")) {
                cout << "logging queue usage\n";
                log_queue_usage = true;
            } else {
                exit_error(argv[0]);
            }
            i++;
        } else if (!strcmp(argv[i],"-cwnd")) {
            cwnd = atoi(argv[i+1]);
            cout << "cwnd "<< cwnd << endl;
            i++;
        } else if (!strcmp(argv[i],"-tm")){
            tm_file = argv[i+1];
            cout << "traffic matrix input file: "<< tm_file << endl;
            i++;
        } else if (!strcmp(argv[i],"-topo")){
            topo_file = argv[i+1];
            cout << "FatTree topology input file: "<< topo_file << endl;
            i++;
        } else if (!strcmp(argv[i],"-q")){
            param_queuesize_set = true;
            queuesize = atoi(argv[i+1]);
            cout << "Setting queuesize to " << queuesize << " packets " << endl;
            i++;
        }
        else if (!strcmp(argv[i],"-sack_threshold")){
            UecSink::_bytes_unacked_threshold = atoi(argv[i+1]);
            cout << "Setting receiver SACK bytes threshold to " << UecSink::_bytes_unacked_threshold  << " bytes " << endl;
            i++;            
        }
        else if (!strcmp(argv[i],"-oversubscribed_cc")){
            UecSink::_oversubscribed_cc = true;
            cout << "Using receiver oversubscribed CC " << endl;
        }
        else if (!strcmp(argv[i],"-force_disable_oversubscribed_cc")){
            UecSink::_oversubscribed_cc = false;
            force_disable_oversubscribed_cc = true;
            cout << "Disabling receiver oversubscribed CC even with OS topology" << endl;
        }
        else if (!strcmp(argv[i],"-disable_accurate_base_rtt")){
            enable_accurate_base_rtt = false;
            cout << "Disabling accurate base rtt configuration, each flow takes network wide rtt as the base rtt upper bound." << endl;
        }
        else if (!strcmp(argv[i],"-fastlossrecovery")){
            UecSrc::_enable_fast_loss_recovery = true;
            cout << "Using sender fast loss recovery heuristic " << endl;
        }
        else if (!strcmp(argv[i],"-ecn")){
            // fraction of queuesize, between 0 and 1
            param_ecn_set = true;
            ecn = true;
            ecn_low = atoi(argv[i+1]); 
            ecn_high = atoi(argv[i+2]);
            i+=2;
        } else if (!strcmp(argv[i],"-disable_trim")) {
            disable_trim = true;
            cout << "Trimming disabled, dropping instread." << endl;
            UecSrc::_trim_disbled = true;
        } else if (!strcmp(argv[i],"-trimsize")){
            // size of trimmed packet in bytes
            trimsize = atoi(argv[i+1]);
            cout << "trimmed packet size: " << trimsize << " bytes\n";
            i+=1;
        } else if (!strcmp(argv[i],"-logtime")){
            double log_ms = atof(argv[i+1]);            
            logtime = timeFromMs(log_ms);
            cout << "logtime "<< logtime << " ms" << endl;
            i++;
        } else if (!strcmp(argv[i],"-logtime_us")){
            double log_us = atof(argv[i+1]);            
            logtime = timeFromUs(log_us);
            cout << "logtime "<< log_us << " us" << endl;
            i++;
        } else if (!strcmp(argv[i],"-failed")){
            int num_failed = atoi(argv[i+1]);

            if (num_failed == 42) {
                num_failed = 0;
                printf("Activating Special mode for Micro failures scenario\n");
                CompositeQueue::scenario_micro_failures = true;
            } else {
                FatTreeTopology::set_failed_links(num_failed);
            }

            i++;
        } else if (!strcmp(argv[i],"-state_aware_ecn")){
            // State-Aware NSCC+REPS master toggle. Off by default.
            UecSrc::_state_aware_ecn_enabled = true;
            // State-aware mode requires REPS freezing semantics to function.
            CircularBufferREPS<int>::setUseFreezing(true);
            cout << "State-Aware NSCC+REPS enabled (CC will mask ECN unless _network_is_asymmetric)" << endl;

        // ===== ADDED (smart-filter): off by default. Mutually exclusive with =====
        // -state_aware_ecn (hard error below after parse loop).               =====
        // See experiments/expNN_smart_filter/ARCHITECTURE.md.     =====
        } else if (!strcmp(argv[i],"-smart_filter_mode")){
            const char* m = argv[i+1];
            if      (!strcmp(m,"none"))                 UecSrc::_smart_filter_mode = UecSrc::SF_NONE;
            else if (!strcmp(m,"md_gain"))              UecSrc::_smart_filter_mode = UecSrc::SF_MD_GAIN;
            else if (!strcmp(m,"rtt_blend_ecn_thresh")) UecSrc::_smart_filter_mode = UecSrc::SF_RTT_BLEND_ECN_THRESH;
            else { cerr << "Unknown -smart_filter_mode: " << m
                        << " (valid: none, md_gain, rtt_blend_ecn_thresh)" << endl; exit(1); }
            cout << "Smart-filter mode: " << m << endl;
            i++;
        } else if (!strcmp(argv[i],"-smart_filter_counter")){
            const char* c = argv[i+1];
            if      (!strcmp(c,"ecn"))      UecSrc::_smart_filter_counter = UecSrc::SF_COUNTER_ECN;
            else if (!strcmp(c,"fresh"))    UecSrc::_smart_filter_counter = UecSrc::SF_COUNTER_FRESH;
            // ===== ADDED (ev-health-counter) =================================
            else if (!strcmp(c,"evhealth")) UecSrc::_smart_filter_counter = UecSrc::SF_COUNTER_EVHEALTH;
            // ===== END ADDED (ev-health-counter) =============================
            else { cerr << "Unknown -smart_filter_counter: " << c
                        << " (valid: ecn, fresh, evhealth)" << endl; exit(1); }
            cout << "Smart-filter counter source: " << c << endl;
            i++;
        } else if (!strcmp(argv[i],"-smart_filter_ecn_thresh")){
            // Interpreted at use-time against the live B so no manual sync with
            // -reps_buffer_size is needed. Default -1 = auto ceil(B/4).
            int k = atoi(argv[i+1]);
            if (k < -1) { cerr << "-smart_filter_ecn_thresh must be >= -1 (use -1 for auto)\n"; exit(1); }
            UecSrc::_smart_filter_ecn_thresh = k;
            if (k < 0) cout << "Smart-filter ECN threshold: auto (ceil(B/4))" << endl;
            else       cout << "Smart-filter ECN threshold K=" << k << endl;
            i++;
        // ===== END ADDED (smart-filter) =====================================

        // ===== ADDED (wtd-in-nscc): off by default. Mutually exclusive with =====
        // -state_aware_ecn and -smart_filter_mode (hard error below).         =====
        // Reference: SMaRTT-REPS paper §3.6.1.                               =====
        } else if (!strcmp(argv[i],"-wtd_in_nscc")){
            UecSrc::_nscc_wtd_enabled = true;
            cout << "WTD in NSCC enabled (ECN EWMA threshold="
                 << UecSrc::_wtd_threshold << ")" << endl;
        // ===== END ADDED (wtd-in-nscc) ======================================

        } else if (!strcmp(argv[i],"-reps_buffer_size")){
            // Set the FREEZING circular-buffer capacity (default 8).
            // Must be parsed before UecSrc objects are constructed.
            int buf_sz = atoi(argv[i+1]);
            CircularBufferREPS<int>::setBufferSize(buf_sz);
            cout << "REPS buffer size set to " << buf_sz << endl;
            i++;
        } else if (!strcmp(argv[i],"-log_reps_state")){
            // Open output CSV for REPS-buffer state instrumentation.
            UecSrc::_reps_state_log = fopen(argv[i+1], "w");
            if (!UecSrc::_reps_state_log) {
                cerr << "Could not open REPS state log: " << argv[i+1] << endl;
                exit(1);
            }
            fprintf(UecSrc::_reps_state_log,
                    "time_us,src_id,ecn,ack_ev,fresh,cwnd_pkts,buf_size,sa_asym,cc_ecn_view,buf_contents,frozen_mode,frozen_ev,pxr_excluded_count,pxr_excluded_evs\n");
            cout << "Logging REPS-buffer state to " << argv[i+1] << endl;
            i++;
        } else if (!strcmp(argv[i],"-log_reps_state_src")){
            UecSrc::_reps_state_log_srcs.insert((uint32_t)atoi(argv[i+1]));
            cout << "Adding src " << argv[i+1]
                 << " to REPS-state log (total tracked="
                 << UecSrc::_reps_state_log_srcs.size() << ")" << endl;
            i++;
        } else if (!strcmp(argv[i],"-log_buffer_contents")) { // ===== ADDED (buffer-contents-log) =====
            UecSrc::_log_buffer_contents = true;
            cout << "Buffer contents logging enabled (appends buf_contents column to reps_state_log)" << endl;
        // ===== ADDED (reps-event-trace) =====
        } else if (!strcmp(argv[i],"-log_reps_events")){
            // Open unified send+ACK+freeze event trace (independent of -log_reps_state,
            // whose schema is untouched — existing runner scripts parse it).
            UecSrc::_reps_events_log = fopen(argv[i+1], "w");
            if (!UecSrc::_reps_events_log) {
                cerr << "Could not open REPS event trace: " << argv[i+1] << endl;
                exit(1);
            }
            fprintf(UecSrc::_reps_events_log,
                    "n,time_ns,src_id,event,ev,ev_src,ecn,seqno,fresh,buf_size,frozen_mode,frozen_ev,head,frozen_head,cwnd_pkts,inflight_pkts,slots,fifo\n"); // ===== ADDED (reps-fifo-trace): fifo column =====
            cout << "Logging REPS event trace to " << argv[i+1] << endl;
            i++;
        } else if (!strcmp(argv[i],"-log_reps_events_src")){
            UecSrc::_reps_events_log_srcs.insert((uint32_t)atoi(argv[i+1]));
            cout << "Adding src " << argv[i+1]
                 << " to REPS event trace (total tracked="
                 << UecSrc::_reps_events_log_srcs.size() << ")" << endl;
            i++;
        } else if (!strcmp(argv[i],"-log_reps_events_max")){
            UecSrc::_reps_events_max = (uint64_t)atoll(argv[i+1]);
            cout << "REPS event trace row cap set to " << UecSrc::_reps_events_max << endl;
            i++;
        } else if (!strcmp(argv[i],"-log_reps_events_window")){
            // Bounds are in NANOSECONDS, matching the trace's time_ns column
            // (and the pre-existing -log_reps_state time column, which is also
            // now/1000 despite being labelled "time_us").
            UecSrc::_reps_events_t0 = (simtime_picosec)(atof(argv[i+1]) * 1000.0);
            UecSrc::_reps_events_t1 = (simtime_picosec)(atof(argv[i+2]) * 1000.0);
            cout << "REPS event trace window set to [" << argv[i+1] << ", " << argv[i+2] << "] ns" << endl;
            i += 2;
        // ===== END ADDED (reps-event-trace) =====
        } else if (!strcmp(argv[i],"-log_cwnd")) { // ===== ADDED (cwnd-log) =====
            UecSrc::_cwnd_log = fopen(argv[i+1], "w");
            if (!UecSrc::_cwnd_log) {
                cerr << "Could not open cwnd log: " << argv[i+1] << endl; exit(1);
            }
            fprintf(UecSrc::_cwnd_log, "time_us,src_id,cwnd_pkts\n");
            cout << "Logging per-ACK cwnd to " << argv[i+1] << endl;
            i++;
        } else if (!strcmp(argv[i],"-log_cwnd_src")) { // ===== ADDED (cwnd-log) =====
            UecSrc::_cwnd_log_srcs.insert((uint32_t)atoi(argv[i+1]));
            cout << "Filtering cwnd log to src " << argv[i+1] << endl;
            i++;
        // ===== END ADDED (cwnd-log) =====
        } else if (!strcmp(argv[i],"-fail_link_time")){
            fail_link_fail_us    = atof(argv[i+1]);
            fail_link_recover_us = atof(argv[i+2]);
            cout << "Scheduled dynamic link failure: fail at " << fail_link_fail_us
                 << " us, recover at " << fail_link_recover_us << " us" << endl;
            i += 2;
        } else if (!strcmp(argv[i],"-fail_link_target")){
            // Repeatable: each -fail_link_target <agg> <core> appends one link.
            int agg  = atoi(argv[i+1]);
            int core = atoi(argv[i+2]);
            fail_link_targets.emplace_back(agg, core);
            cout << "Dynamic link-failure target appended: agg=" << agg
                 << ", core=" << core
                 << " (total targets=" << fail_link_targets.size() << ")" << endl;
            i += 2;
        } else if (!strcmp(argv[i],"-linkspeed")){
            // linkspeed specified is in Mbps
            linkspeed = speedFromMbps(atof(argv[i+1]));
            i++;
        } else if (!strcmp(argv[i],"-seed")){
            seed = atoi(argv[i+1]);
            cout << "random seed "<< seed << endl;
            i++;
        } else if (!strcmp(argv[i],"-mtu")){
            packet_size = atoi(argv[i+1]);
            i++;
        } else if (!strcmp(argv[i],"-paths")){
            path_entropy_size = atoi(argv[i+1]);
            cout << "no of paths " << path_entropy_size << endl;
            i++;
        } else if (!strcmp(argv[i],"-path_burst")){
            path_burst = atoi(argv[i+1]);
            cout << "path burst " << path_burst << endl;
            i++;
        } else if (!strcmp(argv[i],"-hop_latency")){
            hop_latency = timeFromUs(atof(argv[i+1]));
            cout << "Hop latency set to " << timeAsUs(hop_latency) << endl;
            i++;
        } else if (!strcmp(argv[i],"-pcie")){
            UecSink::_model_pcie = true;
            pcie_rate = atof(argv[i+1]);
            i++;
        } else if (!strcmp(argv[i],"-switch_latency")){
            switch_latency = timeFromUs(atof(argv[i+1]));
            cout << "Switch latency set to " << timeAsUs(switch_latency) << endl;
            i++;
        } else if (!strcmp(argv[i],"-ar_sticky_delta")){
            ar_sticky_delta = atof(argv[i+1]);
            cout << "Adaptive routing sticky delta " << ar_sticky_delta << "us" << endl;
            i++;
        } else if (!strcmp(argv[i],"-ar_granularity")){
            if (!strcmp(argv[i+1],"packet"))
                ar_sticky = FatTreeSwitch::PER_PACKET;
            else if (!strcmp(argv[i+1],"flow"))
                ar_sticky = FatTreeSwitch::PER_FLOWLET;
            else  {
                cout << "Expecting -ar_granularity packet|flow, found " << argv[i+1] << endl;
                exit(1);
            }   
            i++;
        } else if (!strcmp(argv[i],"-ar_method")){
            if (!strcmp(argv[i+1],"pause")){
                cout << "Adaptive routing based on pause state " << endl;
                FatTreeSwitch::fn = &FatTreeSwitch::compare_pause;
            }
            else if (!strcmp(argv[i+1],"queue")){
                cout << "Adaptive routing based on queue size " << endl;
                FatTreeSwitch::fn = &FatTreeSwitch::compare_queuesize;
            }
            else if (!strcmp(argv[i+1],"bandwidth")){
                cout << "Adaptive routing based on bandwidth utilization " << endl;
                FatTreeSwitch::fn = &FatTreeSwitch::compare_bandwidth;
            }
            else if (!strcmp(argv[i+1],"pqb")){
                cout << "Adaptive routing based on pause, queuesize and bandwidth utilization " << endl;
                FatTreeSwitch::fn = &FatTreeSwitch::compare_pqb;
            }
            else if (!strcmp(argv[i+1],"pq")){
                cout << "Adaptive routing based on pause, queuesize" << endl;
                FatTreeSwitch::fn = &FatTreeSwitch::compare_pq;
            }
            else if (!strcmp(argv[i+1],"pb")){
                cout << "Adaptive routing based on pause, bandwidth utilization" << endl;
                FatTreeSwitch::fn = &FatTreeSwitch::compare_pb;
            }
            else if (!strcmp(argv[i+1],"qb")){
                cout << "Adaptive routing based on queuesize, bandwidth utilization" << endl;
                FatTreeSwitch::fn = &FatTreeSwitch::compare_qb; 
            }
            else {
                cout << "Unknown AR method expecting one of pause, queue, bandwidth, pqb, pq, pb, qb" << endl;
                exit(1);
            }
            i++;
        } else if (!strcmp(argv[i],"-strat")){
            if (!strcmp(argv[i+1], "ecmp_host")) {
                route_strategy = ECMP_FIB;
                FatTreeSwitch::set_strategy(FatTreeSwitch::ECMP);
            } else if (!strcmp(argv[i+1], "rr_ecmp")) {
                //this is the host route strategy;
                route_strategy = ECMP_FIB_ECN;
                qt = COMPOSITE_ECN_LB;
                //this is the switch route strategy. 
                FatTreeSwitch::set_strategy(FatTreeSwitch::RR_ECMP);
            } else if (!strcmp(argv[i+1], "ecmp_host_ecn")) {
                route_strategy = ECMP_FIB_ECN;
                FatTreeSwitch::set_strategy(FatTreeSwitch::ECMP);
                qt = COMPOSITE_ECN_LB;
            } else if (!strcmp(argv[i+1], "reactive_ecn")) {
                // Jitu's suggestion for something really simple
                // One path at a time, but switch whenever we get a trim or ecn
                //this is the host route strategy;
                route_strategy = REACTIVE_ECN;
                FatTreeSwitch::set_strategy(FatTreeSwitch::ECMP);
                qt = COMPOSITE_ECN_LB;
            } else if (!strcmp(argv[i+1], "ecmp_ar")) {
                route_strategy = ECMP_FIB;
                path_entropy_size = 1;
                FatTreeSwitch::set_strategy(FatTreeSwitch::ADAPTIVE_ROUTING);
            } else if (!strcmp(argv[i+1], "ecmp_host_ar")) {
                route_strategy = ECMP_FIB;
                FatTreeSwitch::set_strategy(FatTreeSwitch::ECMP_ADAPTIVE);
                //the stuff below obsolete
                //FatTreeSwitch::set_ar_fraction(atoi(argv[i+2]));
                //cout << "AR fraction: " << atoi(argv[i+2]) << endl;
                //i++;
            } else if (!strcmp(argv[i+1], "ecmp_rr")) {
                // switch round robin
                route_strategy = ECMP_FIB;
                path_entropy_size = 1;
                FatTreeSwitch::set_strategy(FatTreeSwitch::RR);
            }
            i++;
        // ===== ADDED (path-random queue logging) =====
        } else if (!strcmp(argv[i], "-log_core_queues")) {
            log_core_queues_file = string(argv[i+1]);
            i++;
        // ===== END ADDED (path-random queue logging) =====
        // ===== ADDED (tor-queue logging) =====
        } else if (!strcmp(argv[i], "-log_tor_queues")) {
            log_tor_queues_file = string(argv[i+1]);
            i++;
        // ===== END ADDED (tor-queue logging) =====
        // ===== ADDED (core-downlink-queue-log) =====
        } else if (!strcmp(argv[i], "-log_core_downlink_queues")) {
            log_core_downlink_queues_file = string(argv[i+1]);
            i++;
        // ===== END ADDED (core-downlink-queue-log) =====
        } else {
            cout << "Unknown parameter " << argv[i] << endl;
            exit_error(argv[0]);
        }
        i++;
    }


    if (input_fail_on) {
        FAILURE_GENERATOR->read_failure_list();
        //FAILURE_GENERATOR->topology = topo[0];
    }

    // ===== ADDED (smart-filter + wtd-in-nscc): coexistence guard ==========
    // -state_aware_ecn, -smart_filter_mode, and -wtd_in_nscc are three
    // independent CC additions that target the same gate site and must not
    // be combined in the same run (each is its own A/B test).
    {
        int cc_addons = (UecSrc::_state_aware_ecn_enabled ? 1 : 0)
                      + (UecSrc::_smart_filter_mode != UecSrc::SF_NONE ? 1 : 0)
                      + (UecSrc::_nscc_wtd_enabled ? 1 : 0);
        if (cc_addons > 1) {
            cerr << "ERROR: -state_aware_ecn, -smart_filter_mode, and -wtd_in_nscc are "
                 << "independent CC additions and must not be combined in the same run. "
                 << "Pick exactly one." << endl;
            exit(1);
        }
    }
    // ===== END ADDED (smart-filter + wtd-in-nscc) ========================

    if (!param_queuesize_set || !param_ecn_set){
        cout << "queuesizes and ecn threshold should be input from the parameters, otherwise, queuesize = BDP of 100Gbps and 12us RTT and ecn_low is 20\% of queuesize and 80\% of queuesize."<< endl;
        //abort(); We should restore to default values here, not abort
    }
    if (!data_collection_dir.empty()) {
        data_collector.setDataDir(data_collection_dir);
        cout << "Data collection dir set as " << data_collection_dir << endl;
    }

    assert(trimsize >= 64 && trimsize <= (uint32_t)packet_size);

    srand(seed);
    srandom(seed);
    cout << "Parsed args\n";
    Packet::set_packet_size(packet_size);

    if (route_strategy==NOT_SET){
        route_strategy = ECMP_FIB;
        FatTreeSwitch::set_strategy(FatTreeSwitch::ECMP);
    }

    queuesize = memFromPkt(queuesize);

    if (ecn){
        ecn_low = memFromPkt(ecn_low);
        ecn_high = memFromPkt(ecn_high);
        bool ecn_on_tor_dl = !receiver_driven && !force_disable_tor_ecn;
        cout << "Setting ECN for queues with size " << queuesize << ", with parameters low " << ecn_low << " high " << ecn_high <<  " enable on tor downlink " << ecn_on_tor_dl << endl;
        FatTreeTopology::set_ecn_parameters(true, ecn_on_tor_dl, ecn_low,ecn_high);
    }

    if (enable_qa_gate){
        UecSrc::_enable_qa_gate = true;
        cout << "enable quick adapt gate" << endl;            
    }

    // if(disable_fair_decrease){
    //     UecSrc::disableFairDecrease();
    // }

    /*
    UecSink::_oversubscribed_congestion_control = oversubscribed_congestion_control;
    */

    FatTreeSwitch::_ar_sticky = ar_sticky;
    FatTreeSwitch::_sticky_delta = timeFromUs(ar_sticky_delta);
    FatTreeSwitch::_ecn_threshold_fraction = ecn_thresh;
    FatTreeSwitch::_disable_trim = disable_trim;
    FatTreeSwitch::_trim_size = trimsize;

    eventlist.setEndtime(timeFromUs((uint32_t)end_time));

    
    
    switch (route_strategy) {
    case ECMP_FIB_ECN:
    case REACTIVE_ECN:
        if (qt != COMPOSITE_ECN_LB) {
            fprintf(stderr, "Route Strategy is ECMP ECN.  Must use an ECN queue\n");
            exit(1);
        }
        if (ecn_thresh <= 0 || ecn_thresh >= 1) {
            fprintf(stderr, "Route Strategy is ECMP ECN.  ecn_thresh must be between 0 and 1\n");
            exit(1);
        }
        // no break, fall through
    case ECMP_FIB:
        break;
    case NOT_SET:
        fprintf(stderr, "Route Strategy not set.  Use the -strat param.  \nValid values are perm, rand, pull, rg and single\n");
        exit(1);
    default:
        break;
    }

    // prepare the loggers

    cout << "Logging to " << filename.str() << endl;
    //Logfile 
    //Logfile logfile(filename.str(), eventlist);

    cout << "Linkspeed set to " << linkspeed/1000000000 << "Gbps" << endl;
    //logfile.setStartTime(timeFromSec(0));

    UecSinkLoggerSampling* sink_logger = NULL;
    if (log_sink) {
        //sink_logger = new UecSinkLoggerSampling(logtime, eventlist);
        //logfile.addLogger(*sink_logger);
    }
    NicLoggerSampling* nic_logger = NULL;
    if (log_nic) {
        nic_logger = new NicLoggerSampling(logtime, eventlist);
        //logfile.addLogger(*nic_logger);
    }
    TrafficLoggerSimple* traffic_logger = NULL;
    if (log_traffic) {
        traffic_logger = new TrafficLoggerSimple();
        //logfile.addLogger(*traffic_logger);
    }
    FlowEventLoggerSimple* event_logger = NULL;
    if (log_flow_events) {
        event_logger = new FlowEventLoggerSimple();
        //logfile.addLogger(*event_logger);
    }

    //UecSrc::setMinRTO(50000); //increase RTO to avoid spurious retransmits
    UecSrc::_path_entropy_size = path_entropy_size;
    
    UecSrc* uec_src;
    UecSink* uec_snk;

    //Route* routeout, *routein;

    // scanner interval must be less than min RTO
    //UecRtxTimerScanner UecRtxScanner(timeFromUs((uint32_t)9), eventlist);
   
    QueueLoggerFactory *qlf = 0;
    if (log_tor_downqueue || log_tor_upqueue) {
        //qlf = new QueueLoggerFactory(&logfile, QueueLoggerFactory::LOGGER_SAMPLING, eventlist);
        qlf->set_sample_period(timeFromUs(10.0));
    } else if (log_queue_usage) {
        //qlf = new QueueLoggerFactory(&logfile, QueueLoggerFactory::LOGGER_EMPTY, eventlist);
        qlf->set_sample_period(timeFromUs(10.0));
    }

    ConnectionMatrix* conns = new ConnectionMatrix(no_of_nodes);

    if (tm_file){
        cout << "Loading connection matrix from  " << tm_file << endl;

        if (!conns->load(tm_file)){
            cout << "Failed to load connection matrix " << tm_file << endl;
            exit(-1);
        }
    }
    else {
        cout << "Loading connection matrix from  standard input" << endl;        
        conns->load(cin);
    }

    if (conns->N != no_of_nodes && no_of_nodes != 0){
        cout << "Connection matrix number of nodes is " << conns->N << " while I am using " << no_of_nodes << endl;
        exit(-1);
    }

    no_of_nodes = conns->N;

    simtime_picosec network_max_unloaded_rtt = 0;
    // Register Metrics
    htsim::CsvMetric* _global_metric = data_collector.RegisterCsvMetric(
        "globalInfo", {"linkSpeedGbps", "linkDelayNs", "packetSizeBytes", "sackThresholdBytes",
                       "queueSizeBytes", "kMinBytes", "kMaxBytes", "loadBalancingAlgo"});

    simtime_picosec network_rtt = 0;
    vector <FatTreeTopology*> topo;
    topo.resize(planes);
    for (uint32_t p = 0; p < planes; p++) {
        if (topo_file) {
            topo[p] = FatTreeTopology::load(topo_file, qlf, eventlist, queuesize, qt, snd_type);
            tiers_latency = topo[p]->get_tiers_latency();
            no_of_nodes = topo[p]->no_of_nodes();
            /* if (topo[p]->no_of_nodes() != no_of_nodes) {
                cerr << "Mismatch between connection matrix (" << no_of_nodes << " nodes) and topology ("
                     << topo[p]->no_of_nodes() << " nodes)" << endl;
                exit(1);
            } */
        } else {
            FatTreeTopology::set_tiers(tiers);
            topo[p] = new FatTreeTopology(no_of_nodes, linkspeed, queuesize, qlf, 
                                          &eventlist, NULL, qt, hop_latency,
                                          switch_latency,
                                          snd_type);
            tiers_latency = topo[p]->get_tiers_latency();
        }

        if (topo[p]->get_oversubscription_ratio() > 1 && !UecSrc::_sender_based_cc && !force_disable_oversubscribed_cc) {
            UecSink::_oversubscribed_cc = true;
            OversubscribedCC::setOversubscriptionRatio(topo[p]->get_oversubscription_ratio());
            cout << "Using simple receiver oversubscribed CC. Oversubscription ratio is " << topo[p]->get_oversubscription_ratio() << endl;
        } 

        if (log_switches) {
            //topo[p]->add_switch_loggers(logfile, timeFromUs(20.0));
        }

        if (p==0) {
            network_max_unloaded_rtt = 2 * topo[p]->get_diameter_latency() + (Packet::data_packet_size() * 8 / speedAsGbps(linkspeed) * topo[p]->get_diameter() * 1000) + (UecBasePacket::get_ack_size() * 8 / speedAsGbps(linkspeed) * topo[p]->get_diameter() * 1000);
        } else {
            // We only allow identical network rtts for now
            assert(network_max_unloaded_rtt == topo[p]->get_diameter_latency());
        }
    }
    cout << "network_max_unloaded_rtt " << timeAsUs(network_max_unloaded_rtt) << endl;

   //2 priority queues; 3 hops for incast
    UecSrc::_min_rto = timeFromUs(timeAsUs(network_max_unloaded_rtt) + queuesize * 4.0 * 8 * 1000000 / linkspeed);

    // ===== ADDED (min-rto-flag) =====
    // Honor the -min_rto override AFTER the auto-compute above so the user's value wins.
    if (min_rto_us_override > 0) {
        UecSrc::_min_rto = timeFromUs((uint32_t)min_rto_us_override);
        cout << "min_rto override applied: " << min_rto_us_override << " us" << endl;
    }
    // ===== END ADDED =====

    cout << "Setting queuesize to " << queuesize << endl;
    cout << "Setting min RTO to " << timeAsUs(UecSrc::_min_rto) << endl;
    
    //handle link failures specified in the connection matrix.
    for (size_t c = 0; c < conns->failures.size(); c++){
        failure* crt = conns->failures.at(c);

        cout << "Adding link failure switch type" << crt->switch_type << " Switch ID " << crt->switch_id << " link ID "  << crt->link_id << endl;
        // xxx we only support failures in plane 0 for now.
        topo[0]->add_failed_link(crt->switch_type,crt->switch_id,crt->link_id);
    }

    // Initialize congestion control algorithms
    if (receiver_driven) {
        // TBD
    } else {
        // UecSrc::parameterScaleToTargetQ();
        UecSrc::initNsccParams(network_max_unloaded_rtt, linkspeed);
    }

    vector<UecPullPacer*> pacers;
    vector<PCIeModel*> pcie_models;
    vector<OversubscribedCC*> oversubscribed_ccs;

    vector<UecNIC*> nics;

    for (size_t ix = 0; ix < no_of_nodes; ix++){
        pacers.push_back(new UecPullPacer(linkspeed, 0.99, UecBasePacket::unquantize(UecSink::_credit_per_pull), eventlist, ports));

        if (UecSink::_model_pcie)
            pcie_models.push_back(new PCIeModel(linkspeed * pcie_rate,UecSrc::_mtu,eventlist,pacers[ix]));

        if (UecSink::_oversubscribed_cc)
            oversubscribed_ccs.push_back(new OversubscribedCC(eventlist,pacers[ix]));

        UecNIC* nic = new UecNIC(ix, eventlist, linkspeed, ports);
        nics.push_back(nic);
        if (log_nic) {
            nic_logger->monitorNic(nic);
        }
    }

    if (!SAVE_DATA_FOLDER.empty())  {
        system((string("mkdir -p ") + SAVE_DATA_FOLDER).c_str());
    }

    if (_collect_data) {
        // build a trailing‐slash‐terminated base directory
        string base_dir = SAVE_DATA_FOLDER;
        if (!base_dir.empty() && base_dir.back() != '/')
            base_dir += '/';

        // remove old data
        system((string("rm -rf ") + base_dir + "psn_over_time/*").c_str());
        system((string("rm -rf ") + base_dir + "port/*").c_str());
        system((string("rm -rf ") + base_dir + "link_util/*").c_str());
        system((string("rm -rf ") + base_dir + "queue/*").c_str());
        system((string("rm -rf ") + base_dir + "queueSize/*").c_str());
        system((string("rm -rf ") + base_dir + "cwd/*").c_str());
        system((string("rm -rf ") + base_dir + "valid_entropies/*").c_str());
        system((string("rm -rf ") + base_dir + "dropped/*").c_str());
        system((string("rm -rf ") + base_dir + "nack/*").c_str());
        system((string("rm -rf ") + base_dir + "ecn/*").c_str());
        system((string("rm -rf ") + base_dir + "rtt/*").c_str());
        system((string("rm -rf ") + base_dir + "new_entropy/*").c_str());
        system((string("rm -rf ") + base_dir + "valid_entropy/*").c_str());
        system((string("rm -rf ") + base_dir + "invalid_entropy/*").c_str());
        system((string("rm -rf ") + base_dir + "list_psn/*").c_str());
        system((string("rm -rf ") + base_dir + "pipe/").c_str());
        system((string("rm -rf ") + base_dir + "switch_drops/*").c_str());
        system((string("rm -rf ") + base_dir + "cable_drops/*").c_str());
        system((string("rm -rf ") + base_dir + "cable_failures/*").c_str());
        system((string("rm -rf ") + base_dir + "switch_failures/*").c_str());
        system((string("rm -rf ") + base_dir + "routing_failed_switch/*").c_str());
        system((string("rm -rf ") + base_dir + "cable_degradations/*").c_str());
        system((string("rm -rf ") + base_dir + "switch_degradations/*").c_str());
        system((string("rm -rf ") + base_dir + "random_packet_drops/*").c_str());
        system((string("rm -rf ") + base_dir + "ratio_over_rtt/*").c_str());
        system((string("rm -rf ") + base_dir + "ratio_over_time/*").c_str());
        system((string("rm -rf ") + base_dir + "psn_over_time/*").c_str());

        // recreate directories
        system((string("mkdir -p ") + base_dir + "switch_drops/").c_str());
        system((string("mkdir -p ") + base_dir + "cable_drops/").c_str());
        system((string("mkdir -p ") + base_dir + "cable_failures/").c_str());
        system((string("mkdir -p ") + base_dir + "switch_failures/").c_str());
        system((string("mkdir -p ") + base_dir + "routing_failed_switch/").c_str());
        system((string("mkdir -p ") + base_dir + "cable_degradations/").c_str());
        system((string("mkdir -p ") + base_dir + "switch_degradations/").c_str());
        system((string("mkdir -p ") + base_dir + "random_packet_drops/").c_str());
        system((string("mkdir -p ") + base_dir + "port/").c_str());
        system((string("mkdir -p ") + base_dir + "link_util/").c_str());
        system((string("mkdir -p ") + base_dir + "queue/").c_str());
        system((string("mkdir -p ") + base_dir + "queueSize/").c_str());
        system((string("mkdir -p ") + base_dir + "cwd/").c_str());
        system((string("mkdir -p ") + base_dir + "valid_entropies/").c_str());
        system((string("mkdir -p ") + base_dir + "dropped/").c_str());
        system((string("mkdir -p ") + base_dir + "nack/").c_str());
        system((string("mkdir -p ") + base_dir + "ecn/").c_str());
        system((string("mkdir -p ") + base_dir + "rtt/").c_str());
        system((string("mkdir -p ") + base_dir + "new_entropy/").c_str());
        system((string("mkdir -p ") + base_dir + "valid_entropy/").c_str());
        system((string("mkdir -p ") + base_dir + "invalid_entropy/").c_str());
        system((string("mkdir -p ") + base_dir + "list_psn/").c_str());
        system((string("mkdir -p ") + base_dir + "ratio_over_rtt/").c_str());
        system((string("mkdir -p ") + base_dir + "ratio_over_time/").c_str());
        system((string("mkdir -p ") + base_dir + "psn_over_time/").c_str());
    } 

    // used just to print out stats data at the end
    list <const Route*> routes;
    
    

    vector<connection*>* all_conns = conns->getAllConnections();
    vector <UecSrc*> uec_srcs;

    map <flowid_t, TriggerTarget*> flowmap;
    if(planes != 1){
        cout << "We are taking the plane 0 to calculate the network rtt; If all the planes have the same tiers, you can remove this check." << endl;
        assert(false);
    }


    mem_b cwnd_b = cwnd*Packet::data_packet_size();

    _global_metric->LogData({std::to_string(speedAsGbps(linkspeed)),
                             tiers_latency,
                             std::to_string(Packet::data_packet_size()),
                             std::to_string(UecSink::_bytes_unacked_threshold),
                             std::to_string(queuesize), std::to_string(ecn_low),
                             std::to_string(ecn_high),
                             std::to_string(UecSrc::_load_balancing_algo)});

    // ===== ADDED (path-static-greedy) =====
    std::map<PacketSink*, int> path_static_edge_load;
    // ===== END ADDED (path-static-greedy) =====
    for (size_t c = 0; c < all_conns->size(); c++){
        connection* crt = all_conns->at(c);
        int src = crt->src;
        int dest = crt->dst;
        assert(planes > 0);
        simtime_picosec transmission_delay = (Packet::data_packet_size() * 8 / speedAsGbps(linkspeed) * topo[0]->get_diameter() * 1000) + (UecBasePacket::get_ack_size() * 8 / speedAsGbps(linkspeed) * topo[0]->get_diameter() * 1000);
        simtime_picosec base_rtt_bw_two_points = 2*topo[0]->get_two_point_diameter_latency(src, dest) + transmission_delay;

        //cout << "Connection " << crt->src << "->" <<crt->dst << " starting at " << crt->start << " size " << crt->size << endl;
        cout << "base_rtt_bw_two_points " << timeAsUs(base_rtt_bw_two_points)  << endl;

        uec_src = new UecSrc(traffic_logger, eventlist, *nics.at(src), ports);

        // If cwnd is 0 initXXcc will set a sensible default value 
        if (receiver_driven) {
            // uec_src->setCwnd(cwnd*Packet::data_packet_size());
            // uec_src->setMaxWnd(cwnd*Packet::data_packet_size());

            if (enable_accurate_base_rtt) {
            	uec_src->initRccc(cwnd_b, base_rtt_bw_two_points);
        	} else {
            	uec_src->initRccc(cwnd_b, network_max_unloaded_rtt);
        	}
        } else {
            if (enable_accurate_base_rtt) {
            	uec_src->initNscc(cwnd_b, base_rtt_bw_two_points);
        	} else {
            	uec_src->initNscc(cwnd_b, network_max_unloaded_rtt);
        	}
        }
        //uec_srcs.push_back(uec_src);
        uec_src->setSrc(src);
        uec_src->setDst(dest);

        // ===== ADDED (per-host-lb) =====
        // If this src host has a -host_lb_overrides entry, re-run LB dispatch
        // with the overridden algorithm. No-op if no override is set.
        uec_src->applyHostLBOverride();
        // ===== END ADDED (per-host-lb) =====

        uec_src->from = src;
        uec_src->to = dest;

        

        if (log_flow_events) {
            uec_src->logFlowEvents(*event_logger);
        }
        
        if (receiver_driven)
            uec_snk = new UecSink(NULL,pacers[dest],*nics.at(dest), ports);
        else //each connection has its own pacer, so receiver driven mode does not kick in! 
            uec_snk = new UecSink(NULL,linkspeed,1.1,UecBasePacket::unquantize(UecSink::_credit_per_pull),eventlist,*nics.at(dest), ports);

        uec_src->setName("Uec_" + ntoa(src) + "_" + ntoa(dest));
        //logfile.writeName(*uec_src);
        uec_snk->setSrc(src);
        uec_snk->from = src;
        uec_snk->to = dest;

        if (input_fail_on) {
            FAILURE_GENERATOR->addSrc(uec_src);
            FAILURE_GENERATOR->addDst(uec_snk);
        }
        

        if (UecSink::_model_pcie){
            uec_snk->setPCIeModel(pcie_models[dest]);
        }
                        
        if (UecSink::_oversubscribed_cc){
            uec_snk->setOversubscribedCC(oversubscribed_ccs[dest]);
        }

        ((DataReceiver*)uec_snk)->setName("Uec_sink_" + ntoa(src) + "_" + ntoa(dest));
        //logfile.writeName(*(DataReceiver*)uec_snk);

        if (crt->flowid) {
            uec_src->setFlowId(crt->flowid);
            uec_snk->setFlowId(crt->flowid);

            uec_src->setHashId(src, dest, crt->flowid);
            uec_snk->setHashId(src, dest, crt->flowid);
            assert(flowmap.find(crt->flowid) == flowmap.end()); // don't have dups
            flowmap[crt->flowid] = uec_src;
        }
                        
        if (crt->size>0){
            uec_src->setFlowsize(crt->size);
        }

        if (crt->trigger) {
            Trigger* trig = conns->getTrigger(crt->trigger, eventlist);
            trig->add_target(*uec_src);
        }
        if (crt->send_done_trigger) {
            Trigger* trig = conns->getTrigger(crt->send_done_trigger, eventlist);
            uec_src->setEndTrigger(*trig);
        }


        if (crt->recv_done_trigger) {
            Trigger* trig = conns->getTrigger(crt->recv_done_trigger, eventlist);
            uec_snk->setEndTrigger(*trig);
        }

        //uec_snk->set_priority(crt->priority);
                        
        //UecRtxScanner.registerUec(*UecSrc);
        for (uint32_t p = 0; p < planes; p++) {
            switch (route_strategy) {
            case ECMP_FIB:
            case ECMP_FIB_ECN:
            case REACTIVE_ECN:
                {
                    Route* srctotor = new Route();
                    srctotor->push_back(topo[p]->queues_ns_nlp[src][topo[p]->HOST_POD_SWITCH(src)][0]);
                    srctotor->push_back(topo[p]->pipes_ns_nlp[src][topo[p]->HOST_POD_SWITCH(src)][0]);
                    srctotor->push_back(topo[p]->queues_ns_nlp[src][topo[p]->HOST_POD_SWITCH(src)][0]->getRemoteEndpoint());

                    Route* dsttotor = new Route();
                    dsttotor->push_back(topo[p]->queues_ns_nlp[dest][topo[p]->HOST_POD_SWITCH(dest)][0]);
                    dsttotor->push_back(topo[p]->pipes_ns_nlp[dest][topo[p]->HOST_POD_SWITCH(dest)][0]);
                    dsttotor->push_back(topo[p]->queues_ns_nlp[dest][topo[p]->HOST_POD_SWITCH(dest)][0]->getRemoteEndpoint());

                    uec_src->connectPort(p, *srctotor, *dsttotor, *uec_snk, crt->start);
                    //uec_src->setPaths(path_entropy_size);
                    //uec_snk->setPaths(path_entropy_size);

                    //register src and snk to receive packets from their respective TORs. 
                    assert(topo[p]->switches_lp[topo[p]->HOST_POD_SWITCH(src)]);
                    assert(topo[p]->switches_lp[topo[p]->HOST_POD_SWITCH(src)]);
                    topo[p]->switches_lp[topo[p]->HOST_POD_SWITCH(src)]->addHostPort(src,uec_snk->flowId(),uec_src->getPort(p));
                    topo[p]->switches_lp[topo[p]->HOST_POD_SWITCH(dest)]->addHostPort(dest,uec_src->flowId(),uec_snk->getPort(p));

                    // ===== ADDED (path-rr) =====
                    // Populate the source-route buffer for PATH_RR.  This must
                    // happen after connectPort() (so _srcaddr/_dstaddr are set)
                    // and uses the topology's pre-computed end-to-end routes.
                    // get_bidir_paths() is a read-only topology query; it is
                    // safe to call for every flow at setup time.
                    // The number of distinct routes depends on placement:
                    //   same ToR  → 1 path
                    //   same pod  → K/2 paths  (different Agg switches)
                    //   diff pod  → (K/2)^2 paths  (all Agg+Core combos)
                    //
                    // IMPORTANT: get_bidir_paths() routes end at the last pipe
                    // to the destination host.  In normal switch-based routing,
                    // FatTreeSwitch::addHostPort() appends the UecSink transport
                    // port as the final FibEntry element.  For source routing we
                    // must append it manually; we use Route(orig, dst) which
                    // copies the route and pushes the sink port as the last hop.
                    if (UecSrc::_load_balancing_algo == UecSrc::PATH_RR ||
                        UecSrc::_load_balancing_algo == UecSrc::PATH_RANDOM ||
                        UecSrc::_load_balancing_algo == UecSrc::PATH_STATIC ||
                        UecSrc::_use_srv6) { // ===== ADDED (path-static) (srv6) =====
                        auto* paths = topo[p]->get_bidir_paths(src, dest, true); // true = also build reverse routes (needed for PATH_STATIC ACK/PULL routing)
                        if (paths && !paths->empty()) {
                            PacketSink* sink_port = uec_snk->getPort(p);
                            vector<const Route*> full_paths;
                            full_paths.reserve(paths->size());
                            for (const Route* r : *paths) {
                                // Append sink_port as the final delivery hop.
                                full_paths.push_back(new Route(*r, *sink_port));
                            }
                            // ===== ADDED (path-static) =====
                            if (UecSrc::_load_balancing_algo == UecSrc::PATH_STATIC) {
                                // ===== ADDED (path-static-greedy) =====
                                // Pick the path whose maximum-loaded edge has minimum load.
                                // Route is iterable over PacketSink*; shared pointers = shared physical links.
                                size_t best_idx = 0;
                                const Route* best = full_paths[0];
                                int best_max = 0x7fffffff;
                                for (size_t ri = 0; ri < full_paths.size(); ri++) {
                                    const Route* rc = full_paths[ri];
                                    int max_load = 0;
                                    for (PacketSink* hop : *rc) {
                                        auto it = path_static_edge_load.find(hop);
                                        if (it != path_static_edge_load.end())
                                            max_load = std::max(max_load, it->second);
                                    }
                                    if (max_load < best_max) {
                                        best_max = max_load;
                                        best = rc;
                                        best_idx = ri;
                                    }
                                }
                                for (PacketSink* hop : *best) path_static_edge_load[hop]++;
                                uec_src->setPaths({best});
                                // ===== END ADDED (path-static-greedy) =====
                                // ===== ADDED (path-static-revroute) =====
                                // Override the sink's port route with the full reverse path so
                                // ACK/PULL credits return on the same physical path as data.
                                // The NIC calls sink->getPortRoute(port) to route control packets;
                                // by default it holds only the first hop (dst→ToR) and uses ECMP.
                                // Replacing it with the full reverse path avoids ECMP hash
                                // collisions in bidirectional tornado and similar workloads.
                                // paths->at(best_idx) is the pre-copy route from get_bidir_paths
                                // which has _reverse populated; the copy used in full_paths does not.
                                const Route* orig_r = (*paths)[best_idx];
                                if (orig_r->reverse()) {
                                    Route* rev = new Route(*orig_r->reverse(), *uec_src->getPort(p));
                                    // Cross-link forward↔reverse so bounced packets (trims) can
                                    // traverse both ways without hitting a null-reverse assert.
                                    const_cast<Route*>(best)->set_reverse(rev);
                                    rev->set_reverse(const_cast<Route*>(best));
                                    uec_snk->getPort(p)->setRoute(*rev);
                                }
                                // ===== END ADDED (path-static-revroute) =====
                                cout << "PATH_STATIC: " << src << "->" << dest
                                     << " plane=" << p << " max_edge_load=" << best_max << "\n";
                            } else {
                            // ===== END ADDED (path-static) =====
                            // ===== ADDED (path-rr-npaths): truncate path list for constrained hosts =====
                            {
                                auto it = path_rr_npaths_override.find((uint32_t)src);
                                if (it != path_rr_npaths_override.end() && full_paths.size() > it->second) {
                                    cout << "path_rr_npaths_override: host " << src
                                         << " capped from " << full_paths.size()
                                         << " to " << it->second << " paths\n";
                                    full_paths.resize(it->second);
                                }
                            }
                            // ===== END ADDED (path-rr-npaths) =====
                            uec_src->setPaths(full_paths);
                            // ===== ADDED (path-rr-order) =====
                            {
                                uint32_t np = (uint32_t)full_paths.size();
                                uint32_t start_idx = 0;
                                switch (UecSrc::_path_rr_start_mode) {
                                    case UecSrc::PATH_RR_START_SRC:         start_idx = src % np; break;
                                    case UecSrc::PATH_RR_START_DST:         start_idx = dest % np; break;
                                    case UecSrc::PATH_RR_START_SRCDST_HASH: start_idx = (src * 7 + dest * 3) % np; break;
                                    case UecSrc::PATH_RR_START_SRC2:        start_idx = (src * 2) % np; break; // ===== ADDED (path-rr-startslot) =====
                                    default: start_idx = 0; break;
                                }
                                uec_src->setPathRRStartIdx(start_idx);
                            }
                            // ===== END ADDED (path-rr-order) =====
                            // ===== ADDED (srv6) =====
                            cout << (UecSrc::_use_srv6 ? "SRv6" :
                                     (UecSrc::_load_balancing_algo == UecSrc::PATH_RANDOM ? "PATH_RANDOM" : "PATH_RR"))
                                 << ": " << src << "->" << dest
                                 << " plane=" << p
                                 << " distinct_paths=" << full_paths.size() << "\n";
                            // ===== END ADDED (srv6) =====
                            } // ===== ADDED (path-static) =====
                        } else {
                            cerr << (UecSrc::_load_balancing_algo == UecSrc::PATH_RANDOM ? "PATH_RANDOM" : "PATH_RR")
                                 << " WARNING: no paths found for "
                                 << src << "->" << dest << " plane=" << p
                                 << "; flow will fall back to entropy=0\n";
                        }
                    }
                    // ===== END ADDED (path-rr) =====
                    break;
                }
            default:
                abort();
            }
        }

        // set up the triggers
        // xxx

        if (log_sink) {
            sink_logger->monitorSink(uec_snk);
        }
    }

    //Logged::dump_idmap();
    // Record the setup
    int pktsize = Packet::data_packet_size();
    //logfile.write("# pktsize=" + ntoa(pktsize) + " bytes");
    //logfile.write("# hostnicrate = " + ntoa(linkspeed/1000000) + " Mbps");
    //logfile.write("# corelinkrate = " + ntoa(HOST_NIC*CORE_TO_HOST) + " pkt/sec");
    //logfile.write("# buffer = " + ntoa((double) (queues_na_ni[0][1]->_maxsize) / ((double) pktsize)) + " pkt");
    
    // State-Aware NSCC+REPS: schedule a dynamic Agg<->Core pipe failure if the
    // user asked for one. Both directions of the link are flipped together to
    // mimic a cut cable. Indexes default to (0, 0) targeting the first
    // agg<->core pipe in the topology.
    if (fail_link_fail_us > 0.0 && !topo.empty() && topo[0] != nullptr) {
        if (fail_link_targets.empty()) {
            fail_link_targets.emplace_back(0, 0); // default = first agg<->core
        }
        FatTreeTopology* t0 = topo[0];
        // simtime_picosec uses picoseconds; 1 us == 1e6 ps. Shared by all targets.
        simtime_picosec t_fail    = (simtime_picosec)(fail_link_fail_us    * 1000000.0);
        simtime_picosec t_recover = (simtime_picosec)(fail_link_recover_us * 1000000.0);
        for (const auto& tgt : fail_link_targets) {
            int agg = tgt.first, core = tgt.second;
            Pipe* up = nullptr;
            Pipe* down = nullptr;
            if (agg  >= 0 && (size_t)agg  < t0->pipes_nup_nc.size() &&
                core >= 0 && (size_t)core < t0->pipes_nup_nc[agg].size() &&
                (size_t)fail_link_bundle < t0->pipes_nup_nc[agg][core].size()) {
                up = t0->pipes_nup_nc[agg][core][fail_link_bundle];
            }
            if (core >= 0 && (size_t)core < t0->pipes_nc_nup.size() &&
                agg  >= 0 && (size_t)agg  < t0->pipes_nc_nup[core].size() &&
                (size_t)fail_link_bundle < t0->pipes_nc_nup[core][agg].size()) {
                down = t0->pipes_nc_nup[core][agg][fail_link_bundle];
            }
            if (up == nullptr || down == nullptr) {
                cerr << "[link_failure] target agg=" << agg
                     << " core=" << core
                     << " not found in topology; skipping." << endl;
                continue;
            }
            new LinkFailureEvent(eventlist, up, down, t_fail, t_recover);
            cout << "[link_failure] scheduled: pipe agg=" << agg
                 << " core=" << core
                 << " fail@" << fail_link_fail_us << "us"
                 << " recover@" << fail_link_recover_us << "us" << endl;
        }
    }

    // ===== ADDED (path-random queue logging) =====
    if (!log_core_queues_file.empty() && !topo.empty() && topo[0] != nullptr) {
        new CoreQueueSampler(eventlist, topo[0], log_core_queues_file, 1.0 /* µs */);
        cout << "[core_queue_sampler] logging to " << log_core_queues_file << endl;
    }
    // ===== END ADDED (path-random queue logging) =====
    // ===== ADDED (tor-queue logging) =====
    if (!log_tor_queues_file.empty() && !topo.empty() && topo[0] != nullptr) {
        new TorQueueSampler(eventlist, topo[0], log_tor_queues_file, 1.0 /* µs */);
        cout << "[tor_queue_sampler] logging to " << log_tor_queues_file << endl;
    }
    // ===== END ADDED (tor-queue logging) =====
    // ===== ADDED (core-downlink-queue-log) =====
    if (!log_core_downlink_queues_file.empty() && !topo.empty() && topo[0] != nullptr) {
        new CoreDownlinkQueueSampler(eventlist, topo[0], log_core_downlink_queues_file,
                                      0.2 /* µs, exp25: resolve few-µs round-robin burst */,
                                      16  /* first 16 core switches, exp25 subset */);
        cout << "[core_downlink_queue_sampler] logging to " << log_core_downlink_queues_file << endl;
    }
    // ===== END ADDED (core-downlink-queue-log) =====

    // GO!
    cout << "Starting simulation" << endl;
    while (eventlist.doNextEvent()) {
    }

    cout << "Done" << endl;
    if (CompositeQueue::_log_ecn_timeseries) {
        CompositeQueue::dump_ecn_timeseries(cout);
    }
    int new_pkts = 0, rtx_pkts = 0, bounce_pkts = 0, rts_pkts = 0, ack_pkts = 0;
    for (size_t ix = 0; ix < uec_srcs.size(); ix++) {
        new_pkts += uec_srcs[ix]->_new_packets_sent;
        rtx_pkts += uec_srcs[ix]->_rtx_packets_sent;
        rts_pkts += uec_srcs[ix]->_rts_packets_sent;
        bounce_pkts += uec_srcs[ix]->_bounces_received;
        ack_pkts += uec_srcs[ix]->_acks_received;
    }
    cout << "New: " << new_pkts << " Rtx: " << rtx_pkts << " RTS: " << rts_pkts << " Bounced: " << bounce_pkts << " ACKs: " << ack_pkts << endl;
    if (input_fail_on) {
        FAILURE_GENERATOR->createLoggingData();
        FAILURE_GENERATOR->save_failure_list();

    }
    if (FatTreeSwitch::_log_switch_stats) {
        for (int i = 0; i < topo[0]->switches_lp.size(); i++) {
            if (topo[0]->switches_lp[i]->_up_ports_used.size() == 0 || topo[0]->switches_lp[i]->nodename() != "Switch_LowerPod_0") {
                continue;
            }
            printf("Switch %s\n", topo[0]->switches_lp[i]->nodename().c_str());
            for (int j = 0; j < topo[0]->switches_lp[i]->_up_ports_used.size(); j++) {
                printf("Port: %s\n", topo[0]->switches_lp[i]->_up_ports_used[j].c_str());
            }
        }
    }  
}

