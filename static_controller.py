from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, set_ev_cls
from os_ken.ofproto import ofproto_v1_3


class StaticController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(StaticController, self).__init__(*args, **kwargs)
        self.logger.info("STATIC ROUTING CONTROLLER STARTED")
        self.logger.info("Traffic will remain on Path A")

    def add_flow(self, datapath, priority, match, actions):
        """Install a forwarding rule on an OpenFlow switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        instructions = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        flow = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions
        )

        datapath.send_msg(flow)

    @set_ev_cls(
        ofp_event.EventOFPSwitchFeatures,
        CONFIG_DISPATCHER
    )
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        # Clear existing flow entries on this switch.
        # This prevents stale adaptive-routing rules from
        # interfering with the static-routing experiment.
        delete_flows = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=parser.OFPMatch()
        )
        datapath.send_msg(delete_flows)

        # --------------------------------------------------
        # PATH A: h1 -> s1 -> s2 -> s3 -> s5 -> h2
        # --------------------------------------------------

        forward_ports = {
            1: 2,  # s1 -> s2
            2: 2,  # s2 -> s3
            3: 2,  # s3 -> s5
            5: 2,  # s5 -> h2
        }

        # Forward IPv4 packets destined for h2.
        if dpid in forward_ports:
            out_port = forward_ports[dpid]

            match = parser.OFPMatch(
                eth_type=0x0800,
                ipv4_dst="10.0.0.2"
            )

            actions = [
                parser.OFPActionOutput(out_port)
            ]

            self.add_flow(
                datapath,
                priority=100,
                match=match,
                actions=actions
            )

            self.logger.info(
                "[STATIC] s%d: IPv4 destination h2 -> port %d",
                dpid,
                out_port
            )

        # --------------------------------------------------
        # REVERSE PATH: h2 -> s5 -> s3 -> s2 -> s1 -> h1
        # --------------------------------------------------

        reverse_ports = {
            5: 1,  # s5 -> s3
            3: 1,  # s3 -> s2
            2: 1,  # s2 -> s1
            1: 1,  # s1 -> h1
        }

        # Forward IPv4 packets destined for h1.
        if dpid in reverse_ports:
            out_port = reverse_ports[dpid]

            match = parser.OFPMatch(
                eth_type=0x0800,
                ipv4_dst="10.0.0.1"
            )

            actions = [
                parser.OFPActionOutput(out_port)
            ]

            self.add_flow(
                datapath,
                priority=100,
                match=match,
                actions=actions
            )

            self.logger.info(
                "[STATIC] s%d: IPv4 destination h1 -> port %d",
                dpid,
                out_port
            )

        # --------------------------------------------------
        # ARP: resolve the destination hosts' MAC addresses
        # --------------------------------------------------

        # ARP requests targeting h2 travel along Path A.
        if dpid in forward_ports:
            out_port = forward_ports[dpid]

            match = parser.OFPMatch(
                eth_type=0x0806,
                arp_tpa="10.0.0.2"
            )

            actions = [
                parser.OFPActionOutput(out_port)
            ]

            self.add_flow(
                datapath,
                priority=100,
                match=match,
                actions=actions
            )

            self.logger.info(
                "[STATIC] s%d: ARP target h2 -> port %d",
                dpid,
                out_port
            )

        # ARP requests/replies targeting h1 use the reverse
        # direction of Path A.
        if dpid in reverse_ports:
            out_port = reverse_ports[dpid]

            match = parser.OFPMatch(
                eth_type=0x0806,
                arp_tpa="10.0.0.1"
            )

            actions = [
                parser.OFPActionOutput(out_port)
            ]

            self.add_flow(
                datapath,
                priority=100,
                match=match,
                actions=actions
            )

            self.logger.info(
                "[STATIC] s%d: ARP target h1 -> port %d",
                dpid,
                out_port
            )

