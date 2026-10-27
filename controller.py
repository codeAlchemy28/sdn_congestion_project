import time

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    MAIN_DISPATCHER,
    CONFIG_DISPATCHER,
    set_ev_cls
)
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib import hub

from dashboard_state import (
    initialize_state,
    update_state,
    add_event
)


class CongestionController(app_manager.OSKenApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    # Path A is intentionally limited to 5 Mbps
    PATH_A_CAPACITY = 5_000_000

    # Congestion threshold = 80%
    THRESHOLD = 0.80

    # Priority used for dynamic rerouting rules
    REROUTE_PRIORITY = 200

    def __init__(self, *args, **kwargs):
        super(CongestionController, self).__init__(*args, **kwargs)

        self.datapaths = {}
        self.previous_bytes = {}

        self.congested = False
        self.congestion_time = None
        self.path_b_last_packets = None
        self.recovery_time = None

        # Initialize dashboard state
        initialize_state()

        # Start monitoring
        self.monitor_thread = hub.spawn(self.monitor)

    # ============================================================
    # SWITCH CONNECTION
    # ============================================================

    @set_ev_cls(
        ofp_event.EventOFPSwitchFeatures,
        CONFIG_DISPATCHER
    )
    def switch_features_handler(self, ev):

        datapath = ev.msg.datapath
        dpid = datapath.id

        self.datapaths[dpid] = datapath

        print(
            f"[CONTROLLER] Switch s{dpid} connected"
        )

        # --------------------------------------------------------
        # PERMANENT FIX:
        # Remove any old priority-200 rerouting rule.
        #
        # This means that even if the controller is restarted,
        # old Path B rules will NOT remain active.
        # --------------------------------------------------------

        self.clear_old_reroute_rule(datapath)

        # Add table-miss rule
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        match = parser.OFPMatch()

        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER
            )
        ]

        self.add_flow(
            datapath,
            priority=0,
            match=match,
            actions=actions
        )

        # Install normal Path A rules
        self.install_initial_path(datapath)

    # ============================================================
    # FLOW INSTALLATION
    # ============================================================

    def add_flow(
        self,
        datapath,
        priority,
        match,
        actions
    ):

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        instructions = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        flow_mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions
        )

        datapath.send_msg(flow_mod)

    # ============================================================
    # PERMANENT STALE FLOW CLEANUP
    # ============================================================

    def clear_old_reroute_rule(self, datapath):

        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # This is the same match used by the dynamic Path B rule
        match = parser.OFPMatch(
            eth_type=0x0800,
            ipv4_dst="10.0.0.2"
        )

        flow_mod = parser.OFPFlowMod(
            datapath=datapath,

            # Delete ONLY the exact priority-200 rule
            command=ofproto.OFPFC_DELETE_STRICT,

            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,

            priority=self.REROUTE_PRIORITY,

            match=match
        )

        datapath.send_msg(flow_mod)

        print(
            f"[FLOW CLEANUP] Removed old "
            f"priority-{self.REROUTE_PRIORITY} "
            f"reroute rule from s{datapath.id}"
        )

    # ============================================================
    # INITIAL PATH A
    # ============================================================

    def install_initial_path(self, datapath):

        dpid = datapath.id
        parser = datapath.ofproto_parser

        # Path A: h1 -> s1 -> s2 -> s3 -> s5 -> h2
        forward_ports = {
            1: 2,
            2: 2,
            3: 2,
            5: 2,
        }

        # Reverse path: h2 -> s5 -> s3 -> s2 -> s1 -> h1
        reverse_ports = {
            1: 1,
            2: 1,
            3: 1,
            5: 1,
        }

        # IPv4 traffic toward h2 follows Path A.
        if dpid in forward_ports:
            match = parser.OFPMatch(
                eth_type=0x0800,
                ipv4_dst="10.0.0.2"
            )
            actions = [
                parser.OFPActionOutput(forward_ports[dpid])
            ]
            self.add_flow(
                datapath,
                priority=100,
                match=match,
                actions=actions
            )

        # IPv4 traffic toward h1 follows the reverse path.
        if dpid in reverse_ports:
            match = parser.OFPMatch(
                eth_type=0x0800,
                ipv4_dst="10.0.0.1"
            )
            actions = [
                parser.OFPActionOutput(reverse_ports[dpid])
            ]
            self.add_flow(
                datapath,
                priority=100,
                match=match,
                actions=actions
            )

        # ARP requests targeting h2 travel along Path A.
        if dpid in forward_ports:
            match = parser.OFPMatch(
                eth_type=0x0806,
                arp_tpa="10.0.0.2"
            )
            actions = [
                parser.OFPActionOutput(forward_ports[dpid])
            ]
            self.add_flow(
                datapath,
                priority=100,
                match=match,
                actions=actions
            )

        # ARP requests/replies targeting h1 use the reverse path.
        if dpid in reverse_ports:
            match = parser.OFPMatch(
                eth_type=0x0806,
                arp_tpa="10.0.0.1"
            )
            actions = [
                parser.OFPActionOutput(reverse_ports[dpid])
            ]
            self.add_flow(
                datapath,
                priority=100,
                match=match,
                actions=actions
            )

        print(
            f"[FLOW] s{dpid}: "
            "Initial Path A IPv4 and ARP rules installed",
            flush=True
        )

    # ============================================================
    # MONITORING THREAD
    # ============================================================

    def monitor(self):

        print(
            "[MONITOR] Statistics monitoring thread started"
        )

        while True:

            try:

                for datapath in list(
                    self.datapaths.values()
                ):

                    print(
                        f"[MONITOR] Requesting stats "
                        f"from s{datapath.id}"
                    )

                    parser = datapath.ofproto_parser
                    ofproto = datapath.ofproto

                    request = parser.OFPPortStatsRequest(
                        datapath=datapath,
                        flags=0,
                        port_no=ofproto.OFPP_ANY
                    )

                    datapath.send_msg(request)

                hub.sleep(2)

            except Exception as e:

                print(
                    f"[MONITOR ERROR] {e}"
                )

                hub.sleep(2)

    # ============================================================
    # PORT STATISTICS
    # ============================================================

    @set_ev_cls(
        ofp_event.EventOFPPortStatsReply,
        MAIN_DISPATCHER
    )
    def port_stats_reply_handler(self, ev):

        try:

            datapath = ev.msg.datapath
            dpid = datapath.id

            current_time = time.monotonic()

            print(
                f"[STATS] Received port statistics "
                f"from s{dpid}"
            )

            # ----------------------------------------------------
            # We monitor s3-eth2.
            #
            # This is the outgoing link of Path A:
            #
            # s3 -> s5
            # ----------------------------------------------------

            # Observe traffic leaving s1 toward Path B (s1-eth3).
            if dpid == 1:
                for stat in ev.msg.body:
                    if stat.port_no != 3:
                        continue

                    current_packets = stat.tx_packets

                    if self.path_b_last_packets is None:
                        self.path_b_last_packets = current_packets
                        return

                    previous_packets = self.path_b_last_packets
                    self.path_b_last_packets = current_packets

                    if (
                        self.congested
                        and self.congestion_time is not None
                        and self.recovery_time is None
                        and current_packets > previous_packets
                    ):
                        self.recovery_time = (
                            current_time - self.congestion_time
                        )
                        print(
                            "[RECOVERY] First increase in Path B "
                            "traffic observed at s1-eth3 after "
                            f"{self.recovery_time:.3f} seconds. "
                            "Timing is limited by statistics polling.",
                            flush=True
                        )
                    return

            if dpid != 3:
                return

            for stat in ev.msg.body:

                if stat.port_no != 2:
                    continue

                current_bytes = stat.tx_bytes

                key = (
                    dpid,
                    stat.port_no
                )

                # ------------------------------------------------
                # First measurement
                # ------------------------------------------------

                if key not in self.previous_bytes:

                    self.previous_bytes[key] = (
                        current_bytes,
                        current_time
                    )

                    print(
                        "[STATS] Initial counter "
                        f"for s3-eth2 = "
                        f"{current_bytes} bytes"
                    )

                    return

                previous_bytes, previous_time = (
                    self.previous_bytes[key]
                )

                byte_difference = (
                    current_bytes -
                    previous_bytes
                )

                time_difference = (
                    current_time -
                    previous_time
                )

                if time_difference <= 0:
                    return

                # ------------------------------------------------
                # Calculate bitrate
                # ------------------------------------------------

                bitrate = (
                    byte_difference * 8
                ) / time_difference

                bitrate_mbps = (
                    bitrate / 1_000_000
                )

                # ------------------------------------------------
                # Calculate utilization
                # ------------------------------------------------

                utilization = (
                    bitrate /
                    self.PATH_A_CAPACITY
                ) * 100

                print(
                    "[MONITOR] Path A = "
                    f"{bitrate_mbps:.2f} Mbps "
                    f"({utilization:.1f}% utilization)"
                )

                # Save current counters
                self.previous_bytes[key] = (
                    current_bytes,
                    current_time
                )

                # ------------------------------------------------
                # Update dashboard continuously
                # ------------------------------------------------

                update_state(
                    status="ACTIVE",

                    active_path=(
                        "Path B"
                        if self.congested
                        else "Path A"
                    ),

                    path_a_utilization=round(
                        utilization,
                        2
                    ),

                    path_a_rate=round(
                        bitrate_mbps,
                        2
                    ),

                    threshold=(
                        self.THRESHOLD * 100
                    ),

                    congestion_detected=(
                        self.congested
                    )
                )

                # ------------------------------------------------
                # CONGESTION DETECTION
                # ------------------------------------------------

                if (
                    utilization >=
                    self.THRESHOLD * 100
                    and
                    not self.congested
                ):

                    self.congested = True

                    self.congestion_time = (
                        time.monotonic()
                    )
                    print(
                        '[TIMING] Congestion detected; '
                        f'monotonic={self.congestion_time:.6f}',
                        flush=True
                    )

                    print()
                    print(
                        "=========================================="
                    )
                    print(
                        "[CONTROLLER] CONGESTION DETECTED!"
                    )
                    print(
                        "[CONTROLLER] Path A utilization: "
                        f"{utilization:.1f}%"
                    )
                    print(
                        "[CONTROLLER] Congestion threshold: "
                        "80%"
                    )
                    print(
                        "=========================================="
                    )

                    add_event(
                        "danger",
                        "Congestion detected — "
                        f"Path A reached "
                        f"{utilization:.1f}% utilization"
                    )

                    self.reroute_to_path_b()

        except Exception as e:

            print(
                f"[STATS HANDLER ERROR] {e}"
            )

    # ============================================================
    # REROUTE TO PATH B
    # ============================================================

    def reroute_to_path_b(self):

        print()
        print(
            "[CONTROLLER] Switching traffic "
            "to Path B..."
        )

        add_event(
            "warning",
            "Switching traffic from "
            "Path A to Path B"
        )

        # --------------------------------------------------------
        # Path B:
        #
        # h1 -> s1 -> s4 -> s6 -> s5 -> h2
        # --------------------------------------------------------

        self.install_destination_rule(
            dpid=1,
            output_port=3
        )

        self.install_destination_rule(
            dpid=4,
            output_port=2
        )

        self.install_destination_rule(
            dpid=6,
            output_port=2
        )

        self.install_destination_rule(
            dpid=5,
            output_port=2
        )

        # --------------------------------------------------------
        # Dashboard update
        # --------------------------------------------------------

        update_state(
            active_path="Path B",
            congestion_detected=True,
            last_event=(
                "Traffic successfully "
                "rerouted to Path B"
            )
        )

        add_event(
            "success",
            "Traffic successfully "
            "rerouted to Path B"
        )

        print(
            "[CONTROLLER] Path B activated!"
        )

        print(
            "[CONTROLLER] "
            "h1 -> s1 -> s4 -> s6 -> s5 -> h2"
        )

        print()

    # ============================================================
    # INSTALL DYNAMIC DESTINATION RULE
    # ============================================================

    def install_destination_rule(
        self,
        dpid,
        output_port
    ):

        if dpid not in self.datapaths:

            print(
                f"[FLOW ERROR] s{dpid} "
                "is not connected"
            )

            return

        datapath = self.datapaths[dpid]

        parser = datapath.ofproto_parser

        # --------------------------------------------------------
        # Destination-based rule
        # --------------------------------------------------------

        match = parser.OFPMatch(
            eth_type=0x0800,
            ipv4_dst="10.0.0.2"
        )

        actions = [
            parser.OFPActionOutput(
                output_port
            )
        ]

        # --------------------------------------------------------
        # Priority 200 overrides the normal
        # priority-100 Path A rule.
        # --------------------------------------------------------

        self.add_flow(
            datapath,
            priority=self.REROUTE_PRIORITY,
            match=match,
            actions=actions
        )

        print(
            f"[FLOW] s{dpid}: "
            f"10.0.0.2 -> "
            f"port {output_port} "
            f"(priority {self.REROUTE_PRIORITY})"
        )


# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":

    print()
    print(
        "=============================================="
    )
    print(
        " SDN CONGESTION CONTROLLER"
    )
    print(
        "=============================================="
    )
    print(
        "Path A: h1 -> s1 -> s2 -> s3 -> s5 -> h2"
    )
    print(
        "Path B: h1 -> s1 -> s4 -> s6 -> s5 -> h2"
    )
    print(
        "Congestion threshold: 80%"
    )
    print(
        "Path A capacity: 5 Mbps"
    )
    print(
        "Dynamic reroute priority: 200"
    )
    print(
        "=============================================="
    )
    print()

    # ------------------------------------------------------------
    # Python 3.14 / OS-Ken compatible startup.
    #
    # We intentionally do NOT use:
    #
    #     AppManager.run_apps()
    #
    # because Eventlet's old HubThread implementation
    # is incompatible with Python 3.14.
    # ------------------------------------------------------------

    app_mgr = (
        app_manager.AppManager.get_instance()
    )

    app_mgr.load_apps(
        ["controller"]
    )

    contexts = (
        app_mgr.create_contexts()
    )

    services = (
        app_mgr.instantiate_apps(
            **contexts
        )
    )

    hub.joinall(
        services
    )
