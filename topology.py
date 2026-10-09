
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel


def create_topology():
    net = Mininet(
        controller=None,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True
    )

    h1 = net.addHost('h1', ip='10.0.0.1/24')
    h2 = net.addHost('h2', ip='10.0.0.2/24')

    s1 = net.addSwitch('s1', protocols='OpenFlow13')
    s2 = net.addSwitch('s2', protocols='OpenFlow13')
    s3 = net.addSwitch('s3', protocols='OpenFlow13')
    s4 = net.addSwitch('s4', protocols='OpenFlow13')
    s5 = net.addSwitch('s5', protocols='OpenFlow13')
    s6 = net.addSwitch('s6', protocols='OpenFlow13')

    # Host connection
    net.addLink(h1, s1)

    # Path A: intentionally congested
    net.addLink(s1, s2)
    net.addLink(s2, s3)
    net.addLink(s3, s5)

    # Destination host
    net.addLink(s5, h2)

    # Path B: alternative route
    net.addLink(s1, s4)
    net.addLink(s4, s6)
    net.addLink(s6, s5)

    net.addController(
        'c0',
        controller=RemoteController,
        ip='127.0.0.1',
        port=6653
    )

    print()
    print("==============================================")
    print(" TWO-PATH SDN CONGESTION TEST TOPOLOGY")
    print("==============================================")
    print("Path A: h1 -> s1 -> s2 -> s3 -> s5 -> h2")
    print("Path B: h1 -> s1 -> s4 -> s6 -> s5 -> h2")
    print("Path A bandwidth limit: 5 Mbps per link")
    print("Congestion threshold: 80%")
    print("==============================================")
    print()

    net.start()

    try:
        # Automatically configure congestion on Path A.
        # These commands run inside the relevant switches.
        print("[TOPOLOGY] Configuring Path A bandwidth limits...")

        s1.cmd(
            'tc qdisc replace dev s1-eth2 root '
            'tbf rate 5mbit burst 32kbit latency 50ms'
        )

        s2.cmd(
            'tc qdisc replace dev s2-eth2 root '
            'tbf rate 5mbit burst 32kbit latency 50ms'
        )

        s3.cmd(
            'tc qdisc replace dev s3-eth2 root '
            'tbf rate 5mbit burst 32kbit latency 50ms'
        )

        print("[TOPOLOGY] Path A bandwidth limits applied.")

        # Keep the network running for interactive testing.
        CLI(net)

    finally:
        net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    create_topology()
