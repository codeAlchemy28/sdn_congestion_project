# SDN-Based Congestion Detection and Adaptive Traffic Rerouting

## 1. Project Overview

This project implements a Software-Defined Networking (SDN) system that monitors network congestion and dynamically reroutes traffic through an alternative path.

The network is built using Mininet, Open vSwitch, and the OS-Ken SDN controller framework. Two paths connect the source host to the destination host:

* **Path A:** The primary path, configured with bandwidth limits to create congestion.
* **Path B:** An alternative path used by the adaptive controller when congestion is detected.

The project also includes a static controller to provide a baseline for comparing network performance.

The main goal is to demonstrate how SDN-based traffic management can improve throughput and reduce packet loss when the primary path becomes congested.

## 2. Objectives

* Build a software-defined network with two alternative paths.
* Introduce controlled congestion on the primary path.
* Monitor network statistics using an SDN controller.
* Detect congestion using a utilization threshold.
* Reroute traffic through an alternative path.
* Compare static routing with adaptive routing using UDP performance tests.

## 3. Network Architecture

The topology contains two hosts and six Open vSwitch switches.

### Path A — Primary Path

`h1 → s1 → s2 → s3 → s5 → h2`

Path A is intentionally limited to 5 Mbps on selected links to create a bottleneck.

### Path B — Alternative Path

`h1 → s1 → s4 → s6 → s5 → h2`

Path B provides an alternative route when the controller detects congestion on Path A.

### Network Details

| Component                | Configuration                                 |
| ------------------------ | --------------------------------------------- |
| Source host              | h1 — 10.0.0.1                                 |
| Destination host         | h2 — 10.0.0.2                                 |
| Switches                 | s1, s2, s3, s4, s5, s6                        |
| OpenFlow version         | OpenFlow 1.3                                  |
| Controller framework     | OS-Ken                                        |
| Controller address       | 127.0.0.1:6653                                |
| Path A bandwidth limit   | 5 Mbps on selected links                      |
| Congestion threshold     | 80%, as configured in the adaptive controller |
| Traffic used for testing | UDP                                           |

## 4. How It Works

### Static Routing

The static controller installs the baseline forwarding rules. Traffic follows the configured primary path, allowing us to observe the effects of the bandwidth bottleneck.

### Congestion Detection

The adaptive controller requests switch statistics and monitors utilization on the configured bottleneck link. When the measured utilization crosses the congestion threshold, the controller activates a higher-priority forwarding rule.

### Adaptive Rerouting

When congestion is detected, traffic destined for `10.0.0.2` is redirected through Path B. The higher-priority rule takes precedence over the normal forwarding rule.

This allows the network to respond dynamically to congestion without manually changing the topology.

## 5. Technologies Used

* **Mininet:** Emulates the network topology and hosts.
* **Open vSwitch:** Provides software-based switching.
* **OpenFlow 1.3:** Allows the controller to install forwarding rules.
* **OS-Ken:** Implements the SDN controller logic.
* **Python:** Implements the topology, controller, and test scripts.
* **iperf3:** Generates UDP traffic and measures network performance.
* **Linux traffic control (`tc`):** Applies bandwidth limits to selected links.

## 6. Prerequisites

This project is intended for a Linux environment. Ubuntu running under WSL may also be used if Mininet, Open vSwitch, networking permissions, and controller connectivity are configured correctly.

Install the basic system packages:

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch iperf3 python3 python3-venv python3-pip git
```

Verify the installations:

```bash
python3 --version
mn --version
ovs-vsctl --version
iperf3 --version
```

Install OS-Ken in a Python virtual environment. Use a Python version compatible with the installed OS-Ken dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install os-ken
```

The topology also requires Mininet's Python package to be available to the Python interpreter used to run it.

> Note: The project uses a custom OS-Ken launcher to start the controller. This avoids relying on the standard launcher in environments where compatibility issues occur.

## 7. Clone the Repository

Replace the URL below with the actual URL of this GitHub repository:

```bash
git clone https://github.com/YOUR-USERNAME/sdn-congestion-project.git
cd sdn-congestion-project
```

Create and activate the virtual environment as described above if it has not already been created.

## 8. Running the Project

The controller and Mininet topology must run in separate terminals.

### Step 1: Start the Open vSwitch Service

```bash
sudo service openvswitch-switch start
```

Check that Open vSwitch is running:

```bash
sudo ovs-vsctl show
```

### Step 2: Start the Controller

For the static baseline, open a terminal in the project directory, activate the virtual environment, and run:

```bash
source .venv/bin/activate
python run_static_controller.py
```

For adaptive congestion detection and rerouting, stop the static controller and run the following in its place:

```bash
source .venv/bin/activate
python run_controller.py
```

Run only one controller at a time on port `6653`.

### Step 3: Start the Mininet Topology

Open a second terminal. Navigate to the project directory and start the topology with root privileges.

Use the Python interpreter that can import Mininet:

```bash
sudo python3 topology.py
```

If your Mininet installation requires a particular Python interpreter, use that interpreter instead.

The topology should print the two paths and apply the 5 Mbps traffic-control limits to the selected Path A links.

### Step 4: Check Connectivity

At the Mininet prompt, run:

```text
pingall
```

Check whether the hosts can communicate. Initial packet loss can occur while switches learn or controller rules are installed; repeat the check if necessary.

## 9. Running UDP Performance Tests

Run tests while the topology and the selected controller are active.

### Step 1: Start the UDP Server

At the Mininet prompt, run:

```text
h2 iperf3 -s -1
```

This starts a one-time iperf3 server on the destination host.

### Step 2: Generate UDP Traffic

In the Mininet prompt, run:

```text
h1 iperf3 -c 10.0.0.2 -u -b 10M -t 20
```

This sends UDP traffic at a target rate of 10 Mbps for 20 seconds.

Record the receiver's throughput, jitter, and packet loss from the iperf3 output.

Repeat the experiment with the static controller and the adaptive controller. Restart the one-time server before each test.

### Optional: Use the Python Test Script

The repository includes `run_udp_test.py`, which can be invoked from the Mininet host after the destination server is started:

```text
h1 python3 /home/hemal/sdn-congestion-project/run_udp_test.py --mode adaptive
```

For the static test:

```text
h1 python3 /home/hemal/sdn-congestion-project/run_udp_test.py --mode static
```

Replace the example path with the actual absolute path to the cloned repository.

The test script reports receiver throughput, jitter, and packet loss. Verify the reported results against the raw iperf3 output before using them in an evaluation.

## 10. Verifying Adaptive Rerouting

After congestion has triggered the adaptive controller, inspect the flow tables from a separate terminal:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

Look for the forwarding rules associated with destination `10.0.0.2`.

In this topology, s1's port 2 leads to Path A, while port 3 leads to Path B. A higher-priority rule that outputs to port 3 indicates that the controller has installed the alternate-path rule.

You can also inspect the rule's packet counter. An increasing counter is evidence that the rule is being used.

Check the controller logs for congestion readings and rerouting messages.

## 11. Experimental Results

The following values are observations from separate test runs during development. They are preliminary and are not a controlled benchmark.

| Metric              |   Static baseline | Adaptive routing |
| ------------------- | ----------------: | ---------------: |
| Receiver throughput |         4.85 Mbps |        9.40 Mbps |
| Packet loss         | Approximately 51% | Approximately 6% |
| Jitter              |          0.763 ms |         0.048 ms |

These observations suggest that adaptive rerouting can improve performance when the primary path is congested.

However, the values were collected in separate runs. For a fair evaluation, repeat both tests under the same conditions, record multiple trials, and compare the averages. Do not assume the results will be identical on another machine or installation.

## 12. Troubleshooting

### Controller Does Not Start

* Confirm that OS-Ken is installed in the active Python environment.
* Check that the controller launcher is run from the project directory.
* Check whether another controller is already using port `6653`.

### Switches Do Not Connect to the Controller

* Confirm that the controller is running before starting the topology.
* Verify that the controller listens on `127.0.0.1:6653`.
* Check the Open vSwitch service and controller logs.

### Mininet Cannot Start

* Run the topology with the required privileges.
* Check that Mininet and Open vSwitch are installed.
* Clean up stale Mininet processes before starting a fresh experiment if needed.

### UDP Test Fails

* Make sure the topology is running.
* Verify connectivity between h1 and h2.
* Start the iperf3 server on h2 before running the client.
* Confirm that the test is running inside the Mininet host, not directly in the Ubuntu shell.

### Rerouting Does Not Occur

* Generate enough traffic to cross the configured congestion threshold.
* Check the controller's port-statistics output.
* Inspect the flow table on s1.
* Confirm that the alternate-path rule has a higher priority than the normal rule.

## 13. Limitations

* The topology is an emulated environment rather than a production network.
* Performance depends on host resources, Mininet, Open vSwitch, and traffic-control configuration.
* Preliminary test results require repeated, controlled trials before drawing strong conclusions.
* The current topology and rerouting logic focus on a particular primary bottleneck and its configured alternative route.

## 14. Future Improvements

* Evaluate multiple congestion thresholds.
* Compare additional traffic patterns and traffic rates.
* Collect repeated trials and generate performance graphs.
* Extend monitoring to more links and alternative paths.
* Improve rerouting decisions using additional network statistics.

## 15. Conclusion

This project demonstrates how an SDN controller can monitor a network bottleneck and redirect traffic through an alternative path when congestion is detected. By comparing static routing with adaptive rerouting, the project explores how programmable network control can help improve network performance.

The implementation provides a foundation for further experiments in SDN-based congestion management and traffic engineering.
