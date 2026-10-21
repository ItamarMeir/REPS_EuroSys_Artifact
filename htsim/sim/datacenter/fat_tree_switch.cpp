// -*- c-basic-offset: 4; indent-tabs-mode: nil -*-
#include "fat_tree_switch.h"
#include "routetable.h"
#include "fat_tree_topology.h"
#include "callback_pipe.h"
#include "queue_lossless.h"
#include "queue_lossless_output.h"
// ===== ADDED (routing-convergence) =====
#include <algorithm>
// ===== END ADDED (routing-convergence) =====

unordered_map<BaseQueue*,uint32_t> FatTreeSwitch::_port_flow_counts;
bool FatTreeSwitch::_log_link_utilization = false;
int FatTreeSwitch::_num_disable_per_switch = 0;
bool FatTreeSwitch::_log_switch_stats = false;

FatTreeSwitch::FatTreeSwitch(EventList& eventlist, string s, switch_type t, uint32_t id,simtime_picosec delay, FatTreeTopology* ft): Switch(eventlist, s) {
    _id = id;
    _type = t;
    _pipe = new CallbackPipe(delay,eventlist, this);
    _uproutes = NULL;
    _ft = ft;
    _crt_route = 0;
    _hash_salt = random();
    _last_choice = eventlist.now();
    _fib = new RouteTable();
}

void FatTreeSwitch::receivePacket(Packet& pkt){

    /* if (pkt.size() > 100 && _log_link_utilization) {
        std::string file_name = ("port/port" + nodename() + "_" + ".txt");
        std::ofstream MyPortFile(file_name, std::ios_base::app);
        MyPortFile << eventlist().now() / 1000 << "," << e->getEgressPort()->at(0)->nodename() << "," << pkt.id()  << std::endl;
        MyPortFile.close();
    }  */


    if (pkt.type()==ETH_PAUSE){
        EthPausePacket* p = (EthPausePacket*)&pkt;
        //I must be in lossless mode!
        //find the egress queue that should process this, and pass it over for processing. 
        for (size_t i = 0;i < _ports.size();i++){
            LosslessQueue* q = (LosslessQueue*)_ports.at(i);
            if (q->getRemoteEndpoint() && ((Switch*)q->getRemoteEndpoint())->getID() == p->senderID()){
                q->receivePacket(pkt);
                break;
            }
        }
        
        return;
    }

    if (_packets.find(&pkt)==_packets.end()){
        //ingress pipeline processing.

        _packets[&pkt] = true;

        const Route * nh = getNextHop(pkt,NULL);
        //set next hop which is peer switch.
        pkt.set_route(*nh);

        //emulate the switching latency between ingress and packet arriving at the egress queue.
        _pipe->receivePacket(pkt); 
    }
    else {
        _packets.erase(&pkt);
        
        //egress queue processing.
        //cout << "Switch type " << _type <<  " id " << _id << " pkt dst " << pkt.dst() << " dir " << pkt.get_direction() << endl;
        pkt.sendOn();
    }
};

void FatTreeSwitch::addHostPort(int addr, int flowid, PacketSink* transport_port){
    Route* rt = new Route();
    rt->push_back(_ft->queues_nlp_ns[_ft->HOST_POD_SWITCH(addr)][addr][0]);
    rt->push_back(_ft->pipes_nlp_ns[_ft->HOST_POD_SWITCH(addr)][addr][0]);
    rt->push_back(transport_port);
    _fib->addHostRoute(addr,rt,flowid);
}

uint32_t mhash(uint32_t x) {
    x = ((x >> 16) ^ x) * 0x45d9f3b;
    x = ((x >> 16) ^ x) * 0x45d9f3b;
    x = (x >> 16) ^ x;
    return x;
}

uint32_t FatTreeSwitch::adaptive_route_p2c(vector<FibEntry*>* ecmp_set, int8_t (*cmp)(FibEntry*,FibEntry*)){
    uint32_t choice = 0, min = UINT32_MAX;
    uint32_t start, i = 0;
    static const uint16_t nr_choices = 2;
    
    do {
        start = random()%ecmp_set->size();

        Route * r= (*ecmp_set)[start]->getEgressPort();
        assert(r && r->size()>1);
        BaseQueue* q = (BaseQueue*)(r->at(0));
        assert(q);
        if (q->queuesize()<min){
            choice = start;
            min = q->queuesize();
        }
        i++;
    } while (i<nr_choices);
    return choice;
}


uint32_t FatTreeSwitch::adaptive_nvidia(vector<FibEntry*>* ecmp_set){
    //printf("Adaptive RoCe\n");
    uint32_t choice = 0;

    int smallest_queue = 9999999999;

    for (int i = 0; i< ecmp_set->size(); i++){
        Route * r1= ecmp_set->at(i)->getEgressPort();
        BaseQueue* q1 = dynamic_cast<BaseQueue*>(r1->at(0));
        int queue_size = q1->queuesize();
        if (queue_size < smallest_queue){
            smallest_queue = queue_size;
            choice = i;
            //printf("Switch %s (Q %s): Queue size %d - ECMP %d - Options %d\n", nodename().c_str(), q1->_name.c_str(), queue_size, i, ecmp_set->size());
        }
    }
    //printf("\n");
    return choice;
}

uint32_t FatTreeSwitch::adaptive_route(vector<FibEntry*>* ecmp_set, int8_t (*cmp)(FibEntry*,FibEntry*)){
    //cout << "adaptive_route" << endl;
    uint32_t choice = 0;

    uint32_t best_choices[256];
    uint32_t best_choices_count = 0;
  
    FibEntry* min = (*ecmp_set)[choice];
    best_choices[best_choices_count++] = choice;

    for (uint32_t i = 1; i< ecmp_set->size(); i++){
        int8_t c = cmp(min,(*ecmp_set)[i]);

        if (c < 0){
            choice = i;
            min = (*ecmp_set)[choice];
            best_choices_count = 0;
            best_choices[best_choices_count++] = choice;
        }
        else if (c==0){
            assert(best_choices_count<255);
            best_choices[best_choices_count++] = i;
        }        
    }

    assert (best_choices_count>=1);
    uint32_t choiceindex = random()%best_choices_count;
    choice = best_choices[choiceindex];
    //cout << "ECMP set choices " << ecmp_set->size() << " Choice count " << best_choices_count << " chosen entry " << choiceindex << " chosen path " << choice << " ";

    if (cmp==compare_flow_count){
        //for (uint32_t i = 0; i<best_choices_count;i++)
          //  cout << "pathcnt " << best_choices[i] << "="<< _port_flow_counts[(BaseQueue*)( (*ecmp_set)[best_choices[i]]->getEgressPort()->at(0))]<< " ";
        
        _port_flow_counts[(BaseQueue*)((*ecmp_set)[choice]->getEgressPort()->at(0))]++;
    }

    return choice;
}

uint32_t FatTreeSwitch::replace_worst_choice(vector<FibEntry*>* ecmp_set, int8_t (*cmp)(FibEntry*,FibEntry*),uint32_t my_choice){
    uint32_t best_choice = 0;
    uint32_t worst_choice = 0;

    uint32_t best_choices[256];
    uint32_t best_choices_count = 0;

    FibEntry* min = (*ecmp_set)[best_choice];
    FibEntry* max = (*ecmp_set)[worst_choice];
    best_choices[best_choices_count++] = best_choice;

    for (uint32_t i = 1; i< ecmp_set->size(); i++){
        int8_t c = cmp(min,(*ecmp_set)[i]);

        if (c < 0){
            best_choice = i;
            min = (*ecmp_set)[best_choice];
            best_choices_count = 0;
            best_choices[best_choices_count++] = best_choice;
        }
        else if (c==0){
            assert(best_choices_count<256);
            best_choices[best_choices_count++] = i;
        }        

        if (cmp(max,(*ecmp_set)[i])>0){
            worst_choice = i;
            max = (*ecmp_set)[worst_choice];
        }
    }

    //might need to play with different alternatives here, compare to worst rather than just to worst index.
    int8_t r = cmp((*ecmp_set)[my_choice],(*ecmp_set)[worst_choice]);
    assert(r>=0);

    if (r==0){
        assert (best_choices_count>=1);
        return best_choices[random()%best_choices_count];
    }
    else return my_choice;
}


int8_t FatTreeSwitch::compare_pause(FibEntry* left, FibEntry* right){
    Route * r1= left->getEgressPort();
    assert(r1 && r1->size()>1);
    LosslessOutputQueue* q1 = dynamic_cast<LosslessOutputQueue*>(r1->at(0));
    Route * r2= right->getEgressPort();
    assert(r2 && r2->size()>1);
    LosslessOutputQueue* q2 = dynamic_cast<LosslessOutputQueue*>(r2->at(0));

    if (!q1->is_paused()&&q2->is_paused())
        return 1;
    else if (q1->is_paused()&&!q2->is_paused())
        return -1;
    else 
        return 0;
}

int8_t FatTreeSwitch::compare_flow_count(FibEntry* left, FibEntry* right){
    Route * r1= left->getEgressPort();
    assert(r1 && r1->size()>1);
    BaseQueue* q1 = (BaseQueue*)(r1->at(0));
    Route * r2= right->getEgressPort();
    assert(r2 && r2->size()>1);
    BaseQueue* q2 = (BaseQueue*)(r2->at(0));

    if (_port_flow_counts.find(q1)==_port_flow_counts.end())
        _port_flow_counts[q1] = 0;

    if (_port_flow_counts.find(q2)==_port_flow_counts.end())
        _port_flow_counts[q2] = 0;

    //cout << "CMP q1 " << q1 << "=" << _port_flow_counts[q1] << " q2 " << q2 << "=" << _port_flow_counts[q2] << endl; 

    if (_port_flow_counts[q1] < _port_flow_counts[q2])
        return 1;
    else if (_port_flow_counts[q1] > _port_flow_counts[q2] )
        return -1;
    else 
        return 0;
}

int8_t FatTreeSwitch::compare_queuesize(FibEntry* left, FibEntry* right){
    Route * r1= left->getEgressPort();
    assert(r1 && r1->size()>1);
    BaseQueue* q1 = dynamic_cast<BaseQueue*>(r1->at(0));
    Route * r2= right->getEgressPort();
    assert(r2 && r2->size()>1);
    BaseQueue* q2 = dynamic_cast<BaseQueue*>(r2->at(0));

    if (q1->quantized_queuesize() < q2->quantized_queuesize())
        return 1;
    else if (q1->quantized_queuesize() > q2->quantized_queuesize())
        return -1;
    else 
        return 0;
}

// ===== ADDED (switch-baselines) =====
int8_t FatTreeSwitch::compare_queuesize_exact(FibEntry* left, FibEntry* right){
    BaseQueue* q1 = dynamic_cast<BaseQueue*>(left->getEgressPort()->at(0));
    BaseQueue* q2 = dynamic_cast<BaseQueue*>(right->getEgressPort()->at(0));
    if (q1->queuesize() < q2->queuesize()) return 1;
    else if (q1->queuesize() > q2->queuesize()) return -1;
    return 0;
}
// ===== END ADDED (switch-baselines) =====

int8_t FatTreeSwitch::compare_bandwidth(FibEntry* left, FibEntry* right){
    Route * r1= left->getEgressPort();
    assert(r1 && r1->size()>1);
    BaseQueue* q1 = dynamic_cast<BaseQueue*>(r1->at(0));
    Route * r2= right->getEgressPort();
    assert(r2 && r2->size()>1);
    BaseQueue* q2 = dynamic_cast<BaseQueue*>(r2->at(0));

    if (q1->quantized_utilization() < q2->quantized_utilization())
        return 1;
    else if (q1->quantized_utilization() > q2->quantized_utilization())
        return -1;
    else 
        return 0;

    /*if (q1->average_utilization() < q2->average_utilization())
        return 1;
    else if (q1->average_utilization() > q2->average_utilization())
        return -1;
    else 
        return 0;        */
}

int8_t FatTreeSwitch::compare_pqb(FibEntry* left, FibEntry* right){
    //compare pause, queuesize, bandwidth.
    int8_t p = compare_pause(left, right);

    if (p!=0)
        return p;
    
    p = compare_queuesize(left,right);

    if (p!=0)
        return p;

    return compare_bandwidth(left,right);
}

int8_t FatTreeSwitch::compare_pq(FibEntry* left, FibEntry* right){
    //compare pause, queuesize, bandwidth.
    int8_t p = compare_pause(left, right);

    if (p!=0)
        return p;
    
    return compare_queuesize(left,right);
}

int8_t FatTreeSwitch::compare_qb(FibEntry* left, FibEntry* right){
    //compare pause, queuesize, bandwidth.
    int8_t p = compare_queuesize(left, right);

    if (p!=0)
        return p;
    
    return compare_bandwidth(left,right);
}

int8_t FatTreeSwitch::compare_pb(FibEntry* left, FibEntry* right){
    //compare pause, queuesize, bandwidth.
    int8_t p = compare_pause(left, right);

    if (p!=0)
        return p;
    
    return compare_bandwidth(left,right);
}

void FatTreeSwitch::permute_paths(vector<FibEntry *>* uproutes) {
    int len = uproutes->size();
    for (int i = 0; i < len; i++) {
        int ix = random() % (len - i);
        FibEntry* tmppath = (*uproutes)[ix];
        (*uproutes)[ix] = (*uproutes)[len-1-i];
        (*uproutes)[len-1-i] = tmppath;
    }
}

FatTreeSwitch::routing_strategy FatTreeSwitch::_strategy = FatTreeSwitch::NIX;
uint16_t FatTreeSwitch::_ar_fraction = 0;
uint16_t FatTreeSwitch::_ar_sticky = FatTreeSwitch::PER_PACKET;
simtime_picosec FatTreeSwitch::_sticky_delta = timeFromUs((uint32_t)10);
double FatTreeSwitch::_ecn_threshold_fraction = 0.2;
double FatTreeSwitch::_speculative_threshold_fraction = 0.2;
int8_t (*FatTreeSwitch::fn)(FibEntry*,FibEntry*)= &FatTreeSwitch::compare_queuesize;
uint16_t FatTreeSwitch::_trim_size = 64;
bool FatTreeSwitch::_disable_trim = false;
bool FatTreeSwitch::use_adaptive_roce = false;

// ===== ADDED (ofan) =====
#include "ofan_order.h"
#include "pipe.h"
#include <fstream>

bool FatTreeSwitch::_ofan_hash_small = false;
bool FatTreeSwitch::_ofan_identity_order = false;
bool FatTreeSwitch::_ofan_count = false;
string FatTreeSwitch::_ofan_trace_file = "";  // ===== ADDED (ofan-trace) =====
// "switch<TAB>d<TAB>t<TAB>class<TAB>egress queue" -> packets (TSV: node names contain commas). Keyed by PHYSICAL egress queue
// (not FIB index) so it also catches port-order inconsistencies across keys.
static unordered_map<string, uint64_t> g_ofan_counts;

void FatTreeSwitch::ofan_dump_counts(const string& file) {
    ofstream f(file.c_str());
    f << "switch\td\tt\tclass\tport\tcount\n";
    for (unordered_map<string, uint64_t>::const_iterator it = g_ofan_counts.begin(); it != g_ofan_counts.end(); ++it)
        f << it->first << "\t" << it->second << "\n";
}

// ===== ADDED (ofan-trace) =====
#include <set>
static ofstream& ofan_trace_stream(const string& file) {
    static ofstream tr(file.c_str());
    return tr;
}
// ===== END ADDED (ofan-trace) =====

// Returns the index into hops of the chosen egress port. Sets handled=false
// (caller then uses the ECMP hash) for any set Ofan does not own: only
// northbound sets (TOR->AGG, AGG->CORE) have a per-destination pointer; DOWN
// sets (incl. bundles) and CORE switches are single-path per destination.
uint32_t FatTreeSwitch::ofan_choose(Packet& pkt, vector<FibEntry*>* hops, bool& handled, const vector<bool>* rc_valid) {
    handled = false;
    if ((*hops)[0]->getDirection() != UP || (_type != TOR && _type != AGG))
        return 0;
    // t=0: full data packets; t=1: ACK/NACK/PULL and trimmed headers (exact by type, not size)
    int t = (pkt.type() == UECDATA && !pkt.header_only()) ? 0 : 1;
    if (t == 1 && _ofan_hash_small)
        return 0;

    uint32_t d, Nd;
    if (_type == TOR) {
        uint32_t hosts_per_tor = _ft->radix_down(TOR_TIER);
        d = _ft->HOST_POD_SWITCH(pkt.dst());
        Nd = (_ft->no_of_nodes() + hosts_per_tor - 1) / hosts_per_tor;
    } else {
        d = _ft->HOST_POD(pkt.dst());
        Nd = _ft->no_of_pods();
    }
    int w = (int)hops->size();
    uint32_t id = d + Nd * t;

    // data/ACK pointers of a destination are created together: the ACK one
    // starts half a round away from the data one.
    unordered_map<uint32_t,int>::iterator it = _ofan_ptrs.find(id);
    if (it == _ofan_ptrs.end()) {
        int data_init = ofan::init_ptr_data((int)(random() % (uint32_t)w), w);
        _ofan_ptrs[d] = data_init;
        _ofan_ptrs[d + Nd] = ofan::init_ptr_ack(data_init, w);
        it = _ofan_ptrs.find(id);
        // ===== ADDED (ofan-trace) =====
        if (!_ofan_trace_file.empty()) {
            ofstream& tr = ofan_trace_stream(_ofan_trace_file);
            const char* ty = (_type == TOR) ? "TOR" : "AGG";
            for (int tt = 0; tt < 2; tt++)
                tr << "I\t" << nodename() << "\t" << ty << "\t" << getID() << "\t" << d << "\t" << tt << "\t"
                   << _ofan_ptrs[d + Nd * tt] << "\n";
        }
        // ===== END ADDED (ofan-trace) =====
    }
    // ===== ADDED (ofan-trace) =====
    int trace_ptr_before = it->second;
    // ===== END ADDED (ofan-trace) =====

    // Skip locally failed first-hop pipes. The pointer is committed past the
    // slot actually used (ofan::pick) so each live port still gets one packet
    // per round. Only evaluated if some port is down (no per-packet alloc).
    bool any_failed = false;
    // ===== ADDED (routing-convergence) =====
    // Under -routing_convergence_us the legacy instant local isFailed() skip is disabled:
    // knowledge comes only from the failure view (rc_valid; NULL = every port valid).
    if (!RoutingConvergence::enabled)
    // ===== END ADDED (routing-convergence) =====
    for (int i = 0; i < w && !any_failed; i++) {
        Pipe* p = dynamic_cast<Pipe*>((*hops)[i]->getEgressPort()->at(1));
        any_failed = (p && p->isFailed());
    }
    int choice;
    // ===== ADDED (routing-convergence) =====
    if (RoutingConvergence::enabled) {
        if (rc_valid)
            choice = ofan::pick(it->second, id, w, *rc_valid, ofan::DEFAULT_SEED, _ofan_identity_order);
        else
            choice = ofan::step(it->second, id, w, ofan::DEFAULT_SEED, _ofan_identity_order);
    } else
    // ===== END ADDED (routing-convergence) =====
    if (any_failed) {
        vector<bool> valid(w, true);
        for (int i = 0; i < w; i++) {
            Pipe* p = dynamic_cast<Pipe*>((*hops)[i]->getEgressPort()->at(1));
            valid[i] = !(p && p->isFailed());
        }
        choice = ofan::pick(it->second, id, w, valid, ofan::DEFAULT_SEED, _ofan_identity_order);
    } else {
        choice = ofan::step(it->second, id, w, ofan::DEFAULT_SEED, _ofan_identity_order);
    }

    // ===== ADDED (ofan-trace) =====
    if (!_ofan_trace_file.empty()) {
        ofstream& tr = ofan_trace_stream(_ofan_trace_file);
        static set<int> perm_done;
        if (!perm_done.count(w)) {
            perm_done.insert(w);
            const vector<int>& P = ofan::shared_perm(w);
            tr << "P\t" << w << "\t";
            for (int i = 0; i < w; i++) tr << (i ? "," : "") << P[i];
            tr << "\n";
        }
        const char* pt = (pkt.type() == UECDATA && pkt.header_only()) ? "TRIM" :
            pkt.type() == UECDATA ? "DATA" : pkt.type() == UECACK ? "ACK" :
            pkt.type() == UECNACK ? "NACK" : pkt.type() == UECPULL ? "PULL" : "OTHER";
        tr << "D\t" << eventlist().now() << "\t" << nodename() << "\t" << (_type == TOR ? "TOR" : "AGG") << "\t"
           << getID() << "\t" << pt << "\t" << pkt.size() << "\t" << pkt.dst() << "\t" << d << "\t" << Nd << "\t"
           << t << "\t" << w << "\t" << trace_ptr_before << "\t" << choice << "\t"
           << (*hops)[choice]->getEgressPort()->at(0)->nodename() << "\n";
    }
    // ===== END ADDED (ofan-trace) =====
    if (_ofan_count) {
        // control packets are header_only() too, so test the type first
        const char* cls = (pkt.type() == UECDATA && pkt.header_only()) ? "TRIM" :
            pkt.type() == UECDATA ? "DATA" : pkt.type() == UECACK ? "ACK" :
            pkt.type() == UECNACK ? "NACK" : pkt.type() == UECPULL ? "PULL" : "OTHER";
        g_ofan_counts[nodename() + "	" + to_string(d) + "	" + to_string(t) + "	" + cls + "	" +
                      (*hops)[choice]->getEgressPort()->at(0)->nodename()]++;
    }
    handled = true;
    return (uint32_t)choice;
}
// ===== END ADDED (ofan) =====

Route* FatTreeSwitch::getNextHop(Packet& pkt, BaseQueue* ingress_port){
    vector<FibEntry*> * available_hops = _fib->getRoutes(pkt.dst());

    if (available_hops){
        // ===== ADDED (routing-convergence) =====
        // Known-failure filtering. rc==NULL => every entry valid => original vector used untouched.
        // OFAN keeps the full vector (mask handed to ofan::pick); all other strategies run on the
        // cached filtered copy. Dead end (no valid entry) => unfiltered (Ofan paper fn.5).
        vector<FibEntry*>* rc_orig = available_hops;
        RcEntry* rc = NULL;
        if (RoutingConvergence::enabled && available_hops->size() > 1) {
            rc = rc_lookup(available_hops, _ft->HOST_POD_SWITCH(pkt.dst()));
            if (rc && !rc->dead_end && _strategy != OFAN)
                available_hops = &rc->filtered;
        }
        // ===== END ADDED (routing-convergence) =====
        //implement a form of ECMP hashing; might need to revisit based on measured performance.
        uint32_t ecmp_choice = 0;
        if (available_hops->size()>1)
            switch(_strategy){
            case NIX:
                abort();
            case ECMP:
                if (use_adaptive_roce && pkt.no_bg) {
                    ecmp_choice = adaptive_nvidia(available_hops);
                } else {
                    ecmp_choice = freeBSDHash(pkt.flow_id_src_dest(),pkt.pathid(),_hash_salt) % available_hops->size();
                }
                break;
            case ADAPTIVE_ROUTING:
                if (pkt.size() < 100) {
                    // don't bother adaptive routing the small packets - don't want to pollute the tables
                    ecmp_choice = freeBSDHash(pkt.flow_id_src_dest(),pkt.pathid(),_hash_salt) % available_hops->size();
                    break;
                }
                if (_ar_sticky==FatTreeSwitch::PER_PACKET){
                    ecmp_choice = adaptive_route(available_hops,fn); 
                } else if (_ar_sticky==FatTreeSwitch::PER_FLOWLET){     
                    // ===== ADDED (routing-convergence) ===== stale index guard (maps are cleared per epoch)
                    if (_flowlet_maps.find(pkt.flow_id())!=_flowlet_maps.end() &&
                        !(RoutingConvergence::enabled && _flowlet_maps[pkt.flow_id()]->_egress >= available_hops->size())){
                    // ===== END ADDED (routing-convergence) =====
                        FlowletInfo* f = _flowlet_maps[pkt.flow_id()];
                        
                        // only reroute an existing flow if its inter packet time is larger than _sticky_delta and
                        // and
                        // 50% chance happens. 
                        // and (commented out) if the switch has not taken any other placement decision that we've not seen the effects of.
                        if (eventlist().now() - f->_last > _sticky_delta && /*eventlist().now() - _last_choice > _pipe->delay() + BaseQueue::_update_period  &&*/ random()%2==0){ 
                            //cout << "AR 1 " << timeAsUs(eventlist().now()) << endl;
                            uint32_t new_route = adaptive_route(available_hops,fn); 
                            if (fn(available_hops->at(f->_egress),available_hops->at(new_route)) < 0){
                                f->_egress = new_route;
                                _last_choice = eventlist().now();
                                //cout << "Switch " << _type << ":" << _id << " choosing new path "<<  f->_egress << " for " << pkt.flow_id() << " at " << timeAsUs(eventlist().now()) << " last is " << timeAsUs(f->_last) << endl;
                            }
                        }
                        ecmp_choice = f->_egress;

                        f->_last = eventlist().now();
                    }
                    else {
                        //cout << "AR 2 " << timeAsUs(eventlist().now()) << endl;
                        ecmp_choice = adaptive_route(available_hops,fn); 
                        _last_choice = eventlist().now();

                        _flowlet_maps[pkt.flow_id()] = new FlowletInfo(ecmp_choice,eventlist().now());
                    }
                }

                break;
            case ECMP_ADAPTIVE:
                ecmp_choice = freeBSDHash(pkt.flow_id_src_dest(),pkt.pathid(),_hash_salt) % available_hops->size();
                if (random()%100 < 50)
                    ecmp_choice = replace_worst_choice(available_hops,fn, ecmp_choice);
                break;
            case RR:
                if (pkt.size()<128)
                    ecmp_choice = freeBSDHash(pkt.flow_id_src_dest(),pkt.pathid(),_hash_salt) % available_hops->size();
                else {
                    if (_crt_route>=1*available_hops->size()){
                        _crt_route = 0;
                        permute_paths(available_hops);
                    }
                    ecmp_choice = _crt_route % available_hops->size();
                    _crt_route ++;
                }
                break;
            case RR_ECMP:
                if (_type == TOR){
                    if (_crt_route>=5 * available_hops->size()){
                        _crt_route = 0;
                        permute_paths(available_hops);
                    }
                    ecmp_choice = _crt_route % available_hops->size();
                    _crt_route ++;
                }
                else ecmp_choice = freeBSDHash(pkt.flow_id_src_dest(),pkt.pathid(),_hash_salt) % available_hops->size();

                break;
            // ===== ADDED (ofan) =====
            case OFAN: {
                bool handled;
                ecmp_choice = ofan_choose(pkt, available_hops, handled, rc ? &rc->valid : NULL);
                // ===== ADDED (routing-convergence) ===== non-owned sets hash over the filtered vector
                if (!handled && rc && !rc->dead_end)
                    available_hops = &rc->filtered;
                // ===== END ADDED (routing-convergence) =====
                if (!handled)
                    ecmp_choice = freeBSDHash(pkt.flow_id_src_dest(),pkt.pathid(),_hash_salt) % available_hops->size();
                break;
            }
            // ===== END ADDED (ofan) =====
            // ===== ADDED (switch-baselines) =====
            case RR_FIXED:
                // Simple RR as in the Ofan paper: fixed port order, one switch-wide pointer, no per-round permutation
                if (pkt.size()<128)
                    ecmp_choice = freeBSDHash(pkt.flow_id_src_dest(),pkt.pathid(),_hash_salt) % available_hops->size();
                else {
                    ecmp_choice = _crt_route % available_hops->size();
                    _crt_route ++;
                }
                break;
            case RANDOM:
                if (pkt.size()<100)
                    ecmp_choice = freeBSDHash(pkt.flow_id_src_dest(),pkt.pathid(),_hash_salt) % available_hops->size();
                else
                    ecmp_choice = random() % available_hops->size();
                break;
            case P2C:
                if (pkt.size()<100)
                    ecmp_choice = freeBSDHash(pkt.flow_id_src_dest(),pkt.pathid(),_hash_salt) % available_hops->size();
                else
                    ecmp_choice = adaptive_route_p2c(available_hops,fn);
                break;
            // ===== END ADDED (switch-baselines) =====
            }

        FibEntry* e = (*available_hops)[ecmp_choice];
        // ===== ADDED (routing-convergence) =====
        // Counter: a decision for a port known dead (by mask or by its own first-hop pipe) while
        // a valid alternative existed must never happen.
        if (RoutingConvergence::enabled && rc_orig->size() > 1) {
            bool bad = false;
            // by entry identity, not index: RR/RR_ECMP permute the shared original vector in place
            if (rc) bad = find(rc->invalid.begin(), rc->invalid.end(), e) != rc->invalid.end();
            Pipe* fp = dynamic_cast<Pipe*>(e->getEgressPort()->at(1));
            if (fp && RoutingConvergence::known_down(fp)) bad = true;
            if (bad && !(rc && rc->dead_end)) RoutingConvergence::decisions_to_known_dead++;
        }
        // ===== END ADDED (routing-convergence) =====
        pkt.set_direction(e->getDirection());

        //printf("I am at %s - Time %lu\n", nodename().c_str(), eventlist().now()/1000);

        if (true) {
            if (pkt.size() > 100 && _log_link_utilization) {
                std::string file_name = (SAVE_DATA_FOLDER + "/port/port" + nodename() + "_" + ".txt");
                std::ofstream MyPortFile(file_name, std::ios_base::app);
                MyPortFile << eventlist().now() / 1000 << "," << e->getEgressPort()->at(0)->nodename() << "," << pkt.id()  << std::endl;
                MyPortFile.close();
            } 

            if (pkt.size() > 100 && _log_link_utilization && pkt.name_previous_hop != "" && pkt.name_previous_direction == UP) {
                std::string file_name = (SAVE_DATA_FOLDER + "/link_util/link_util" + pkt.name_previous_hop + "_" + ".txt");
                std::ofstream MyPortFile(file_name, std::ios_base::app);
                MyPortFile << eventlist().now() / 1000 << "," << nodename() << "," << pkt.id()  << std::endl;
                MyPortFile.close();
            }  
        }

        if (_log_switch_stats) {
            _up_ports_used.push_back(e->getEgressPort()->at(0)->nodename());
        }
        
        pkt.name_previous_hop = nodename();
        pkt.name_previous_direction = e->getDirection();
        return e->getEgressPort();
    }

    //no route table entries for this destination. Add them to FIB or fail. 
    if (_type == TOR){
        int disable_count = 0;
        if ( _ft->HOST_POD_SWITCH(pkt.dst()) == _id) { 
            //this host is directly connected!
            HostFibEntry* fe = _fib->getHostRoute(pkt.dst(),pkt.flow_id());
            assert(fe);
            pkt.set_direction(DOWN);
            return fe->getEgressPort();
        } else {
            //route packet up!
            if (_uproutes)
                _fib->setRoutes(pkt.dst(),_uproutes);
            else {
                uint32_t podid,agg_min,agg_max;

                if (_ft->get_tiers()==3) {
                    podid = _id / _ft->tor_switches_per_pod();
                    agg_min = _ft->MIN_POD_AGG_SWITCH(podid);
                    agg_max = _ft->MAX_POD_AGG_SWITCH(podid);
                }
                else {
                    agg_min = 0;
                    agg_max = _ft->getNAGG()-1;
                }

                for (uint32_t k=agg_min; k<=agg_max;k++){
                    //if (k == 0) continue;
                    for (uint32_t b = 0; b < _ft->bundlesize(AGG_TIER); b++) {
                        if (disable_count < _num_disable_per_switch && _id == 0) {
                            disable_count++;
                            printf("Disabling something\n");
                            continue;
                        }
                        Route * r = new Route();
                        r->push_back(_ft->queues_nlp_nup[_id][k][b]);
                        assert(((BaseQueue*)r->at(0))->getSwitch() == this);

                        r->push_back(_ft->pipes_nlp_nup[_id][k][b]);
                        r->push_back(_ft->queues_nlp_nup[_id][k][b]->getRemoteEndpoint());
                        _fib->addRoute(pkt.dst(),r,1,UP);
                    }

                    /*
                      FatTreeSwitch* next = (FatTreeSwitch*)_ft->queues_nlp_nup[_id][k]->getRemoteEndpoint();
                      assert (next->getType()==AGG && next->getID() == k);
                    */
                }
                _uproutes = _fib->getRoutes(pkt.dst());
                // ===== ADDED (ofan) ===== Ofan needs one stable port order per switch
                if (_strategy != OFAN && _strategy != RR_FIXED)
                // ===== END ADDED (ofan) =====
                permute_paths(_uproutes);
            }
        }
    } else if (_type == AGG) {
        if ( _ft->get_tiers()==2 || _ft->HOST_POD(pkt.dst()) == _ft->AGG_SWITCH_POD_ID(_id)) {
            //must go down!
            //target NLP id is 2 * pkt.dst()/K
            uint32_t target_tor = _ft->HOST_POD_SWITCH(pkt.dst());
            for (uint32_t b = 0; b < _ft->bundlesize(AGG_TIER); b++) {
                Route * r = new Route();
                r->push_back(_ft->queues_nup_nlp[_id][target_tor][b]);
                assert(((BaseQueue*)r->at(0))->getSwitch() == this);

                r->push_back(_ft->pipes_nup_nlp[_id][target_tor][b]);          
                r->push_back(_ft->queues_nup_nlp[_id][target_tor][b]->getRemoteEndpoint());

                _fib->addRoute(pkt.dst(),r,1, DOWN);
            }
        } else {
            //go up!
            if (_uproutes)
                _fib->setRoutes(pkt.dst(),_uproutes);
            else {
                uint32_t podpos = _id % _ft->agg_switches_per_pod();
                uint32_t uplink_bundles = _ft->radix_up(AGG_TIER) / _ft->bundlesize(CORE_TIER);
                for (uint32_t l = 0; l <  uplink_bundles ; l++) {
                    uint32_t core = l * _ft->agg_switches_per_pod() + podpos;
                    for (uint32_t b = 0; b < _ft->bundlesize(CORE_TIER); b++) {
                        Route *r = new Route();
                        r->push_back(_ft->queues_nup_nc[_id][core][b]);
                        assert(((BaseQueue*)r->at(0))->getSwitch() == this);

                        r->push_back(_ft->pipes_nup_nc[_id][core][b]);
                        r->push_back(_ft->queues_nup_nc[_id][core][b]->getRemoteEndpoint());

                        /*
                          FatTreeSwitch* next = (FatTreeSwitch*)_ft->queues_nup_nc[_id][k]->getRemoteEndpoint();
                          assert (next->getType()==CORE && next->getID() == k);
                        */
                    
                        _fib->addRoute(pkt.dst(),r,1,UP);

                        //cout << "AGG switch " << _id << " adding route to " << pkt.dst() << " via CORE " << k << " bundle_id " << b << endl;
                    }
                }
                //_uproutes = _fib->getRoutes(pkt.dst());
                // ===== ADDED (ofan) ===== per-destination shuffle would break key consolidation
                if (_strategy != OFAN && _strategy != RR_FIXED)
                // ===== END ADDED (ofan) =====
                permute_paths(_fib->getRoutes(pkt.dst()));
            }
        }
    } else if (_type == CORE) {
        uint32_t nup = _ft->MIN_POD_AGG_SWITCH(_ft->HOST_POD(pkt.dst())) + (_id % _ft->agg_switches_per_pod());
        for (uint32_t b = 0; b < _ft->bundlesize(CORE_TIER); b++) {
            Route *r = new Route();
            //cout << "CORE switch " << _id << " adding route to " << pkt.dst() << " via AGG " << nup << endl;

            /* printf("CORE switch %d adding route to %d via AGG %d, bundle b %d\n", _id, pkt.dst(), nup, b); */

            assert(_ft->queues_nc_nup[_id][nup][b]);
            r->push_back(_ft->queues_nc_nup[_id][nup][b]);
            assert(((BaseQueue*)r->at(0))->getSwitch() == this);

            assert (_ft->pipes_nc_nup[_id][nup][b]);
            r->push_back(_ft->pipes_nc_nup[_id][nup][b]);

            r->push_back(_ft->queues_nc_nup[_id][nup][b]->getRemoteEndpoint());
            _fib->addRoute(pkt.dst(),r,1,DOWN);
        }
    }
    else {
        cerr << "Route lookup on switch with no proper type: " << _type << endl;
        abort();
    }
    assert(_fib->getRoutes(pkt.dst()));

    //FIB has been filled in; return choice. 
    return getNextHop(pkt, ingress_port);
};

// ===== ADDED (routing-convergence) =====
// Failure-knowledge model + reachability masks + brute-force reference check.
// Design: experiments/OFAN_ARCHITECTURE.md, section "Failure convergence model".
#include <unordered_set>
#include <algorithm>
#include <set>
#include <queue>
#include <random>
#include <cmath>

namespace RoutingConvergence {

bool enabled = false;
bool check = false;
uint32_t rand_trials = 0; uint64_t rand_seed = 1; double rand_p = 0.1;
uint64_t decisions_to_known_dead = 0;

static const simtime_picosec NEVER = 10000000000000000000ULL;  // "no recovery" (1e19 ps < 2^64)
static simtime_picosec g_G = 0;

struct Interval { simtime_picosec tf, tr; };
static unordered_map<Pipe*, vector<Interval> > g_pipes;
static vector<simtime_picosec> g_trans;    // sorted unique knowledge-transition times
static bool g_trans_dirty = true;
static size_t g_idx = 0;
static uint64_t g_epoch = 0;
static bool g_known_stale = true;
static unordered_set<Pipe*> g_known;

static uint64_t g_mismatches = 0, g_runs = 0, g_real_checks = 0, g_synth_checks = 0;

simtime_picosec G() { return g_G; }

void enable(double G_us) {
    if (!std::isfinite(G_us) || G_us < 0) {
        fprintf(stderr, "-routing_convergence_us: G must be a finite, non-negative number of microseconds (got %g)\n", G_us);
        exit(1);
    }
    double ps = G_us * 1000000.0;
    if (ps > 4e18) ps = 4e18;
    g_G = (simtime_picosec)ps;
    enabled = true;
    Pipe::_rc_drop_hook = &dropped_after_known;
}

void register_failure(Pipe* p, simtime_picosec t_fail, simtime_picosec t_recover) {
    if (!enabled || !p) return;
    Interval iv; iv.tf = t_fail; iv.tr = (t_recover > t_fail) ? t_recover : NEVER;
    g_pipes[p].push_back(iv);
    g_trans_dirty = true;
}

static void finalize_transitions() {
    if (!g_trans_dirty) return;
    g_trans.clear();
    for (unordered_map<Pipe*, vector<Interval> >::iterator it = g_pipes.begin(); it != g_pipes.end(); ++it)
        for (size_t i = 0; i < it->second.size(); i++) {
            g_trans.push_back(it->second[i].tf + g_G);
            if (it->second[i].tr < NEVER) g_trans.push_back(it->second[i].tr + g_G);
        }
    sort(g_trans.begin(), g_trans.end());
    g_trans.erase(unique(g_trans.begin(), g_trans.end()), g_trans.end());
    g_idx = 0; g_epoch = 0; g_known_stale = true; g_trans_dirty = false;
}

void refresh(simtime_picosec now) {
    finalize_transitions();
    bool changed = false;
    while (g_idx < g_trans.size() && g_trans[g_idx] <= now) { g_idx++; g_epoch++; changed = true; }
    if (changed || g_known_stale) {
        g_known.clear();
        for (unordered_map<Pipe*, vector<Interval> >::iterator it = g_pipes.begin(); it != g_pipes.end(); ++it)
            for (size_t i = 0; i < it->second.size(); i++) {
                const Interval& iv = it->second[i];
                if (iv.tf + g_G <= now && (iv.tr >= NEVER || now < iv.tr + g_G)) { g_known.insert(it->first); break; }
            }
        g_known_stale = false;
    }
}

uint64_t epoch() { return g_epoch; }
bool known_down(Pipe* p) { return p && g_known.count(p) > 0; }
bool nothing_known() { return g_known.empty(); }

bool dropped_after_known(Pipe* p, simtime_picosec now) {
    unordered_map<Pipe*, vector<Interval> >::iterator it = g_pipes.find(p);
    if (it == g_pipes.end()) return false;
    // The drop belongs to the failure interval in force at `now`: the one with the latest t_fail <= now.
    // (Fallback, should not happen: earliest interval.)
    simtime_picosec best_tf = 0; bool have = false, any = false; simtime_picosec first_tf = NEVER;
    for (size_t i = 0; i < it->second.size(); i++) {
        simtime_picosec tf = it->second[i].tf;
        first_tf = min(first_tf, tf); any = true;
        if (tf <= now && (!have || tf > best_tf)) { best_tf = tf; have = true; }
    }
    if (!any) return false;
    return now >= (have ? best_tf : first_tf) + g_G;
}

uint64_t check_mismatches() { return g_mismatches; }
uint64_t check_runs() { return g_runs; }

// ---------------- independent brute-force reference ----------------
// Graph built ONLY from the queues_* arrays (switch -> remote endpoint) plus the paired pipe.
// A FIB entry is valid iff its first-hop pipe is live and (for an upward first hop) a live
// valley-free MINIMAL path (up* then down*, hop count = intact-graph minimum) leads from the
// next switch to the destination ToR. Downward first hops: first-hop liveness only (as designed).
struct REdge { Switch* from; Switch* to; BaseQueue* q; Pipe* p; bool up; };
static vector<REdge> g_edges;
static unordered_map<Switch*, vector<int> > g_adj;
static unordered_map<BaseQueue*, int> g_edge_of_q;
static FatTreeTopology* g_ref_ft = NULL;
static map<pair<Switch*, Switch*>, int> g_minlen;

static void ref_add(vector<vector<vector<BaseQueue*> > >& Q, vector<vector<vector<Pipe*> > >& P) {
    for (size_t i = 0; i < Q.size(); i++)
        for (size_t j = 0; j < Q[i].size(); j++)
            for (size_t b = 0; b < Q[i][j].size(); b++) {
                BaseQueue* q = Q[i][j][b];
                if (!q) continue;
                if (i >= P.size() || j >= P[i].size() || b >= P[i][j].size() || !P[i][j][b]) continue;
                REdge e;
                e.q = q; e.p = P[i][j][b];
                e.from = q->getSwitch();
                e.to = dynamic_cast<Switch*>(q->getRemoteEndpoint());
                if (!e.from || !e.to) continue;
                e.up = e.from->getType() < e.to->getType();
                g_edge_of_q[q] = (int)g_edges.size();
                g_adj[e.from].push_back((int)g_edges.size());
                g_edges.push_back(e);
            }
}

static void ref_build(FatTreeTopology* ft) {
    if (g_ref_ft == ft) return;
    g_ref_ft = ft;
    g_edges.clear(); g_adj.clear(); g_edge_of_q.clear(); g_minlen.clear();
    ref_add(ft->queues_nlp_nup, ft->pipes_nlp_nup);
    ref_add(ft->queues_nup_nlp, ft->pipes_nup_nlp);
    ref_add(ft->queues_nup_nc, ft->pipes_nup_nc);
    ref_add(ft->queues_nc_nup, ft->pipes_nc_nup);
}

// minimal up*-down* hop count S->T on the intact graph (BFS over (switch, phase))
static int ref_minlen(Switch* S, Switch* T) {
    pair<Switch*, Switch*> key(S, T);
    map<pair<Switch*, Switch*>, int>::iterator f = g_minlen.find(key);
    if (f != g_minlen.end()) return f->second;
    map<pair<Switch*, int>, int> dist;
    std::queue<pair<Switch*, int> > qu;
    dist[make_pair(S, 0)] = 0; qu.push(make_pair(S, 0));
    int best = -1;
    while (!qu.empty() && best < 0) {
        pair<Switch*, int> cur = qu.front(); qu.pop();
        int d = dist[cur];
        if (cur.first == T) { best = d; break; }
        vector<int>& adj = g_adj[cur.first];
        for (size_t k = 0; k < adj.size(); k++) {
            const REdge& e = g_edges[adj[k]];
            if (cur.second == 1 && e.up) continue;
            pair<Switch*, int> nx(e.to, e.up ? 0 : 1);
            if (dist.find(nx) == dist.end()) { dist[nx] = d + 1; qu.push(nx); }
        }
    }
    g_minlen[key] = best;
    return best;
}

static bool ref_reach(Switch* cur, int phase, int remaining, Switch* T) {
    if (cur == T) return remaining == 0;
    if (remaining == 0) return false;
    vector<int>& adj = g_adj[cur];
    for (size_t k = 0; k < adj.size(); k++) {
        const REdge& e = g_edges[adj[k]];
        if (known_down(e.p)) continue;
        if (phase == 1 && e.up) continue;
        if (ref_reach(e.to, e.up ? 0 : 1, remaining - 1, T)) return true;
    }
    return false;
}

static void ref_mask(FatTreeTopology* ft, vector<FibEntry*>* hops, uint32_t T, vector<bool>& out, const char* who) {
    Switch* Tsw = ft->switches_lp[T];
    out.assign(hops->size(), true);
    for (size_t i = 0; i < hops->size(); i++) {
        Route* r = (*hops)[i]->getEgressPort();
        BaseQueue* q = dynamic_cast<BaseQueue*>(r->at(0));
        unordered_map<BaseQueue*, int>::iterator it = g_edge_of_q.find(q);
        if (it == g_edge_of_q.end()) {
            g_mismatches++;
            printf("ROUTING_CHECK MISMATCH %s: FIB queue not in topology arrays\n", who);
            continue;
        }
        const REdge& e = g_edges[it->second];
        if (dynamic_cast<Pipe*>(r->at(1)) != e.p) {
            g_mismatches++;
            printf("ROUTING_CHECK MISMATCH %s: FIB pipe differs from paired pipe\n", who);
        }
        if (known_down(e.p)) out[i] = false;
        else if (!e.up) out[i] = true;
        else {
            int L = ref_minlen(e.from, Tsw);
            out[i] = (L >= 2) && ref_reach(e.to, 0, L - 1, Tsw);
        }
    }
}

static void compare_masks(FatTreeSwitch* S, uint32_t T, const vector<bool>& prod, const vector<bool>& ref,
                          const char* tag, const char* when) {
    for (size_t i = 0; i < prod.size(); i++)
        if (prod[i] != ref[i]) {
            g_mismatches++;
            if (g_mismatches <= 40)
                printf("ROUTING_CHECK MISMATCH (%s,%s) switch=%s dstTor=%u entry=%zu prod=%d ref=%d\n", tag, when,
                       S->nodename().c_str(), T, i, (int)prod[i], (int)ref[i]);
        }
}

void check_real(FatTreeTopology* ft, FatTreeSwitch* S, vector<FibEntry*>* hops, uint32_t T, const vector<bool>& mask) {
    ref_build(ft);
    vector<bool> r;
    ref_mask(ft, hops, T, r, "real");
    compare_masks(S, T, mask, r, "real-FIB", "runtime");
    g_real_checks++;
}

static FibEntry* synth_entry(const REdge& e) {
    Route* r = new Route();
    r->push_back(e.q); r->push_back(e.p); r->push_back(e.q->getRemoteEndpoint());
    return new FibEntry(r, 1, e.up ? UP : DOWN);
}

static void synth_pass(FatTreeTopology* ft, const char* when, bool item6);

void run_check(FatTreeTopology* ft, const char* when) {
    EventList& el = EventList::getTheEventList();
    refresh(el.now());
    ref_build(ft);
    g_runs++;
    synth_pass(ft, when, true);
}

void run_check_random(FatTreeTopology* ft) {
    if (rand_trials == 0) return;
    EventList& el = EventList::getTheEventList();
    refresh(el.now());
    ref_build(ft);
    unordered_set<Pipe*> saved = g_known;
    vector<Pipe*> all;
    for (size_t i = 0; i < g_edges.size(); i++) all.push_back(g_edges[i].p);
    std::mt19937_64 rng(rand_seed);
    std::uniform_real_distribution<double> U(0.0, 1.0);
    uint64_t before = g_mismatches, down_total = 0;
    for (uint32_t t = 0; t < rand_trials; t++) {
        g_known.clear();
        for (size_t i = 0; i < all.size(); i++) if (U(rng) < rand_p) g_known.insert(all[i]);
        down_total += g_known.size();
        synth_pass(ft, "random", false);   // item6 (same-pod agg-mask equality) assumes only Agg<->Core failures
    }
    g_known = saved;
    g_known_stale = true;
    printf("ROUTING_CHECK_RANDOM trials=%u seed=%llu p=%g pipes=%zu avg_down=%.1f mismatches=%llu\n", rand_trials,
           (unsigned long long)rand_seed, rand_p, all.size(), (double)down_total / rand_trials,
           (unsigned long long)(g_mismatches - before));
}

static void synth_pass(FatTreeTopology* ft, const char* when, bool item6) {
    uint32_t ntors = (uint32_t)ft->switches_lp.size();
    bool three = FatTreeTopology::get_tiers() == 3;
    uint32_t A = ft->agg_switches_per_pod();
    uint32_t TPP = ft->tor_switches_per_pod();
    // item 6: (agg, dst pod) -> first non-dead-end mask
    map<pair<uint32_t, uint32_t>, vector<bool> > agg_up_masks;
    vector<Switch*> all;
    all.insert(all.end(), ft->switches_lp.begin(), ft->switches_lp.end());
    all.insert(all.end(), ft->switches_up.begin(), ft->switches_up.end());
    all.insert(all.end(), ft->switches_c.begin(), ft->switches_c.end());
    for (size_t si = 0; si < all.size(); si++) {
        FatTreeSwitch* S = dynamic_cast<FatTreeSwitch*>(all[si]);
        if (!S) continue;
        vector<int>& adj = g_adj[S];
        uint32_t type = S->getType();
        for (uint32_t T = 0; T < ntors; T++) {
            if (type == FatTreeSwitch::TOR && S->getID() == T) continue;
            uint32_t podT = three ? T / TPP : 0;
            uint32_t podS = (three && type == FatTreeSwitch::AGG) ? S->getID() / A : 0;
            bool agg_up = false;
            vector<FibEntry*> hops;
            for (size_t k = 0; k < adj.size(); k++) {
                const REdge& e = g_edges[adj[k]];
                bool take = false;
                if (type == FatTreeSwitch::TOR) take = e.up;
                else if (type == FatTreeSwitch::AGG) {
                    if (three && podT != podS) { take = e.up; agg_up = true; }
                    else take = (!e.up && e.to == ft->switches_lp[T]);
                } else {  // CORE: down toward the agg of dst pod
                    FatTreeSwitch* nb = dynamic_cast<FatTreeSwitch*>(e.to);
                    take = !e.up && nb && (nb->getID() / A == podT);
                }
                if (take) hops.push_back(synth_entry(e));
            }
            if (!hops.empty()) {
                vector<bool> prod, ref;
                S->rc_compute_mask(&hops, T, prod);
                ref_mask(ft, &hops, T, ref, "synthetic");
                compare_masks(S, T, prod, ref, "synthetic", when);
                g_synth_checks++;
                if (agg_up && item6) {
                    bool any = false;
                    for (size_t i = 0; i < prod.size(); i++) any = any || prod[i];
                    if (any) {
                        pair<uint32_t, uint32_t> key(S->getID(), podT);
                        map<pair<uint32_t, uint32_t>, vector<bool> >::iterator f = agg_up_masks.find(key);
                        if (f == agg_up_masks.end()) agg_up_masks[key] = prod;
                        else if (f->second != prod) {
                            g_mismatches++;
                            if (g_mismatches <= 40)
                                printf("ROUTING_CHECK MISMATCH (item6,%s) agg=%u dstPod=%u: masks of two dst ToRs differ outside dead-end\n",
                                       when, S->getID(), podT);
                        }
                    }
                }
            }
            for (size_t i = 0; i < hops.size(); i++) { delete hops[i]->getEgressPort(); delete hops[i]; }
        }
    }
}

class RcCheckEvent : public EventSource {
public:
    RcCheckEvent(EventList& el, FatTreeTopology* ft)
        : EventSource(el, "rc_check"), _ft(ft), _i(0) {
        finalize_transitions();
        _times.push_back(0);
        for (size_t i = 0; i < g_trans.size(); i++) if (g_trans[i] > 0) _times.push_back(g_trans[i]);
        eventlist().sourceIsPending(*this, _times[0]);
    }
    void doNextEvent() override {
        run_check(_ft, "epoch");
        _i++;
        if (_i < _times.size()) eventlist().sourceIsPending(*this, _times[_i]);
    }
private:
    FatTreeTopology* _ft;
    vector<simtime_picosec> _times;
    size_t _i;
};

void schedule_checks(EventList& el, FatTreeTopology* ft) {
    new RcCheckEvent(el, ft);
}

void print_summary() {
    printf("ROUTING_CONV decisions_to_known_dead=%llu drops_before_known=%llu drops_after_known=%llu\n",
           (unsigned long long)decisions_to_known_dead,
           (unsigned long long)Pipe::_rc_drops_before_known,
           (unsigned long long)Pipe::_rc_drops_after_known);
    if (check)
        printf("ROUTING_CHECK_INFO runs=%llu synthetic_pairs=%llu real_fib_vectors=%llu\n",
               (unsigned long long)g_runs, (unsigned long long)g_synth_checks, (unsigned long long)g_real_checks);
}

}  // namespace RoutingConvergence

// ---------------- FatTreeSwitch members ----------------
static bool rc_any_live(const vector<Pipe*>& v) {
    for (size_t i = 0; i < v.size(); i++)
        if (v[i] && !RoutingConvergence::known_down(v[i])) return true;
    return false;
}

// Does AGG switch `k` reach dst ToR T over live pipes? (any live bundle per leg)
bool FatTreeSwitch::rc_agg_reaches(uint32_t k, uint32_t T) {
    if (FatTreeTopology::get_tiers() == 2)
        return rc_any_live(_ft->pipes_nup_nlp[k][T]);
    uint32_t A = _ft->agg_switches_per_pod();
    uint32_t podT = T / _ft->tor_switches_per_pod();
    if (k / A == podT)
        return rc_any_live(_ft->pipes_nup_nlp[k][T]);
    uint32_t podpos = k % A;
    uint32_t uplink_bundles = _ft->radix_up(AGG_TIER) / _ft->bundlesize(CORE_TIER);
    for (uint32_t l = 0; l < uplink_bundles; l++) {
        uint32_t c = l * A + podpos;
        if (!rc_any_live(_ft->pipes_nup_nc[k][c])) continue;
        uint32_t dagg = podT * A + c % A;
        if (rc_any_live(_ft->pipes_nc_nup[c][dagg]) && rc_any_live(_ft->pipes_nup_nlp[dagg][T])) return true;
    }
    return false;
}

void FatTreeSwitch::rc_compute_mask(vector<FibEntry*>* hops, uint32_t T, vector<bool>& valid) {
    RoutingConvergence::refresh(eventlist().now());
    valid.assign(hops->size(), true);
    for (size_t i = 0; i < hops->size(); i++) {
        FibEntry* fe = (*hops)[i];
        Route* r = fe->getEgressPort();
        Pipe* p = dynamic_cast<Pipe*>(r->at(1));
        bool ok = !RoutingConvergence::known_down(p);
        if (ok && fe->getDirection() == UP) {
            FatTreeSwitch* n = dynamic_cast<FatTreeSwitch*>(r->at(2));
            if (!n) {
                fprintf(stderr, "rc_compute_mask: next hop of an UP FIB entry at %s is not a FatTreeSwitch\n", nodename().c_str());
                exit(1);
            }
            {
                if (_type == TOR) ok = rc_agg_reaches(n->getID(), T);
                else if (_type == AGG) {  // up to core c, 3-tier
                    uint32_t c = n->getID();
                    uint32_t A = _ft->agg_switches_per_pod();
                    uint32_t podT = T / _ft->tor_switches_per_pod();
                    uint32_t dagg = podT * A + c % A;
                    ok = rc_any_live(_ft->pipes_nc_nup[c][dagg]) && rc_any_live(_ft->pipes_nup_nlp[dagg][T]);
                }
            }
        }
        valid[i] = ok;
    }
}

FatTreeSwitch::RcEntry* FatTreeSwitch::rc_lookup(vector<FibEntry*>* hops, uint32_t T) {
    RoutingConvergence::refresh(eventlist().now());
    uint64_t ep = RoutingConvergence::epoch();
    if (ep != _rc_last_epoch) {
        // flowlet egress indices refer to the vector used in the previous epoch
        for (unordered_map<uint32_t,FlowletInfo*>::iterator it = _flowlet_maps.begin(); it != _flowlet_maps.end(); ++it)
            delete it->second;
        _flowlet_maps.clear();
        _rc_last_epoch = ep;
    }
    if (RoutingConvergence::nothing_known()) return NULL;
    RcKey key; key.v = hops; key.dst_tor = T;
    unordered_map<RcKey, RcEntry, RcKeyHash>::iterator it = _rc_cache.find(key);
    if (it != _rc_cache.end() && it->second.epoch == ep)
        return it->second.all_valid ? NULL : &it->second;
    RcEntry& e = _rc_cache[key];
    e.epoch = ep;
    rc_compute_mask(hops, T, e.valid);
    size_t nvalid = 0;
    for (size_t i = 0; i < e.valid.size(); i++) nvalid += e.valid[i] ? 1 : 0;
    e.all_valid = (nvalid == e.valid.size());
    e.dead_end = (nvalid == 0);
    e.filtered.clear();
    e.invalid.clear();
    for (size_t i = 0; i < hops->size(); i++) {
        if (e.valid[i]) { if (!e.all_valid && !e.dead_end) e.filtered.push_back((*hops)[i]); }
        else e.invalid.push_back((*hops)[i]);
    }
    if (RoutingConvergence::check)
        RoutingConvergence::check_real(_ft, this, hops, T, e.valid);
    return e.all_valid ? NULL : &e;
}
// ===== END ADDED (routing-convergence) =====
